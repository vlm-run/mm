"""Integration tests — require a running inference server.

Run with: uv run pytest tests/python/test_integration.py -m integration -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

HEADERS = {"User-Agent": "mm-ctx/1.0"}


# ---------------------------------------------------------------------------
# Fixtures — generate minimal valid binaries on the fly
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def base_url():
    from mm.profile import DEFAULTS

    return DEFAULTS["base_url"]


@pytest.fixture(scope="session")
def tmp_session(tmp_path_factory):
    return tmp_path_factory.mktemp("integration")


@pytest.fixture(scope="session")
def png_file(tmp_session: Path) -> Path:
    """Minimal valid 1x1 red PNG (67 bytes)."""
    import struct
    import zlib

    def _chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1x1 RGB
    raw = zlib.compress(b"\x00\xff\x00\x00")  # filter=none, R=255 G=0 B=0
    p = tmp_session / "test.png"
    p.write_bytes(sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", raw) + _chunk(b"IEND", b""))
    return p


@pytest.fixture(scope="session")
def pdf_file(tmp_session: Path) -> Path:
    """Minimal valid single-page PDF with text."""
    content = (
        b"%PDF-1.0\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Contents 4 0 R/Resources<</Font<</F1<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>>>>>>>endobj\n"
        b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 100 700 Td (Hello World) Tj ET\nendstream\nendobj\n"
        b"xref\n0 5\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000306 00000 n \n"
        b"trailer<</Size 5/Root 1 0 R>>\nstartxref\n406\n%%EOF"
    )
    p = tmp_session / "test.pdf"
    p.write_bytes(content)
    return p


# ---------------------------------------------------------------------------
# Server health
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestServerHealth:
    def test_default_profile_reachable(self, base_url):
        """Verify the default profile's base_url is up."""
        import httpx

        resp = httpx.get(f"{base_url}/models", headers={**HEADERS}, timeout=5)
        assert resp.status_code == 200

    def test_l2_chat_completion(self, base_url):
        """Trivial L2 call — send a short prompt, get a response."""
        from mm.profile import DEFAULTS
        from openai import OpenAI

        client = OpenAI(
            base_url=base_url,
            api_key=DEFAULTS["api_key"],
            default_headers=HEADERS,
        )
        resp = client.chat.completions.create(
            model=DEFAULTS["model"],
            messages=[{"role": "user", "content": "Say hello in one word."}],
            max_tokens=10,
        )
        assert resp.choices[0].message.content
        assert len(resp.choices[0].message.content) > 0


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestEmbeddings:
    def test_embed_text(self):
        from mm.store.embed import embed_texts

        vecs = embed_texts(["What is machine learning?", "A cat on a mat."])
        assert len(vecs) == 2
        assert len(vecs[0]) > 0

    def test_embed_image(self, png_file: Path):
        from mm.store.embed import embed_parts, image_part

        vecs = embed_parts([image_part(png_file)])
        assert len(vecs) == 1
        assert len(vecs[0]) > 0

    def test_embed_document(self, pdf_file: Path):
        from mm.store.embed import document_part, embed_parts

        vecs = embed_parts([document_part(pdf_file)])
        assert len(vecs) == 1
        assert len(vecs[0]) > 0

    def test_embed_mixed_batch(self, png_file: Path):
        from mm.store.embed import embed_parts, image_part, text_part

        parts = [text_part("hello"), image_part(png_file)]
        vecs = embed_parts(parts)
        assert len(vecs) == 2


# ---------------------------------------------------------------------------
# End-to-end: L2 + chunk embedding
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestChunkEmbedding:
    def test_l2_store_and_embed(self, tmp_session: Path):
        """Write L2 content, chunk it, embed chunks, verify round-trip."""
        import pyarrow as pa
        from mm.store import MmDatabase
        from mm.store.embed import embed_file_chunks

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
        content = "Machine learning is transforming software engineering. " * 40
        db.put_l2("/test/integ/doc.txt", "h1", "default", "test-model", content)

        from unittest.mock import patch

        with patch("mm.store.db.MmDatabase", return_value=db):
            n = embed_file_chunks("/test/integ/doc.txt", "h1", "default", "test-model")
        assert n > 0

        full = db.get_full_content("/test/integ/doc.txt", "h1", "default", "test-model")
        assert full == content
