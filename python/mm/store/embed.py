"""Embedding generation for mm via the mm inference server.

The server at /embeddings accepts google.genai Part dicts and returns vectors.
This avoids leaking API keys into the CLI.

Supported content types:
  - Text: any string
  - Image: PNG, JPEG (max 6 per request)
  - Audio: MP3, WAV (max 80s)
  - Video: MP4, MOV (max 120s — longer videos are chunked)
  - Document: PDF (max 6 pages)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mm.decorators import retry
from mm.deps import try_import_or_raise

_VIDEO_MAX_SECONDS = 120
_VIDEO_OVERLAP_SECONDS = 10
_AUDIO_MAX_SECONDS = 80
_AUDIO_OVERLAP_SECONDS = 5
_EMBEDDINGS_PATH = "/embeddings"
_EMBEDDING_ATTEMPTS = 2


def import_genai_types():
    """Lazy-load ``google.genai.types``, raising if the gemini extra is missing."""
    return try_import_or_raise("google.genai.types", extra="gemini", package="google-genai")


def text_part(text: str) -> dict[str, Any]:
    """Construct a text Part."""
    types = import_genai_types()
    return types.Part(text=text).to_json_dict()


def image_part(path: Path) -> dict[str, Any]:
    """Construct an image Part from a file path."""
    types = import_genai_types()
    return types.Part.from_bytes(
        data=path.read_bytes(),
        mime_type=_mime_for(path, fallback="image/png"),
    ).to_json_dict()


def _audio_part(path: Path) -> dict[str, Any]:
    """Construct an audio Part from a file path (max 80s)."""
    types = import_genai_types()
    return types.Part.from_bytes(
        data=path.read_bytes(),
        mime_type=_mime_for(path, fallback="audio/mpeg"),
    ).to_json_dict()


def audio_parts(path: Path) -> list[dict[str, Any]]:
    """Chunk audio into overlapping segments and return Parts."""
    from mm.video import extract_segment, probe

    duration_s = probe(path).duration
    if duration_s <= _AUDIO_MAX_SECONDS:
        return [_audio_part(path)]

    import tempfile

    parts: list[dict[str, Any]] = []
    step = _AUDIO_MAX_SECONDS - _AUDIO_OVERLAP_SECONDS
    start = 0.0
    while start < duration_s:
        end = min(start + _AUDIO_MAX_SECONDS, duration_s)
        with tempfile.NamedTemporaryFile(suffix=path.suffix, delete=False) as tmp:
            seg_path = Path(tmp.name)
        extract_segment(path, seg_path, start, end)
        parts.append(_audio_part(seg_path))
        seg_path.unlink(missing_ok=True)
        start += step
    return parts


def document_part(path: Path) -> dict[str, Any]:
    """Construct a document Part from a PDF (max 6 pages)."""
    types = import_genai_types()
    return types.Part.from_bytes(
        data=path.read_bytes(),
        mime_type="application/pdf",
    ).to_json_dict()


def _video_part(path: Path) -> dict[str, Any]:
    """Construct a video Part from a file (max 120s)."""
    types = import_genai_types()
    return types.Part.from_bytes(
        data=path.read_bytes(),
        mime_type=_mime_for(path, fallback="video/mp4"),
    ).to_json_dict()


def video_parts(path: Path) -> list[dict[str, Any]]:
    """Chunk a video into overlapping segments and return Parts."""
    from mm.video import extract_segment, probe

    duration_s = probe(path).duration
    if duration_s <= _VIDEO_MAX_SECONDS:
        return [_video_part(path)]

    import tempfile

    parts: list[dict[str, Any]] = []
    step = _VIDEO_MAX_SECONDS - _VIDEO_OVERLAP_SECONDS
    start = 0.0

    while start < duration_s:
        end = min(start + _VIDEO_MAX_SECONDS, duration_s)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            seg_path = Path(tmp.name)
        extract_segment(path, seg_path, start, end)

        parts.append(_video_part(seg_path))
        seg_path.unlink(missing_ok=True)
        start += step

    return parts


@retry(retries=_EMBEDDING_ATTEMPTS, delay=1, backoff=2)
def _request_embeddings(parts: list[dict[str, Any]]) -> list[list[float]]:
    """Send Parts to the embedding server and return vectors."""
    import httpx

    from mm import __version__
    from mm.profile import GATEWAY_BASE_URL

    url = GATEWAY_BASE_URL + _EMBEDDINGS_PATH
    response = httpx.post(
        url,
        json=parts,
        headers={"User-Agent": f"mm-ctx/{__version__}", "Content-Type": "application/json"},
        timeout=300,
    )
    response.raise_for_status()
    result: list[list[float]] = response.json()["embeddings"]
    return result


def embed_parts(parts: list[dict[str, Any]]) -> list[list[float]]:
    """Embed Parts via the server, retrying transient request failures once."""
    return _request_embeddings(parts)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of text strings via the server."""
    return embed_parts([text_part(t) for t in texts])


def embed_file_chunks(extraction_id: str) -> int:
    """Embed all chunks for a file's extraction. Returns number of chunks embedded."""
    from mm.store.utils import shared_db

    db = shared_db()
    chunks = db.get_chunks(extraction_id)
    if not chunks:
        return 0

    texts = [c["chunk_text"] for c in chunks]
    vectors = embed_texts(texts)
    db.upsert_embeddings(extraction_id=extraction_id, vectors=vectors)
    return len(vectors)


def _parallel_embed_texts(texts: list[str], *, max_workers: int) -> list[list[float]]:
    """Split *texts* across a thread pool; concatenate the per-batch vectors."""
    from concurrent.futures import ThreadPoolExecutor
    from math import ceil

    n = len(texts)
    workers = max(1, min(max_workers, n))
    if workers == 1:
        return embed_texts(texts)
    batch = ceil(n / workers)
    groups = [texts[i : i + batch] for i in range(0, n, batch)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(embed_texts, groups))
    return [v for r in results for v in r]


def embed_file_chunks_concurrent(extraction_id: str, *, max_workers: int = 4) -> int:
    """Embed an extraction's chunks via a threadpool. Returns vector count."""
    from mm.store.utils import shared_db

    db = shared_db()
    chunks = db.get_chunks(extraction_id)
    if not chunks:
        return 0

    texts = [c["chunk_text"] for c in chunks]
    vectors = _parallel_embed_texts(texts, max_workers=max_workers)
    db.upsert_embeddings(extraction_id=extraction_id, vectors=vectors)
    return len(vectors)


def embed_text_chunks_concurrent(content_hash: str, *, max_workers: int = 4) -> int:
    """Embed FK-orphan text chunks via a thread pool.

    These chunks have no parent extraction (see ``put_text_chunks``),
    so they're looked up by ``content_hash`` and vectors upserted by
    explicit chunk_id list. Returns the number of vectors written.
    """
    from mm.store.utils import shared_db

    db = shared_db()
    chunks = db.get_text_chunks(content_hash)
    if not chunks:
        return 0

    texts = [c["chunk_text"] for c in chunks]
    chunk_ids = [c["id"] for c in chunks]
    vectors = _parallel_embed_texts(texts, max_workers=max_workers)
    db.upsert_embeddings(chunk_ids=chunk_ids, vectors=vectors)
    return len(vectors)


def _mime_for(path: Path, fallback: str) -> str:
    """Return the MIME type for *path*, falling back to *fallback*."""
    from mm.constants import guess_mime

    return guess_mime(path.name, fallback=fallback)
