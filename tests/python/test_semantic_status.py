"""Tests for the 3-state index status helper and ``--pre-index`` dispatch.

The boundary under test:
- ``mm cat`` writes chunks but no embeddings (chunked-only state).
- ``mm grep -s --pre-index`` finishes the indexing — embed-only path
  for chunked-only files, full pipeline for unprocessed files.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from mm import semantic
from mm.store import MmDatabase

from .conftest import requires_sqlite_vec
from .test_utils import ensure_fast, get_hash


@pytest.fixture()
def db(tmp_path: Path) -> MmDatabase:
    return MmDatabase(db_path=tmp_path / "test.db")


@requires_sqlite_vec
class TestIndexStatusClassification:
    """``check_index_status`` partitions URIs by chunk + vec presence."""

    def test_unprocessed_when_no_chunks(self, db: MmDatabase):
        with patch("mm.store.db.MmDatabase", return_value=db):
            s = semantic.check_index_status(["/test/data/never-seen.txt"])
        assert s.unprocessed == {"/test/data/never-seen.txt"}
        assert s.chunked_only == set()
        assert s.indexed == set()

    def test_chunked_only_when_extraction_present_but_no_vec(self, db: MmDatabase):
        uri = "/test/data/doc.txt"
        ensure_fast(db, uri)
        # Write extraction-bound chunks but skip embedding.
        db.put_extraction(uri, get_hash(uri), "default", "qwen", "Some content")

        with patch("mm.store.db.MmDatabase", return_value=db):
            s = semantic.check_index_status([uri])
        assert s.chunked_only == {uri}
        assert s.unprocessed == set()
        assert s.indexed == set()
        # Resume hint: extraction id captured for the embed-only path.
        assert uri in s.extraction_ids_by_uri
        assert len(s.extraction_ids_by_uri[uri]) >= 1

    def test_chunked_only_for_text_passthrough(self, db: MmDatabase):
        uri = "/test/data/main.py"
        ensure_fast(db, uri)
        ch = get_hash(uri)
        db.put_text_chunks(uri=uri, content_hash=ch, content="print('hi')\n" * 5)

        with patch("mm.store.db.MmDatabase", return_value=db):
            s = semantic.check_index_status([uri])
        assert s.chunked_only == {uri}
        assert s.text_hashes_by_uri.get(uri) == ch
        assert uri not in s.extraction_ids_by_uri


class TestIndexMissingDispatch:
    """``index_missing`` skips ``_index_one`` for chunked-only URIs."""

    def test_chunked_only_uses_embed_only_path(self):
        uri = "/test/data/doc.txt"
        status = semantic.IndexStatus(
            chunked_only={uri},
            extraction_ids_by_uri={uri: ["eid-1"]},
        )

        with (
            patch.object(semantic, "_index_one") as mock_extract,
            patch.object(semantic, "_embed_chunked_only", return_value=uri) as mock_embed,
            patch("mm.encoders._ensure_discovered"),
        ):
            n = semantic.index_missing([uri], status=status)

        assert n == 1
        mock_extract.assert_not_called()
        mock_embed.assert_called_once_with(uri, ["eid-1"], None)

    def test_unprocessed_uses_full_pipeline(self):
        uri = "/test/data/photo.png"
        status = semantic.IndexStatus(unprocessed={uri})

        with (
            patch.object(semantic, "_index_one", return_value=uri) as mock_extract,
            patch.object(semantic, "_embed_chunked_only") as mock_embed,
            patch("mm.encoders._ensure_discovered"),
        ):
            n = semantic.index_missing([uri], status=status)

        assert n == 1
        mock_extract.assert_called_once_with(uri)
        mock_embed.assert_not_called()


class TestIndexOneUsesFastMode:
    """``_index_one`` must invoke ``_extract`` with ``mode='fast'``."""

    def test_passes_fast_mode_to_extract(self, tmp_path: Path):
        png = tmp_path / "x.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)

        from mm.results import CatResult

        with (
            patch(
                "mm.cat_utils.extract.extract",
                return_value=CatResult(path=str(png), content="caption", mode="fast", kind="image"),
            ) as mock_extract,
            patch.object(
                semantic,
                "check_index_status",
                return_value=semantic.IndexStatus(),
            ),
            patch.object(semantic, "_embed_chunked_only", return_value=str(png)),
        ):
            semantic._index_one(str(png))

        assert mock_extract.call_count == 1
        opts = mock_extract.call_args[0][1]
        assert opts.mode == "fast"
