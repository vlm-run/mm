"""Text embedding generation against an OpenAI-compatible endpoint."""

from __future__ import annotations

from typing import Any

from mm.decorators import retry

_EMBEDDINGS_PATH = "/embeddings"
_EMBEDDING_ATTEMPTS = 2


@retry(retries=_EMBEDDING_ATTEMPTS, delay=1, backoff=2)
def _request_embeddings(texts: list[str]) -> list[list[float]]:
    """POST *texts* to the embeddings endpoint and return the vectors."""
    import httpx

    from mm import __version__
    from mm.profile import EMBEDDING_BASE_URL, EMBEDDING_MODEL, gateway_api_key

    headers: dict[str, str] = {
        "User-Agent": f"mm-ctx/{__version__}",
        "Content-Type": "application/json",
    }
    if api_key := gateway_api_key():
        headers["Authorization"] = f"Bearer {api_key}"

    payload: dict[str, Any] = {
        "model": EMBEDDING_MODEL,
        "input": texts,
        "encoding_format": "float",
    }

    response = httpx.post(
        EMBEDDING_BASE_URL + _EMBEDDINGS_PATH,
        json=payload,
        headers=headers,
        timeout=300,
    )
    response.raise_for_status()
    data: list[dict[str, Any]] = response.json()["data"]
    return [list(item["embedding"]) for item in data]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of text strings and return one vector per string."""
    return _request_embeddings(texts)


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
