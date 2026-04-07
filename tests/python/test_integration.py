"""Integration tests — require a running inference server and sample_files/.

Run with: uv run pytest tests/test_integration.py -m integration -v
"""

from pathlib import Path

import pytest

SAMPLE = Path("sample_files")

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Server health
# ---------------------------------------------------------------------------


class TestServerHealth:
    def test_default_profile_reachable(self):
        """Verify the default profile's base_url is up."""
        import httpx

        from mm.profile import get_profile

        profile = get_profile()
        resp = httpx.get(f"{profile.base_url}/models", timeout=5)
        assert resp.status_code == 200

    def test_l2_chat_completion(self):
        """Trivial L2 call — send a short prompt, get a response."""
        from openai import OpenAI

        from mm.profile import get_profile

        profile = get_profile()
        client = OpenAI(base_url=profile.base_url, api_key=profile.api_key or "none")
        resp = client.chat.completions.create(
            model=profile.model,
            messages=[{"role": "user", "content": "Say hello in one word."}],
            max_tokens=10,
        )
        assert resp.choices[0].message.content
        assert len(resp.choices[0].message.content) > 0


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


class TestEmbeddings:
    def test_embed_text(self):
        from mm.store.embed import embed_texts

        vecs = embed_texts(["What is machine learning?", "A cat on a mat."])
        assert len(vecs) == 2
        assert len(vecs[0]) > 0

    def test_embed_image(self):
        from mm.store.embed import embed_parts, image_part

        img = SAMPLE / "image.png"
        pytest.importorskip("google.genai")
        if not img.exists():
            pytest.skip("sample_files/image.png not found")
        vecs = embed_parts([image_part(img)])
        assert len(vecs) == 1
        assert len(vecs[0]) > 0

    def test_embed_audio(self):
        from mm.store.embed import audio_parts, embed_parts

        audio = SAMPLE / "audio.mp3"
        if not audio.exists():
            pytest.skip("sample_files/audio.mp3 not found")
        parts = audio_parts(audio)
        vecs = embed_parts(parts)
        assert len(vecs) == len(parts)
        assert len(vecs[0]) > 0

    def test_embed_document(self):
        from mm.store.embed import document_part, embed_parts

        pdf = SAMPLE / "document.pdf"
        if not pdf.exists():
            pytest.skip("sample_files/document.pdf not found")
        vecs = embed_parts([document_part(pdf)])
        assert len(vecs) == 1
        assert len(vecs[0]) > 0

    def test_embed_video(self):
        from mm.store.embed import embed_parts, video_parts

        vid = SAMPLE / "video.mp4"
        if not vid.exists():
            pytest.skip("sample_files/video.mp4 not found")
        vecs = embed_parts(video_parts(vid))
        assert len(vecs) > 0
        assert len(vecs[0]) > 0

    def test_embed_mixed_batch(self):
        from mm.store.embed import embed_parts, image_part, text_part

        img = SAMPLE / "image.png"
        if not img.exists():
            pytest.skip("sample_files/image.png not found")
        parts = [text_part("hello"), image_part(img)]
        vecs = embed_parts(parts)
        assert len(vecs) == 2


# ---------------------------------------------------------------------------
# End-to-end: L2 + chunk embedding
# ---------------------------------------------------------------------------


class TestChunkEmbedding:
    def test_embed_file_chunks(self):
        from mm.store import MmDatabase
        from mm.store.embed import embed_file_chunks

        db = MmDatabase()
        conn = db._connect
        row = conn.execute("SELECT COUNT(*) FROM l2_results").fetchone()
        if row[0] == 0:
            pytest.skip("No L2 results in DB. Run: mm cat sample_files/document.txt -l 2")
        r = conn.execute(
            "SELECT uri, content_hash, profile, model FROM l2_results LIMIT 1"
        ).fetchone()
        uri, content_hash, profile, model = r
        n = embed_file_chunks(uri, content_hash, profile, model)
        assert n > 0

    def test_db_state(self):
        from mm.store import MmDatabase

        db = MmDatabase()
        conn = db._connect
        l2_count = conn.execute("SELECT COUNT(*) FROM l2_results").fetchone()[0]
        chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        embedded = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE embed_model IS NOT NULL"
        ).fetchone()[0]
        # Just verify we can read the counts without error
        assert l2_count >= 0
        assert chunk_count >= 0
        assert embedded >= 0
