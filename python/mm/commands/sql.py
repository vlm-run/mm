"""mm sql -- query file metadata, L2 results, and chunks with SQL."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Optional

import typer

if TYPE_CHECKING:
    from pyarrow import Table

_LANCE_TABLES = {"l2_results", "chunks"}


def sql_cmd(
    query: Annotated[
        Optional[str],
        typer.Argument(help="SQL query (use 'files', 'l2_results', or 'chunks' as table name)"),
    ] = None,
    directory: Annotated[Path, typer.Option("--dir", "-d", help="Directory to index")] = Path("."),
    format: Annotated[
        Optional[str],
        typer.Option(
            "--format", "-f", help="Output format: json, tsv, csv, dataset-jsonl, dataset-hf"
        ),
    ] = None,
    no_cache: Annotated[
        bool, typer.Option("--no-cache", help="Skip cache, force fresh scan")
    ] = False,
    list_tables: Annotated[
        bool, typer.Option("--list-tables", help="List available tables")
    ] = False,
) -> None:
    """Query file metadata, L2 results, and chunks with SQL via DuckDB.

    \b
    Tables:
      files       — L0/L1 file metadata (scanned from --dir)
      l2_results  — LLM-generated summaries (stored in LanceDB)
      chunks      — Chunked L2 content + embeddings (stored in LanceDB)

    \b
    Examples:
      mm sql "SELECT kind, COUNT(*) as n FROM files GROUP BY kind"
      mm sql "SELECT * FROM files WHERE kind='image'" --dir ~/photos
      mm sql "SELECT uri, summary FROM l2_results LIMIT 10"
      mm sql "SELECT uri, chunk_idx, LENGTH(chunk_text) FROM chunks"
      mm sql "SELECT COUNT(*) FROM chunks WHERE embed_model IS NOT NULL"
      mm sql --list-tables
    """
    from mm.display import resolve_format

    fmt = resolve_format(format)
    if list_tables:
        _list_tables(fmt)
        return

    if query is None:
        raise typer.BadParameter("Provide a SQL query or use --list-tables")

    # Route: if query references l2_results or chunks, use LanceDB
    table_name = _detect_table(query)
    if table_name in _LANCE_TABLES:
        _query_lance(query, table_name, fmt)
    else:
        _query_files(query, directory, fmt, no_cache)


def _detect_table(query: str) -> str:
    """Detect which table the query targets from the FROM clause."""
    match = re.search(r"\bFROM\s+(\w+)", query, re.IGNORECASE)
    if match:
        name = match.group(1).lower()
        if name in _LANCE_TABLES:
            return name
    return "files"


def _query_lance(query: str, table_name: str, fmt: str) -> None:
    from mm.lancedb.db import MmDatabase

    db = MmDatabase()
    result = db.sql(query, table_name=table_name)
    _emit_tsv(_arrow_to_tsv(result), fmt)


def _query_files(query: str, directory: Path, fmt: str, no_cache: bool) -> None:
    cached_tsv: str | None = None
    cache_key: str | None = None
    if not no_cache:
        cache_key = _make_cache_key(directory, query)
        if cache_key:
            from mm.lancedb.db import MmDatabase

            cached_tsv = MmDatabase._cache_get(cache_key)

    if cached_tsv is not None:
        _emit_tsv(cached_tsv, fmt)
        return

    from mm.context import Context
    from mm.duck import query_arrow_table

    result = query_arrow_table(Context(directory).to_arrow(), query)
    tsv = _arrow_to_tsv(result)
    if cache_key and tsv:
        from mm.lancedb.db import MmDatabase

        MmDatabase()._cache_put(cache_key, tsv)
    _emit_tsv(tsv, fmt)


def _list_tables(fmt: str) -> None:
    from mm.lancedb.db import MmDatabase

    db = MmDatabase()
    lance_tables = db._connect().table_names() if db._db_path.exists() else []

    rows = [
        {"table": "files", "source": "scan + DuckDB", "stored": "ephemeral"},
    ]
    for name in ("l2_results", "chunks"):
        if name in lance_tables:
            count = db._connect().open_table(name).count_rows()
            rows.append({"table": name, "source": "LanceDB", "stored": f"{count} rows"})
        else:
            rows.append({"table": name, "source": "LanceDB", "stored": "empty"})

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
            title="Available tables",
            box=box.ROUNDED,
            border_style="dim",
            header_style="bold white",
        )
        t.add_column("table", style="bold")
        t.add_column("source")
        t.add_column("stored", justify="right")
        for r in rows:
            t.add_row(r["table"], r["source"], r["stored"])
        output_console.print(t)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cache_key(directory: Path, query: str) -> str | None:
    try:
        from mm._mm import directory_hash

        dir_hash = directory_hash(str(Path(directory).resolve()))
        if dir_hash is None:
            return None
        query_hash = hashlib.md5(query.encode()).hexdigest()[:12]
        return f"sql:{dir_hash}:{query_hash}"
    except Exception:
        return None


def _arrow_to_tsv(table: Table) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter="\t")
    writer.writerow(table.column_names)
    for i in range(table.num_rows):
        writer.writerow(str(table.column(c)[i].as_py()) for c in table.column_names)
    return buf.getvalue()


def _parse_tsv(tsv: str) -> tuple[list[str], list[list[str]]]:
    reader = csv.reader(io.StringIO(tsv), delimiter="\t")
    headers = next(reader)
    rows = list(reader)
    return headers, rows


def _emit_tsv(tsv: str, fmt: str) -> None:
    if fmt in ("tsv", "csv"):
        if fmt == "csv":
            headers, rows = _parse_tsv(tsv)
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(headers)
            writer.writerows(rows)
            print(buf.getvalue(), end="")
        else:
            print(tsv, end="")
    elif fmt in ("json", "dataset-jsonl", "dataset-hf"):
        from mm.display import emit_rows

        headers, rows = _parse_tsv(tsv)
        emit_rows(fmt, [{h: row[i] for i, h in enumerate(headers)} for row in rows])
    else:
        from rich import box
        from rich.table import Table

        from mm.display import _style_cell, output_console

        headers, rows = _parse_tsv(tsv)
        rich_table = Table(
            caption=f"{len(rows):,} row{'s' if len(rows) != 1 else ''}",
            caption_style="dim",
            caption_justify="right",
            show_lines=False,
            padding=(0, 1),
            border_style="dim",
            header_style="bold white",
            box=box.ROUNDED,
        )
        for h in headers:
            rich_table.add_column(h)
        for row in rows:
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
