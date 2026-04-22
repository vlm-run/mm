"""Semantic search — check indexing status, index on demand, then KNN query.

Used by `mm grep` to automatically search inside binary files (images, video,
audio, documents) using vector similarity over the persisted chunks table.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

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
    """Index a single file via the accurate-mode pipeline.

    Returns the URI on success, or ``None`` on failure (missing file,
    extractor error, or embed failure). Accurate-mode extraction writes
    to the ``l2_results`` + ``chunks`` + ``chunks_vec`` tables as a
    side effect of ``_run_accurate``.
    """
    from mm.commands.cat import _CatOpts, _extract

    path = Path(uri)
    if not path.exists():
        return None

    opts = _CatOpts(
        n=None,
        output_dir=None,
        mode="accurate",
        no_cache=False,
        format="rich",
        encode_overrides={},
        generate_overrides={},
        pipelines={},
        verbose=False,
    )

    try:
        result = _extract(path, opts)
        if result and not result.startswith("["):
            return uri
        raise ValueError(f"Accurate extraction failed for {uri}: {result}")
    except Exception as e:
        from mm.display import console

        console.print(f"[red]Error indexing {uri}: {e}[/red]")
        return None


def index_missing(missing: list[str]) -> int:
    """Index up to *max_files* URIs in parallel. Returns count of successfully indexed files."""
    from mm.display import console
    from mm.encoders import _ensure_discovered

    _ensure_discovered()

    to_index = missing[:MAX_INDEX]
    if len(missing) > MAX_INDEX:
        console.print(
            f"[yellow]Note:[/yellow] Indexing {MAX_INDEX} of {len(missing)} unindexed files."
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


SEMANTIC_MAX_DISTANCE = 1.0


def search(
    query: str,
    *,
    uri: str | None = None,
    uri_prefix: str | None = None,
    limit=5,
    max_distance=SEMANTIC_MAX_DISTANCE,
    kind: str | None = None,
    ext: str | None = None,
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

    fetch_multiplier = 5 if (kind or ext) else 2
    raw = MmDatabase().search_similar(vectors[0], limit=limit * fetch_multiplier, where=where)
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

    if raw and not results:
        from mm.display import console

        closest = min(r.get("distance", float("inf")) for r in raw)
        console.print(
            f"[dim]Semantic search: {len(raw)} candidate(s) found but all exceeded "
            f"the distance cutoff ({max_distance}). Closest was {closest:.3f}.[/dim]"
        )

    if kind:
        from mm.utils import file_kind_with_code
        kinds = {k.strip() for k in kind.split(",")}
        results = [res for res in results if file_kind_with_code(Path(res["path"])) in kinds]
    if ext:
        exts = tuple(e.strip().lower() for e in ext.split(","))
        results = [res for res in results if res["path"].lower().endswith(exts)]
    results = sorted(results, key=lambda r: r["distance"])
    return results[:limit]


def handle_missing(
    uris: list[str],
    *,
    do_index: bool = False,
    cmd_hint: str | None = None,
    quiet: bool = False,
) -> bool:
    """Check indexing status, optionally index, and warn about missing files.

    Args:
        uris: File URIs to check.
        do_index: If True, index missing files (up to MAX_INDEX).
        cmd_hint: Command string to show the user for manual indexing.
        quiet: Suppress warning output (useful for structured output formats).

    Returns:
        True if at least some files are indexed (safe to search), False otherwise.
    """
    _, missing = check_indexed(uris)
    if not missing:
        return True

    if do_index:
        index_missing(missing)
        return True

    if not quiet:
        from mm.display import console

        console.print(
            f"[yellow]Warning:[/yellow] {len(missing)} of {len(uris)} files are not indexed."
        )
        if cmd_hint:
            console.print(f"[dim]To index missing files, run:[/dim]\n  [bold]{cmd_hint}[/bold]")

    return len(missing) < len(uris)


def build_hint_cmd(
    pattern: str,
    directory: Path,
    kind: str | None,
    ext: str | None,
    ignore_case: bool = False,
) -> str:
    """Reconstruct the user's grep command with ``-s --index`` appended."""
    parts = ["mm grep", f'"{pattern}"', str(directory)]
    if kind:
        parts.append(f"--kind {kind}")
    if ext:
        parts.append(f"--ext {ext}")
    if ignore_case:
        parts.append("--ignore-case")
    parts.append("-s --index")
    return " ".join(parts)


def grep_semantic(
    pattern: str,
    directory: Path,
    kind: str | None,
    ext: str | None,
    limit: int,
    stdin_paths: list[str] | None = None,
    no_ignore: bool = False,
    do_index: bool = False,
    quiet: bool = False,
    cmd_hint: str | None = None,
) -> list[dict]:
    """Semantic search via embeddings.

    Only considers binary files (image, video, audio, document) — text and
    code files are handled by the normal regex grep path.

    Warns the user about missing indexes via stderr. Returns a list of
    semantic match dicts (path, index, distance, match).
    """
    from mm.context import Context
    from mm.utils import file_kind, is_binary_content

    path = directory.resolve()
    is_file = path.is_file()

    if stdin_paths:
        all_uris = [str(Path(p).resolve()) for p in stdin_paths if Path(p).is_file()]
    elif is_file:
        all_uris = [str(path)]
    else:
        ctx = Context(directory, no_ignore=no_ignore)
        if kind:
            ctx = ctx.filter(kind=kind)
        if ext:
            ctx = ctx.filter(ext=ext)
        all_uris = [str(path / f.path) for f in ctx.files]

    uris = [u for u in all_uris if is_binary_content(kind=file_kind(u))]
    if not uris:
        return []

    # Reconcile DB → disk: drop indexed rows whose files no longer exist.
    from mm.store.utils import prune_missing

    if not is_file:
        prune_missing(prefix=str(path), disk_uris=set(all_uris))
    else:
        prune_missing(uris=[str(path)])

    has_indexed = handle_missing(
        uris,
        do_index=do_index,
        cmd_hint=cmd_hint,
        quiet=quiet,
    )
    if not has_indexed:
        return []

    if stdin_paths:
        results: list[dict] = []
        uri_prefixes = [str(Path(p).resolve()) for p in stdin_paths if not Path(p).is_file()]

        for uri_prefix in uri_prefixes:
            results.extend(
                search(
                    pattern,
                    uri_prefix=uri_prefix,
                    limit=limit,
                    kind=kind,
                    ext=ext,
                )
            )

        results.sort(key=lambda r: r["distance"])
        results = results[:limit]
    else:
        results = search(
            pattern,
            uri=str(path) if is_file else None,
            uri_prefix=str(path) if not is_file else None,
            limit=limit,
            kind=kind,
            ext=ext,
        )

    return results
