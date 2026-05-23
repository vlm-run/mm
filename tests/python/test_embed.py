"""Tests for mm.store.embed — embedding generation workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from mm.store import MmDatabase
from mm.store.embed import (
    _EMBEDDINGS_PATH,
    embed_file_chunks,
    embed_texts,
)

from .conftest import requires_sqlite_vec
from .test_utils import ensure_fast, get_hash

FAKE_DIM = 4


def _mock_embeddings_response(n: int) -> dict[str, Any]:
    """Return an OpenAI-style embeddings response with *n* fake vectors."""
    return {
        "data": [
            {"index": i, "embedding": [float(i + 1)] * FAKE_DIM, "object": "embedding"}
            for i in range(n)
        ],
        "model": "qwen/qwen3-vl-embedding-2b",
        "object": "list",
    }


@pytest.fixture()
def mock_server():
    """Patch httpx.post to simulate the OpenAI-compatible embeddings endpoint."""

    def _fake_post(url: str, **kwargs: Any) -> MagicMock:
        assert url.endswith(_EMBEDDINGS_PATH)
        payload = kwargs.get("json", {})
        inputs = payload.get("input", [])
        assert payload.get("model")
        assert payload.get("encoding_format") == "float"

        headers = kwargs.get("headers", {})
        assert headers.get("User-Agent", "").startswith("mm-ctx/")
        assert headers.get("Content-Type") == "application/json"

        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = _mock_embeddings_response(len(inputs))
        return resp

    with patch("httpx.post", side_effect=_fake_post) as mock:
        yield mock


@pytest.fixture()
def db(tmp_path: Path) -> MmDatabase:
    return MmDatabase(db_path=tmp_path / "test.db")


class TestEmbedTexts:
    def test_embed_texts_returns_one_vector_per_input(self, mock_server: MagicMock):
        vectors = embed_texts(["hello", "world", "test"])
        assert len(vectors) == 3
        assert all(len(v) == FAKE_DIM for v in vectors)
        mock_server.assert_called_once()

    def test_embed_texts_url(self, mock_server: MagicMock):
        embed_texts(["test"])
        url = mock_server.call_args[0][0]
        assert url.endswith(_EMBEDDINGS_PATH)

    def test_embed_texts_default_url_is_gateway_openai(self, mock_server: MagicMock):
        """Default embeddings URL must be the gateway's OpenAI-compatible route.

        The gateway exposes embeddings at ``/v1/openai/embeddings``; a plain
        ``/v1/embeddings`` path returns 404. See ``mm.profile.GATEWAY_BASE_URL``.
        """
        from mm.profile import EMBEDDING_BASE_URL

        assert EMBEDDING_BASE_URL == "https://gateway.vlm.run/v1/openai"
        embed_texts(["test"])
        url = mock_server.call_args[0][0]
        assert url == "https://gateway.vlm.run/v1/openai/embeddings"

    def test_embed_texts_user_agent(self, mock_server: MagicMock):
        embed_texts(["test"])
        headers = mock_server.call_args[1].get("headers", {})
        assert headers["User-Agent"].startswith("mm-ctx/")

    def test_authorization_header_when_gateway_key_set(self, mock_server: MagicMock):
        with patch("mm.profile.gateway_api_key", return_value="test-key"):
            embed_texts(["test"])
        headers = mock_server.call_args[1].get("headers", {})
        assert headers.get("Authorization") == "Bearer test-key"

    def test_no_authorization_header_when_gateway_key_empty(self, mock_server: MagicMock):
        with patch("mm.profile.gateway_api_key", return_value=""):
            embed_texts(["test"])
        headers = mock_server.call_args[1].get("headers", {})
        assert "Authorization" not in headers

    def test_embed_texts_retries_once(self):
        import httpx

        success = MagicMock()
        success.raise_for_status = MagicMock()
        success.json.return_value = _mock_embeddings_response(1)

        with patch(
            "httpx.post", side_effect=[httpx.ConnectError("temporary"), success]
        ) as mock_post:
            vectors = embed_texts(["retry"])

        assert len(vectors) == 1
        assert mock_post.call_count == 2


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
            dry_run=False,
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
