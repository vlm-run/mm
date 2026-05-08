"""Semantic search — check indexing status, index on demand, then KNN query.

Used by `mm grep` to automatically search inside binary files (images, video,
audio, documents) using vector similarity over the persisted chunks table.

A file is considered **indexed** only when all four stages have run:
processed → chunked → embedded → stored in the vector table. ``mm cat``
performs only the first two stages (it writes chunks but no embeddings);
``mm grep -s --pre-index`` completes the indexing (embed + vec store) for
already-chunked files and runs the full pipeline for previously
unprocessed ones.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mm.utils import batch_array

MAX_INDEX = 25
INDEX_TIMEOUT_S = 300


@dataclass
class IndexStatus:
    """
    Three-way classification of URIs against the chunks/vec tables
    """

    indexed: set[str] = field(default_factory=set)
    chunked_only: set[str] = field(default_factory=set)
    unprocessed: set[str] = field(default_factory=set)
    # Resume hints for chunked_only URIs.
    extraction_ids_by_uri: dict[str, list[str]] = field(default_factory=dict)
    text_hashes_by_uri: dict[str, str] = field(default_factory=dict)

    @property
    def missing(self) -> list[str]:
        """URIs not yet fully indexed (chunked-only ∪ unprocessed)."""
        return list(self.chunked_only) + list(self.unprocessed)


def check_index_status(uris: list[str]) -> IndexStatus:
    """
    Classify each URI as indexed, chunked_only, or unprocessed.

    *indexed*: at least one chunk row JOINs a ``chunks_vec`` entry.
    *chunked_only*: chunks present but no vector — needs embedding only.
    *unprocessed*: no chunks at all — needs the full pipeline.
    """
    status = IndexStatus()
    if not uris:
        return status

    from mm.store.db import MmDatabase

    db = MmDatabase()
    vec_exists = db._connect.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunks_vec'"
    ).fetchone()

    chunked: set[str] = set()
    for batch in batch_array(uris, 500):
        placeholders = ", ".join("?" * len(batch))
        rows = db._connect.execute(
            f"SELECT file_uri, extraction_id, content_hash FROM chunks "
            f"WHERE file_uri IN ({placeholders})",
            batch,
        ).fetchall()
        for uri, extraction_id, content_hash in rows:
            chunked.add(uri)
            if extraction_id:
                ids = status.extraction_ids_by_uri.setdefault(uri, [])
                if extraction_id not in ids:
                    ids.append(extraction_id)
            else:
                status.text_hashes_by_uri[uri] = content_hash

    indexed: set[str] = set()
    if vec_exists and chunked:
        chunked_list = list(chunked)
        for batch in batch_array(chunked_list, 500):
            placeholders = ", ".join("?" * len(batch))
            rows = db._connect.execute(
                f"SELECT DISTINCT c.file_uri FROM chunks c "
                f"JOIN chunks_vec v ON v.chunk_id = c.id "
                f"WHERE c.file_uri IN ({placeholders})",
                batch,
            ).fetchall()
            indexed.update(r[0] for r in rows)

    status.indexed = indexed
    status.chunked_only = chunked - indexed
    status.unprocessed = set(uris) - chunked
    return status


def _embed_chunked_only(
    uri: str,
    extraction_ids: list[str],
    text_hash: str | None,
) -> str | None:
    """Embed already-chunked content for *uri* without re-running extraction."""
    from mm.store.embed import embed_file_chunks_concurrent, embed_text_chunks_concurrent

    try:
        for eid in extraction_ids:
            embed_file_chunks_concurrent(eid, max_workers=4)
        if text_hash:
            embed_text_chunks_concurrent(text_hash, max_workers=4)
        return uri
    except Exception as e:
        from mm.display import console

        console.print(f"[red]Error embedding {uri}: {e}[/red]")
        return None


def _index_one(uri: str) -> str | None:
    """
    Run the full pipeline for an unprocessed *uri* in fast mode.
    """
    from mm.cat_utils.base_utils import CatOpts
    from mm.commands.cat import _extract

    path = Path(uri)
    if not path.exists():
        return None

    opts = CatOpts(
        n=None,
        output_dir=None,
        mode="fast",
        no_cache=False,
        format="rich",
        encode_overrides={},
        generate_overrides={},
        pipelines={},
        verbose=False,
    )

    try:
        result = _extract(path, opts)
        if not result or result.startswith("["):
            raise ValueError(f"Fast extraction failed for {uri}: {result}")
    except Exception as e:
        from mm.display import console

        console.print(f"[red]Error indexing {uri}: {e}[/red]")
        return None

    fresh = check_index_status([uri])
    return _embed_chunked_only(
        uri,
        fresh.extraction_ids_by_uri.get(uri, []),
        fresh.text_hashes_by_uri.get(uri),
    )


def index_missing(
    missing: list[str],
    *,
    status: IndexStatus | None = None,
) -> int:
    """
    Finish indexing for up to ``MAX_INDEX`` URIs in parallel.

    When *status* is supplied, chunked-only URIs take the embed-only
    fast path (no re-extraction). When *status* is ``None`` every URI is
    treated as unprocessed and run through ``_index_one``.
    """
    from mm.display import console
    from mm.encoders import _ensure_discovered

    _ensure_discovered()

    to_index = missing[:MAX_INDEX]
    total = len(to_index)
    if len(missing) > MAX_INDEX:
        console.print(
            f"[yellow]Note:[/yellow] {MAX_INDEX} of {len(missing)} unindexed files will be indexed."
        )
    console.print(
        f"[dim]Indexing {total} file{'s' if total != 1 else ''} "
        f"(timeout: {INDEX_TIMEOUT_S}s)...[/dim]"
    )

    chunked_only = status.chunked_only if status else set()
    extraction_ids_by_uri = status.extraction_ids_by_uri if status else {}
    text_hashes_by_uri = status.text_hashes_by_uri if status else {}

    def _dispatch(uri: str) -> str | None:
        if uri in chunked_only:
            return _embed_chunked_only(
                uri,
                extraction_ids_by_uri.get(uri, []),
                text_hashes_by_uri.get(uri),
            )
        return _index_one(uri)

    workers = min(4, total)
    successful = 0
    errored = 0
    completed = 0
    timed_out = False

    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {pool.submit(_dispatch, uri): uri for uri in to_index}
        try:
            for fut in as_completed(futures, timeout=INDEX_TIMEOUT_S):
                completed += 1
                if fut.result() is not None:
                    successful += 1
                    console.print(f"[dim]  {completed}/{total} done...[/dim]")
                else:
                    errored += 1
                    console.print(f"[dim]  {completed}/{total} errored...[/dim]")
        except TimeoutError:
            timed_out = True
            pending = [futures[f] for f in futures if not f.done()]
            console.print(
                f"[yellow]Warning:[/yellow] indexing hit the {INDEX_TIMEOUT_S}s timeout; "
                f"{len(pending)} file{'s' if len(pending) != 1 else ''} did not finish. "
                f"Continuing the search with {successful} indexed file"
                f"{'s' if successful != 1 else ''}."
            )
            for uri in pending:
                console.print(f"[dim]  skipped: {uri}[/dim]")
    finally:
        pool.shutdown(wait=not timed_out, cancel_futures=True)

    if not timed_out:
        suffix = f" [red]({errored} errored)[/red]" if errored else "."
        console.print(
            f"[green]Indexed {successful} file{'s' if successful != 1 else ''}[/green]{suffix}"
        )
    return successful


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
    """
    Embed query string and run KNN search, scoped by URI or prefix.
    """
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

    fetch_limit = max(limit * 10, 100) if (kind or ext) else limit * 2
    raw = MmDatabase().search_similar(vectors[0], limit=fetch_limit, where=where)
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
    """
    Check indexing status, optionally index, and warn about missing files.

    Args:
        uris: File URIs to check.
        do_index: If True, finish indexing missing files (up to MAX_INDEX).
        cmd_hint: Command string to show the user for manual indexing.
        quiet: Suppress warning output (useful for structured output formats).

    Returns:
        True if at least some files are indexed (safe to search), False otherwise.
    """
    status = check_index_status(uris)
    missing = status.missing
    if not missing:
        return True

    if do_index:
        index_missing(missing, status=status)
        return True

    if not quiet:
        from mm.display import console

        console.print(
            f"[yellow]Warning:[/yellow] {len(missing)} of {len(uris)} files "
            f"are not fully indexed — {len(missing)} missing."
        )
        if cmd_hint:
            console.print(f"[dim]To finish indexing, run:\n  [bold]{cmd_hint}[/bold][/dim]")

    return len(status.indexed) > 0


def build_hint_cmd(
    pattern: str,
    directory: Path,
    kind: str | None,
    ext: str | None,
    ignore_case: bool = False,
) -> str:
    """
    Reconstruct the user's grep command with ``-s --pre-index`` appended.
    """
    parts = ["mm grep", f'"{pattern}"', str(directory)]
    if kind:
        parts.append(f"--kind {kind}")
    if ext:
        parts.append(f"--ext {ext}")
    if ignore_case:
        parts.append("--ignore-case")
    parts.append("-s --pre-index")
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
    """
    Semantic search via embeddings
    """
    from mm.context import Context

    path = directory.resolve()
    is_file = path.is_file()

    if stdin_paths:
        uris = [str(Path(p).resolve()) for p in stdin_paths if Path(p).is_file()]
    elif is_file:
        uris = [str(path)]
    else:
        ctx = Context(directory, no_ignore=no_ignore)
        if kind:
            ctx = ctx.filter(kind=kind)
        if ext:
            ctx = ctx.filter(ext=ext)
        uris = [str(path / f.path) for f in ctx.files]

    if not uris:
        return []
    all_uris = uris

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
