"""Case-insensitive substring search over indexed ``chunks.chunk_text``.

Used by ``mm grep`` as an additive search layer alongside regex; independent
of the semantic (vector) layer in :mod:`mm.semantic` and not gated by ``-s``.

Backed by :meth:`mm.store.db.MmDatabase.search_chunks_fts`, which runs a
single ``LIKE %q% COLLATE NOCASE`` query with ``kind``/``ext``/``uri`` filters
pushed into SQL. Returns at most ``limit`` rows.
"""

from __future__ import annotations

from typing import Any


def fts_search(
    query: str,
    *,
    uri: str | None = None,
    uri_prefix: str | None = None,
    limit: int = 5,
    kind: str | None = None,
    ext: str | None = None,
) -> list[dict[str, Any]]:
    """Search indexed chunks for *query* as a case-insensitive substring"""
    from mm.store.db import MmDatabase

    q = query.strip()
    if not q:
        return []

    rows = MmDatabase().search_chunks_fts(
        q, uri=uri, uri_prefix=uri_prefix, kind=kind, ext=ext, limit=limit
    )
    return [
        {
            "path": r["file_uri"],
            "index": r["chunk_idx"],
            "rank": 0.0,
            "match": r["chunk_text"],
            "snippet": None,
        }
        for r in rows
    ]
