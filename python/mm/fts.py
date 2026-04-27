"""FTS5 token search over indexed ``chunks.chunk_text``.

Used by ``mm grep`` as an additive search layer alongside regex; independent
of the semantic (vector) layer in :mod:`mm.semantic` and not gated by ``-s``.
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
    """Run an FTS5 phrase query over indexed chunks.

    Strips regex metacharacters from ``query`` and runs a phrase match.
    ``kind`` and ``ext`` are pushed into SQL by ``MmDatabase.search_fts``,
    so ``limit`` rows come back already filtered. Returns an empty list when
    the pattern has no usable tokens or the FTS table is unavailable.
    """
    import re as _re

    from mm.store.db import MmDatabase

    tokens = _re.findall(r"\w+", query)
    if not tokens:
        return []
    fts_query = '"' + " ".join(tokens) + '"'

    raw = MmDatabase().search_fts(
        fts_query,
        uri=uri,
        uri_prefix=uri_prefix,
        kind=kind,
        ext=ext,
        limit=limit,
    )
    return [
        {
            "path": r["file_uri"],
            "index": r["chunk_idx"],
            "rank": round(r["rank"], 4),
            "match": r["chunk_text"],
            "snippet": r["snippet"],
        }
        for r in raw
    ]
