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

from .test_utils import ensure_l1, get_hash

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
        assert url.endswith("/v1/embeddings")

    def test_embed_parts_user_agent(self, mock_server: MagicMock):
        embed_texts(["test"])
        call_args = mock_server.call_args
        headers = call_args[1].get("headers", {})
        assert headers["User-Agent"].startswith("mm-ctx/")


# ---------------------------------------------------------------------------
# End-to-end: embed_file_chunks
# ---------------------------------------------------------------------------


class TestEmbedFileChunks:
    def test_embeds_chunks_after_l2(self, db: MmDatabase, mock_server: MagicMock):
        uri = "/test/data/doc.txt"
        ensure_l1(db, uri)

        content = "Test content for embedding. " * 50
        l2_id = db.put_l2(uri, "hash1", "default", "qwen", content)
        with patch("mm.store.db.MmDatabase", return_value=db):
            n = embed_file_chunks(l2_id)
        assert n > 0
        mock_server.assert_called()

    def test_returns_zero_for_missing_chunks(self, db: MmDatabase, mock_server: MagicMock):
        with patch("mm.store.db.MmDatabase", return_value=db):
            n = embed_file_chunks("nonexistent_id")
        assert n == 0
        mock_server.assert_not_called()

    def test_vectors_stored_in_db(self, db: MmDatabase, mock_server: MagicMock):
        uri = "/test/data/doc.txt"
        ensure_l1(db, uri)
        content_hash = get_hash(uri)

        l2_id = db.put_l2(uri, content_hash, "default", "qwen", "Short text")
        with patch("mm.store.db.MmDatabase", return_value=db):
            embed_file_chunks(l2_id)

        results = db.search_similar([1.0] * FAKE_DIM, limit=1)
        assert len(results) > 0
        assert "chunk_text" in results[0]

    def test_content_preserved_after_embedding(self, db: MmDatabase, mock_server: MagicMock):
        uri = "/test/data/doc.txt"
        ensure_l1(db, uri)
        content_hash = get_hash(uri)

        content = "Preserved content. " * 100
        l2_id = db.put_l2(uri, content_hash, "default", "qwen", content)
        with patch("mm.store.db.MmDatabase", return_value=db):
            embed_file_chunks(l2_id)
        full = db.get_full_content(uri, content_hash, "default", "qwen")
        assert full == content


# ---------------------------------------------------------------------------
# Cat workflow integration
# ---------------------------------------------------------------------------


class TestCatEmbedIntegration:
    def test_run_l2_triggers_embedding(self, tmp_path: Path, mock_server: MagicMock):
        """After L2 extraction, embed_file_chunks should be called."""
        from mm.commands.cat import _CatOpts, _run_l2

        txt = tmp_path / "test.txt"
        txt.write_text("hello")

        opts = _CatOpts(
            level=2,
            n=None,
            detail=False,
            output_dir=None,
            mosaic_tile="4x4",
            mosaic_image_width=160,
            video_mosaic_count=1,
            video_mosaic_strategy="uniform",
            mode=None,
            no_cache=False,
            format="rich",
        )

        mock_db = MagicMock()
        mock_db.get_l2.return_value = None  # cache miss
        l2_id = "fake_l2_id"
        mock_db.put_l2.return_value = l2_id

        with (
            patch("mm.commands.cat._l2", return_value="LLM generated text."),
            patch("mm.store.util.get_content_hash", return_value="fakehash"),
            patch("mm.store.db.MmDatabase", return_value=mock_db),
            patch("mm.profile.get_profile") as mock_profile,
            patch("mm.store.embed.embed_file_chunks") as mock_embed,
        ):
            mock_profile.return_value.name = "default"
            mock_profile.return_value.model = "test-model"
            result = _run_l2(txt, "text", opts)

        assert result == "LLM generated text."
        mock_db.put_l2.assert_called_once()
        mock_embed.assert_called_once_with(l2_id)
