"""Semantic search — check indexing status, index on demand, then KNN query.

Used by `mm grep -l 2` to search inside files using vector similarity.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import typer

from mm.utils import batch_array

MAX_INDEX = 50


def check_indexed(uris: list[str]) -> tuple[set[str], list[str]]:
    """Return (indexed_set, missing_list) for the given URIs."""
    if not uris:
        return set(), []

    from mm.store.db import MmDatabase

    db = MmDatabase()
    vec_exists = db._connect.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunks_vec'"
    ).fetchone()

    indexed: set[str] = set()
    if vec_exists:
        rows_items = []
        for batch in batch_array(uris, 500):
            placeholders = ", ".join("?" * len(batch))
            rows = db._connect.execute(
                f"SELECT DISTINCT c.file_uri FROM chunks c "
                f"JOIN chunks_vec v ON v.chunk_id = c.id "
                f"WHERE c.file_uri IN ({placeholders})",
                batch,
            ).fetchall()
            rows_items.extend(rows)
        indexed = {r[0] for r in rows_items}

    missing = [u for u in uris if u not in indexed]
    return indexed, missing


def _index_one(uri: str) -> str | None:
    """Index a single file via L2 pipeline. Returns URI on success, None on failure."""
    from mm.commands.cat import _CatOpts, _file_kind, _run_l2

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

    path = Path(uri)
    if not path.exists():
        return None
    try:
        result = _run_l2(path, _file_kind(path), opts)
        if not result.startswith("["):
            return uri
        raise ValueError(f"Failed to extract L2 for {uri}: {result}")
    except Exception as e:
        from mm.display import console

        console.print(f"[red]Error indexing {uri}: {e}[/red]")
        return None


def index_missing(missing: list[str], *, max_files: int = MAX_INDEX) -> int:
    """Index up to *max_files* URIs in parallel. Returns count of successfully indexed files."""
    from mm.display import console

    to_index = missing[:max_files]
    if len(missing) > max_files:
        console.print(
            f"[yellow]Note:[/yellow] Indexing {max_files} of {len(missing)} unindexed files."
        )
    else:
        console.print(
            f"[dim]Indexing {len(to_index)} file{'s' if len(to_index) != 1 else ''}...[/dim]"
        )

    workers = min(4, len(to_index))
    indexed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_index_one, uri): uri for uri in to_index}
        for fut in as_completed(futures):
            if fut.result() is not None:
                indexed += 1

    console.print(f"[green]Indexed {indexed} file{'s' if indexed != 1 else ''}.[/green]")
    return indexed


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
        where = f"c.file_uri = '{uri.replace(chr(39), chr(39) * 2)}'"
    elif uri_prefix:
        where = f"c.file_uri LIKE '{uri_prefix.replace(chr(39), chr(39) * 2)}%'"

    raw = MmDatabase().search_similar(vectors[0], limit=limit * 2, where=where)
    results = [
        {
            "path": r["file_uri"],
            "index": r["chunk_idx"],
            "distance": round(r["distance"], 4),
            "match": r["chunk_text"],
        }
        for r in raw
        if r.get("distance", float("inf")) <= max_distance
    ]
    results = sorted(results, key=lambda r: r["distance"])
    return results[:limit]


def handle_missing(
    uris: list[str],
    pattern: str,
    directory: Path,
    kind: str | None,
    ext: str | None,
    do_index=False,
):
    """Handle missing indexed files: optionally index, or show instructions to the user."""
    from mm.semantic import check_indexed, index_missing

    indexed, missing = check_indexed(uris)
    if not missing:
        return

    if missing and do_index:
        index_missing(missing, max_files=50)
        return

    from mm.display import console

    # Build the equivalent command for the user to copy
    cmd_parts = ["mm grep"]
    cmd_parts.append(f'"{pattern}"')
    cmd_parts.append(str(directory))
    if kind:
        cmd_parts.append(f"--kind {kind}")
    if ext:
        cmd_parts.append(f"--ext {ext}")
    cmd_parts.append("-l 2 --index")

    console.print(f"[yellow]Warning:[/yellow] {len(missing)} of {len(uris)} files are not indexed.")
    if not indexed:
        console.print(
            f"[dim]No indexed files found. Index them first:[/dim]\n"
            f"  [bold]{' '.join(cmd_parts)}[/bold]"
        )
        raise typer.Exit(1)
    console.print(f"[dim]To index missing files, run:[/dim]\n  [bold]{' '.join(cmd_parts)}[/bold]")
