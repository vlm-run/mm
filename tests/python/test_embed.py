"""Tests for mm.store.embed — embedding generation workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from mm.store import MmDatabase
from mm.store.embed import (
    _EMBEDDINGS_PATH,
    _audio_part,
    _video_part,
    document_part,
    embed_file_chunks,
    embed_parts,
    embed_texts,
    image_part,
    text_part,
)

from .conftest import requires_sqlite_vec
from .test_utils import ensure_fast, get_hash


def _genai_available() -> bool:
    try:
        import google.genai  # noqa: F401

        return True
    except ImportError:
        return False


requires_gemini = pytest.mark.skipif(
    not _genai_available(),
    reason="google-genai not installed (pip install mm-ctx[gemini])",
)

FAKE_DIM = 4


def _mock_embeddings_response(parts: list[dict[str, Any]]) -> list[list[float]]:
    """Mock server: returns a distinct fake vector per part."""
    return [[float(i + 1)] * FAKE_DIM for i in range(len(parts))]


@pytest.fixture()
def mock_server():
    """Patch httpx.post to simulate the embedding server."""

    def _fake_post(url: str, **kwargs: Any) -> MagicMock:
        assert url.endswith(_EMBEDDINGS_PATH)
        parts = kwargs.get("json", [])
        # Validate User-Agent header
        headers = kwargs.get("headers", {})
        assert headers.get("User-Agent", "").startswith("mm-ctx/")

        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"embeddings": _mock_embeddings_response(parts)}
        return resp

    with patch("httpx.post", side_effect=_fake_post) as mock:
        yield mock


@pytest.fixture()
def db(tmp_path: Path) -> MmDatabase:
    return MmDatabase(db_path=tmp_path / "test.db")


# ---------------------------------------------------------------------------
# Part constructors
# ---------------------------------------------------------------------------


@requires_gemini
class TestPartConstructors:
    def test_text_part(self):
        from google.genai import types

        p = text_part("hello world")
        assert p["text"] == "hello world"
        types.Part.model_validate(p)

    def test_image_part(self, tmp_path: Path):
        from google.genai import types

        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        p = image_part(img)
        assert p["inline_data"]["mime_type"] == "image/png"
        assert len(p["inline_data"]["data"]) > 0
        types.Part.model_validate(p)

    def test_audio_part(self, tmp_path: Path):
        from google.genai import types

        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"\xff\xfb" + b"\x00" * 100)
        p = _audio_part(audio)
        assert p["inline_data"]["mime_type"] == "audio/mpeg"
        types.Part.model_validate(p)

    def test_document_part(self, tmp_path: Path):
        from google.genai import types

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4" + b"\x00" * 100)
        p = document_part(pdf)
        assert p["inline_data"]["mime_type"] == "application/pdf"
        types.Part.model_validate(p)

    def test_video_part(self, tmp_path: Path):
        from google.genai import types

        vid = tmp_path / "test.mp4"
        vid.write_bytes(b"\x00\x00\x00\x1cftyp" + b"\x00" * 100)
        p = _video_part(vid)
        assert p["inline_data"]["mime_type"] == "video/mp4"
        types.Part.model_validate(p)


# ---------------------------------------------------------------------------
# Server communication
# ---------------------------------------------------------------------------


@requires_gemini
class TestEmbedParts:
    def test_embed_parts_sends_correct_request(self, mock_server: MagicMock):
        parts = [text_part("one"), text_part("two")]
        vectors = embed_parts(parts)
        assert len(vectors) == 2
        assert len(vectors[0]) == FAKE_DIM
        mock_server.assert_called_once()

    def test_embed_texts(self, mock_server: MagicMock):
        vectors = embed_texts(["hello", "world", "test"])
        assert len(vectors) == 3
        assert all(len(v) == FAKE_DIM for v in vectors)

    def test_embed_parts_url(self, mock_server: MagicMock):
        embed_texts(["test"])
        call_args = mock_server.call_args
        url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
        assert url.endswith(_EMBEDDINGS_PATH)

    def test_embed_parts_user_agent(self, mock_server: MagicMock):
        embed_texts(["test"])
        call_args = mock_server.call_args
        headers = call_args[1].get("headers", {})
        assert headers["User-Agent"].startswith("mm-ctx/")

    def test_embed_parts_retries_once(self):
        import httpx

        parts = [text_part("retry")]
        success = MagicMock()
        success.raise_for_status = MagicMock()
        success.json.return_value = {"embeddings": _mock_embeddings_response(parts)}

        with patch(
            "httpx.post", side_effect=[httpx.ConnectError("temporary"), success]
        ) as mock_post:
            vectors = embed_parts(parts)

        assert len(vectors) == 1
        assert mock_post.call_count == 2


# ---------------------------------------------------------------------------
# End-to-end: embed_file_chunks
# ---------------------------------------------------------------------------


@requires_gemini
class TestEmbedFileChunks:
    @requires_sqlite_vec
    def test_embeds_chunks_after_accurate(self, db: MmDatabase, mock_server: MagicMock):
        uri = "/test/data/doc.txt"
        ensure_fast(db, uri)

        content = "Test content for embedding. " * 50
        extraction_id = db.put_extraction(uri, "hash1", "default", "qwen", content)
        with patch("mm.store.db.MmDatabase", return_value=db):
            n = embed_file_chunks(extraction_id)
        assert n > 0
        mock_server.assert_called()

    def test_returns_zero_for_missing_chunks(self, db: MmDatabase, mock_server: MagicMock):
        with patch("mm.store.db.MmDatabase", return_value=db):
            n = embed_file_chunks("nonexistent_id")
        assert n == 0
        mock_server.assert_not_called()

    @requires_sqlite_vec
    def test_vectors_stored_in_db(self, db: MmDatabase, mock_server: MagicMock):
        uri = "/test/data/doc.txt"
        ensure_fast(db, uri)
        content_hash = get_hash(uri)

        extraction_id = db.put_extraction(uri, content_hash, "default", "qwen", "Short text")
        with patch("mm.store.db.MmDatabase", return_value=db):
            embed_file_chunks(extraction_id)

        results = db.search_similar([1.0] * FAKE_DIM, limit=1)
        assert len(results) > 0
        assert "chunk_text" in results[0]

    @requires_sqlite_vec
    def test_content_preserved_after_embedding(self, db: MmDatabase, mock_server: MagicMock):
        uri = "/test/data/doc.txt"
        ensure_fast(db, uri)
        content_hash = get_hash(uri)

        content = "Preserved content. " * 100
        extraction_id = db.put_extraction(uri, content_hash, "default", "qwen", content)
        with patch("mm.store.db.MmDatabase", return_value=db):
            embed_file_chunks(extraction_id)
        full = db.get_full_content(uri, content_hash, "default", "qwen")
        assert full == content


# ---------------------------------------------------------------------------
# Cat workflow integration
# ---------------------------------------------------------------------------


class TestCatEmbedIntegration:
    def test_run_accurate_does_not_embed(self, tmp_path: Path, mock_server: MagicMock):
        """``cat`` writes chunks (via put_extraction)"""
        from mm.cat_utils.base_utils import CatOpts, RunResult
        from mm.commands.cat import _extract

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        opts = CatOpts(
            n=None,
            output_dir=None,
            mode="accurate",
            no_cache=False,
            format="rich",
            encode_overrides={},
            generate_overrides={},
            pipelines={},
            verbose=False,
        )

        mock_db = MagicMock()
        mock_db.get_extraction.return_value = None
        mock_db.put_extraction.return_value = "fake_extraction_id"

        with (
            patch(
                "mm.commands.cat._run_accurate",
                return_value=RunResult(content="LLM generated text."),
            ),
            patch("mm.store.utils.get_content_hash", return_value="fakehash"),
            patch("mm.store.db.MmDatabase", return_value=mock_db),
            patch("mm.profile.get_profile") as mock_profile,
            patch("mm.store.utils.get_extraction_id", return_value="fake_extraction_id"),
            patch("mm.store.embed.embed_file_chunks") as mock_embed_file,
            patch("mm.store.embed.embed_text_chunks_concurrent") as mock_embed_text,
            patch("mm.store.embed.embed_file_chunks_concurrent") as mock_embed_file_conc,
        ):
            mock_profile.return_value.name = "default"
            mock_profile.return_value.model = "test-model"
            result = _extract(pdf, opts)

        assert result == "LLM generated text."
        mock_db.put_extraction.assert_called_once()
        mock_embed_file.assert_not_called()
        mock_embed_text.assert_not_called()
        mock_embed_file_conc.assert_not_called()
