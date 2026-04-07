"""mm sql -- query file metadata, L2 results, and chunks with SQL."""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

_STORED_TABLES = {"l2_results", "chunks", "files", "cache"}


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
    list_tables: Annotated[
        bool, typer.Option("--list-tables", help="List available tables")
    ] = False,
) -> None:
    """Query file metadata, L2 results, and chunks with SQL.

    \b
    Tables:
      files       — L0/L1 file metadata (scanned from --dir, or persistent store)
      l2_results  — LLM-generated summaries (stored in SQLite)
      chunks      — Chunked L2 content + embeddings (stored in SQLite)

    \b
    Examples:
      mm sql "SELECT kind, COUNT(*) as n FROM files GROUP BY kind"
      mm sql "SELECT * FROM files WHERE kind='image'" --dir ~/photos
      mm sql "SELECT uri, summary FROM l2_results LIMIT 10"
      mm sql "SELECT uri, chunk_idx, LENGTH(chunk_text) FROM chunks"
      mm sql --list-tables
    """
    from mm.display import resolve_format

    fmt = resolve_format(format)
    if list_tables:
        _list_tables(fmt)
        return

    if query is None:
        raise typer.BadParameter("Provide a SQL query or use --list-tables")

    table_name = _detect_table(query)
    if table_name in ("l2_results", "chunks"):
        _query_stored(query, fmt)
    else:
        _query_files(query, directory, fmt)


def _detect_table(query: str) -> str:
    match = re.search(r"\bFROM\s+(\w+)", query, re.IGNORECASE)
    if match:
        name = match.group(1).lower()
        if name in _STORED_TABLES:
            return name
    return "files"


def _query_stored(query: str, fmt: str) -> None:
    """Query persistent SQLite tables (l2_results, chunks)."""
    from mm.store.db import MmDatabase

    columns, rows = MmDatabase().sql(query)
    _emit(columns, rows, fmt)


def _query_files(query: str, directory: Path, fmt: str) -> None:
    """Scan directory → temp SQLite table → query."""
    from mm.context import Context
    from mm.query import query_arrow_table

    result = query_arrow_table(Context(directory).to_arrow(), query)
    columns = result.column_names
    rows = [tuple(result.column(c)[i].as_py() for c in columns) for i in range(result.num_rows)]
    _emit(columns, rows, fmt)


def _list_tables(fmt: str) -> None:
    from mm.store.db import MmDatabase

    db = MmDatabase()
    counts = {}
    for name in ("l2_results", "chunks"):
        row = db._connect.execute(f"SELECT COUNT(*) FROM {name}").fetchone()
        counts[name] = row[0] if row else 0

    rows = [
        {"table": "files", "source": "scan + SQLite", "stored": "ephemeral"},
    ]
    for name in ("l2_results", "chunks"):
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
            border_style="dim",
            header_style="bold white",
            box=box.ROUNDED,
        )
        for h in headers:
            rich_table.add_column(h)
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
