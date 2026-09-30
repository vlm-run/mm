"""mm sql -- query file metadata, extractions, and chunks with SQL."""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

from mm.utils import Format

_STORED_TABLES = {"extractions", "chunks", "chunks_vec"}
_RICH_COLUMNS = {
    "name",
    "kind",
    "ext",
    "size",
    "parent",
    "mime",
    "width",
    "height",
    "modified",
    "depth",
}


def sql_cmd(
    query: Annotated[
        Optional[str],
        typer.Argument(help="SQL query (use 'files', 'extractions', or 'chunks' as table name)"),
    ] = None,
    directory: Annotated[Path, typer.Option("--dir", "-d", help="Directory to index")] = Path("."),
    format: Annotated[
        Optional[Format],
        typer.Option(
            "--format", "-f", help="Output format: json, tsv, csv, dataset-jsonl, dataset-hf"
        ),
    ] = None,
    list_tables: Annotated[
        bool, typer.Option("--list-tables", help="List available tables")
    ] = False,
    pre_index: Annotated[
        bool,
        typer.Option(
            "--pre-index",
            help="Index unindexed files (metadata) before querying the files table",
        ),
    ] = False,
) -> None:
    """Query file metadata, extractions, and chunks with SQL.

    \b
    Tables:
      files        — file metadata + locally extracted content (scanned from --dir, or persistent store)
      extractions  — fast/accurate extraction outputs (stored in SQLite)
      chunks       — chunked content + embeddings (stored in SQLite)

    \b
    Examples:
      mm sql "SELECT kind, COUNT(*) as n FROM files GROUP BY kind"
      mm sql "SELECT * FROM files WHERE kind='image'" --dir ~/photos
      mm sql "SELECT file_uri, summary FROM extractions LIMIT 10"
      mm sql "SELECT file_uri, chunk_idx, LENGTH(chunk_text) FROM chunks"
      mm sql --list-tables
    """
    from mm.display import resolve_format

    fmt = resolve_format(format.value if format else None)
    if list_tables:
        _list_tables(fmt)
        return

    if query is None:
        raise typer.BadParameter("Provide a SQL query or use --list-tables")

    table_name = _detect_table(query)
    if _introspecting(query) or table_name != "files":
        _query_stored(query, fmt)
    else:
        _query_files(query, directory, fmt, pre_index=pre_index)


def _introspecting(query: str):
    return re.match(r"\s*PRAGMA\b", query, re.IGNORECASE)


def _detect_table(query: str) -> str:
    for match in re.finditer(r"\bFROM\s+(\w+)", query, re.IGNORECASE):
        name = match.group(1).lower()
        if name in _STORED_TABLES:
            return name
    # Also check JOIN clauses
    for match in re.finditer(r"\bJOIN\s+(\w+)", query, re.IGNORECASE):
        name = match.group(1).lower()
        if name in _STORED_TABLES:
            return name
    return "files"


def _query_stored(query: str, fmt: str) -> None:
    """Query persistent SQLite tables (extractions, chunks)."""
    from mm.store.db import MmDatabase

    columns, rows = MmDatabase().sql(query)
    _emit(columns, rows, fmt)


def _query_files(query: str, directory: Path, fmt: str, *, pre_index: bool = False) -> None:
    """Query the files table from the persistent DB. Show diff of unindexed files."""
    from mm.context import Context
    from mm.store.db import MmDatabase

    resolved = directory.resolve()
    prefix = str(resolved)
    ctx = Context(directory)
    if pre_index:
        ctx.save()

    db = MmDatabase()

    # Reconcile: drop rows under *prefix* whose files no longer exist on disk.
    # Uses the directory walk as a hint so only stale candidates get stat'd.
    from mm.store.utils import prune_missing

    disk_uris = {str(resolved / f.path) for f in ctx.files}
    prune_missing(prefix=prefix, disk_uris=disk_uris, db=db)

    # Query indexed files scoped to this directory from the persistent store
    safe_prefix = prefix.replace("'", "''")
    indexed_rows = db.get_files(where=f"uri LIKE '{safe_prefix}/%'")

    if indexed_rows:
        # Load indexed rows into an in-memory SQLite table and run the user's query
        columns, rows = _query_dicts_as_files(indexed_rows, query)
        if fmt == "rich" and len(columns) > len(_RICH_COLUMNS):
            columns, rows = _trim_columns(columns, rows)
        _emit(columns, rows, fmt)
    else:
        from mm.display import console

        _emit([], [], fmt)
        console.print("\n[bold]No indexed files[/bold]\n---")

    # Compute diff: files on disk but not in DB (when NOT pre-indexing)
    if not pre_index:
        db_uris_rows = db._connect.execute(
            "SELECT uri FROM files WHERE uri LIKE ?", (f"{prefix}/%",)
        ).fetchall()

        db_uris = {r[0] for r in db_uris_rows}
        if unindexed := sorted(disk_uris - db_uris):
            _show_unindexed_diff(unindexed, prefix, query, directory)


def _trim_columns(columns: list[str], rows: list[tuple]) -> tuple[list[str], list[tuple]]:
    keep = [i for i, c in enumerate(columns) if c in _RICH_COLUMNS]
    new_columns = [columns[i] for i in keep]
    new_rows = [tuple(row[i] for i in keep) for row in rows]
    return new_columns, new_rows


