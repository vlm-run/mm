"""Semantic search — ensure embeddings exist, then KNN query.

Used by `mm grep -l 2` to search inside files using vector similarity.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def ensure_indexed(uris: list[str]) -> None:
    """Ensure all URIs have embeddings in chunks_vec. Index missing ones via L2 pipeline."""
    if not uris:
        return

    from mm.store.db import MmDatabase

    db = MmDatabase()
    # Find which URIs already have embeddings
    vec_exists = db._connect.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunks_vec'"
    ).fetchone()

    indexed: set[str] = set()
    if vec_exists:
        placeholders = ", ".join("?" * len(uris))
        rows = db._connect.execute(
            f"SELECT DISTINCT c.uri FROM chunks c "
            f"JOIN chunks_vec v ON v.chunk_id = c.id "
            f"WHERE c.uri IN ({placeholders})",
            uris,
        ).fetchall()
        indexed = {r[0] for r in rows}

    missing = [u for u in uris if u not in indexed]
    if not missing:
        return

    # Run L2 extraction + embedding on each missing file
    from mm.commands.cat import _CatOpts, _file_kind, _l2_cached

    opts = _CatOpts(
        level=2,
        n=None,
        detail=False,
        output_dir=None,
        max_pages=None,
        mosaic_tile="4x4",
        mosaic_image_width=160,
        video_mosaic_count=1,
        video_mosaic_strategy="uniform",
        audio_speed=2.0,
        audio_sample_rate=16000,
        mode=None,
        no_cache=False,
        format="rich",
    )

    for uri in missing:
        path = Path(uri)
        if not path.exists():
            continue
        kind = _file_kind(path)
        try:
            _l2_cached(path, kind, opts)
        except Exception:
            continue


def search(
    query: str,
    *,
    uri: str | None = None,
    uri_prefix: str | None = None,
    limit=5,
    max_distance=1.0,
) -> list[dict[str, Any]]:
    """Embed query string and run KNN search, scoped by URI or prefix."""
    from mm.store.db import MmDatabase
    from mm.store.embed import embed_texts

    vectors = embed_texts([query])
    if not vectors or not vectors[0]:
        return []

    where = None
    if uri:
        where = f"c.uri = '{uri.replace(chr(39), chr(39) * 2)}'"
    elif uri_prefix:
        where = f"c.uri LIKE '{uri_prefix.replace(chr(39), chr(39) * 2)}%'"

    raw = MmDatabase().search_similar(vectors[0], limit=limit * 2, where=where)
    results = [
        {
            "path": r["uri"],
            "index": r["chunk_idx"],
            "distance": round(r["distance"], 4),
            "match": r["chunk_text"],
        }
        for r in raw
        if r.get("distance", float("inf")) <= max_distance
    ]

    seen: dict[str, dict[str, Any]] = {}
    for r in results:
        f = r["path"]
        if f not in seen or r["distance"] < seen[f]["distance"]:
            seen[f] = r
    results = sorted(seen.values(), key=lambda r: r["distance"])

    return results[:limit]
