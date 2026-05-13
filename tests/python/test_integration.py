"""Integration tests — require a running inference server.

!!IMPORTANT NOTE: Server calls are currently mocked so the suite can run offline.
Once the inference server is stable and available in CI, remove the
``_mock_servers`` fixture and let the tests hit real endpoints.  The
test logic itself should remain unchanged — only the fixture needs to
go away for this to become a true integration suite again.

Run with: uv run pytest tests/python/test_integration.py -m integration -v
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

HEADERS = {"User-Agent": "mm-ctx/1.0"}

# Fake embedding vector returned by mocked server
_FAKE_VECTOR = [0.1] * 1536


# ---------------------------------------------------------------------------
# Mock fixture — remove this to restore real server calls
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _mock_servers():
    """Mock all external server calls.

    TODO: Remove this fixture once the inference server is deployed and
    reachable from CI.  All test assertions are written against real API
    contracts so they will pass against a live server without changes.
    """
    # Mock httpx.get (used by test_default_profile_reachable)
    mock_get_resp = MagicMock(status_code=200)

    # Mock httpx.post (used by embed_parts)
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.raise_for_status = MagicMock()
    mock_post_resp.json.return_value = {"embeddings": [_FAKE_VECTOR]}

    def _fake_post(*args, json=None, **kwargs):
        """Return one vector per `input` in the gateway-shape response."""
        inputs = json.get("input") if isinstance(json, dict) else None
        n = len(inputs) if isinstance(inputs, list) else 1
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "object": "list",
            "data": [
                {"object": "embedding", "index": i, "embedding": _FAKE_VECTOR} for i in range(n)
            ],
        }
        return resp

    # Mock OpenAI chat completions (used by test_accurate_chat_completion)
    mock_choice = SimpleNamespace(message=SimpleNamespace(content="Hello"))
    mock_completion = SimpleNamespace(choices=[mock_choice])

    with (
        patch("httpx.get", return_value=mock_get_resp),
        patch("httpx.post", side_effect=_fake_post),
        patch(
            "openai.OpenAI",
            return_value=SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(create=MagicMock(return_value=mock_completion))
                )
            ),
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# Fixtures — generate minimal valid binaries on the fly
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def base_url():
    from mm.profile import DEFAULT_PROFILE, RESERVED_DEFAULTS

    return RESERVED_DEFAULTS[DEFAULT_PROFILE]["base_url"]


@pytest.fixture(scope="session")
def tmp_session(tmp_path_factory):
    return tmp_path_factory.mktemp("integration")


# ---------------------------------------------------------------------------
# Server health
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.integration
class TestServerHealth:
    def test_default_profile_reachable(self, base_url):
        """Verify the default profile's base_url is up."""
        import httpx

        resp = httpx.get(f"{base_url}/models", headers={**HEADERS}, timeout=5)
        assert resp.status_code == 200

    def test_accurate_chat_completion(self, base_url):
        """Trivial accurate-mode call — send a short prompt, get a response."""
        from mm.profile import DEFAULT_PROFILE, RESERVED_DEFAULTS
        from openai import OpenAI

        default_profile = RESERVED_DEFAULTS[DEFAULT_PROFILE]

        client = OpenAI(
            base_url=base_url,
            api_key=default_profile["api_key"],
            default_headers=HEADERS,
        )
        resp = client.chat.completions.create(
            model=default_profile["model"],
            messages=[{"role": "user", "content": "Say hello in one word."}],
            max_tokens=10,
        )
        assert resp.choices[0].message.content
        assert len(resp.choices[0].message.content) > 0


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.integration
class TestEmbeddings:
    def test_embed_text(self):
        from mm.store.embed import embed_texts

        vecs = embed_texts(["What is machine learning?", "A cat on a mat."])
        assert vecs is not None
        assert len(vecs) == 2
        assert len(vecs[0]) > 0


# ---------------------------------------------------------------------------
# End-to-end: accurate result + chunk embedding
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.integration
class TestChunkEmbedding:
    def test_accurate_store_and_embed(self, tmp_session: Path):
        """Write accurate content, chunk it, embed chunks, verify round-trip."""
        import pyarrow as pa
        from mm.store import MmDatabase
        from mm.store.embed import embed_file_chunks
        from mm.store.schema import FileCol

        db = MmDatabase(db_path=tmp_session / "integ.db")
        table = pa.table(
            {
                "path": ["doc.txt"],
                "name": ["doc.txt"],
                "stem": ["doc"],
                "ext": [".txt"],
                "size": pa.array([100], type=pa.uint64()),
                "modified": pa.array([1712000000000000], type=pa.timestamp("us")),
                "created": pa.array([1712000000000000], type=pa.timestamp("us")),
                "mime": ["text/plain"],
                "kind": ["text"],
                "is_binary": [False],
                "depth": pa.array([0], type=pa.uint16()),
                "parent": [""],
                "width": pa.array([None], type=pa.uint32()),
                "height": pa.array([None], type=pa.uint32()),
            }
        )
        root = Path("/test/integ")
        db.upsert_files(table, root)

        uri = "/test/integ/doc.txt"
        db.put_file_content(
            uri,
            {
                FileCol.CONTENT_HASH: "h1",
                FileCol.TEXT_PREVIEW: "fast content",
            },
        )

        content = "Machine learning is transforming software engineering. " * 40
        extraction_id = db.put_extraction(uri, "h1", "default", "test-model", content)
        with patch("mm.store.db.MmDatabase", return_value=db):
            n = embed_file_chunks(extraction_id)
        assert n > 0

        full = db.get_full_content(uri, "h1", "default", "test-model")
        assert full == content