def _show_unindexed_diff(unindexed: list[str], prefix: str, query: str, directory: Path) -> None:
    """Print the diff of unindexed files as a Rich table to stderr."""
    from rich import box
    from rich.table import Table

    from mm.display import console

    diff_table = Table(
        title=f"{len(unindexed)} unindexed file{'s' if len(unindexed) != 1 else ''}",
        box=box.ROUNDED,
        header_style="dim",
        title_style="dim",
        title_justify="left",
        style="dim",
    )
    diff_table.add_column("path", overflow="fold", style="dim")
    for uri in unindexed[:5]:
        rel = uri[len(prefix) + 1 :] if uri.startswith(prefix) else uri
        diff_table.add_row(rel)
    if len(unindexed) > 5:
        diff_table.add_row(f"... and {len(unindexed) - 5} more")
    console.print()
    console.print(diff_table)

    cmd = f'mm sql "{query}" --dir {directory} --pre-index'
    console.print(f"[dim]To include these files, run:  {cmd}[/dim]")


def _query_dicts_as_files(rows: list[dict[str, Any]], query: str) -> tuple[list[str], list[tuple]]:
    """Load dict rows into an in-memory SQLite 'files' table and execute query."""
    import sqlite3

    db = sqlite3.connect(":memory:")
    if not rows:
        return [], []

    # Infer columns from first row; use INTEGER affinity for numeric columns
    _INT_COLS = {
        "size",
        "width",
        "height",
        "depth",
        "is_binary",
        "line_count",
        "word_count",
        "pages",
        "has_audio",
        "indexed_at",
        "content_indexed_at",
    }
    _REAL_COLS = {"modified", "created", "duration_s", "fps"}
    all_cols = list(rows[0].keys())

    def _col_type(c: str) -> str:
        if c in _INT_COLS:
            return "INTEGER"
        if c in _REAL_COLS:
            return "REAL"
        return "TEXT"

    col_defs = ", ".join(f'"{c}" {_col_type(c)}' for c in all_cols)
    db.execute(f"CREATE TABLE files ({col_defs})")

    placeholders = ", ".join("?" * len(all_cols))
    db.executemany(
        f"INSERT INTO files VALUES ({placeholders})",
        [
            tuple(str(r.get(c, "")) if r.get(c) is not None else None for c in all_cols)
            for r in rows
        ],
    )

    cursor = db.execute(query)
    columns = [desc[0] for desc in cursor.description] if cursor.description else []
    result_rows = cursor.fetchall()
    db.close()
    return columns, result_rows


def _list_tables(fmt: str) -> None:
    from mm.store.db import MmDatabase

    db = MmDatabase()
    counts = {}
    for name in ("extractions", "chunks"):
        row = db._connect.execute(f"SELECT COUNT(*) FROM {name}").fetchone()
        counts[name] = row[0] if row else 0

    rows = [
        {"table": "files", "source": "scan + SQLite", "stored": "ephemeral"},
    ]
    for name in ("extractions", "chunks"):
        n = counts.get(name, 0)
        rows.append(
            {
                "table": name,
                "source": "SQLite",
                "stored": f"{n} rows" if n else "empty",
            }
        )

    if fmt in ("json", "dataset-jsonl", "dataset-hf"):
        from mm.display import emit_rows

        emit_rows(fmt, rows)
    elif fmt in ("tsv", "csv"):
        sep = "\t" if fmt == "tsv" else ","
        print(sep.join(rows[0].keys()))
        for r in rows:
            print(sep.join(str(v) for v in r.values()))
    else:
        from rich import box
        from rich.table import Table

        from mm.display import output_console

        t = Table(
            title="[bold]Available tables[/bold]",
            box=box.ROUNDED,
            header_style="bold",
        )
        t.add_column("table")
        t.add_column("source")
        t.add_column("stored", justify="right")
        for r in rows:
            t.add_row(r["table"], r["source"], r["stored"])
        output_console.print(t)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _to_tsv(columns: list[str], rows: list[tuple]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter="\t")
    writer.writerow(columns)
    for row in rows:
        writer.writerow(str(v) for v in row)
    return buf.getvalue()


def _parse_tsv(tsv: str) -> tuple[list[str], list[list[str]]]:
    reader = csv.reader(io.StringIO(tsv), delimiter="\t")
    headers = next(reader)
    rows = list(reader)
    return headers, rows


def _emit(columns: list[str], rows: list[tuple], fmt: str) -> None:
    if fmt in ("json", "dataset-jsonl", "dataset-hf"):
        from mm.display import emit_rows

        emit_rows(fmt, [{h: row[i] for i, h in enumerate(columns)} for row in rows])
        return

    tsv = _to_tsv(columns, rows)
    if fmt in ("tsv", "csv"):
        if fmt == "csv":
            headers, parsed = _parse_tsv(tsv)
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(headers)
            writer.writerows(parsed)
            print(buf.getvalue(), end="")
        else:
            print(tsv, end="")
    else:
        from rich import box
        from rich.table import Table

        from mm.display import _style_cell, output_console

        headers, parsed = _parse_tsv(tsv)
        rich_table = Table(
            caption=f"{len(parsed):,} row{'s' if len(parsed) != 1 else ''}",
            caption_style="dim",
            caption_justify="right",
            show_lines=False,
            padding=(0, 1),
            header_style="bold",
            box=box.ROUNDED,
        )
        for h in headers:
            rich_table.add_column(h, overflow="ellipsis" if h == "summary" else "fold")
        for row in parsed:
            styled = []
            for h, v in zip(headers, row):
                val: Any = v
                if v and h in ("size", "depth", "line_count", "word_count", "pages", "n", "count"):
                    try:
                        val = int(float(v))
                    except ValueError:
                        pass
                elif v in ("True", "False"):
                    val = v == "True"
                elif v == "None":
                    val = None
                styled.append(_style_cell(h, val))
            rich_table.add_row(*styled)
        output_console.print(rich_table)
