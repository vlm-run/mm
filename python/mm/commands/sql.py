"""mm sql -- query the file index with SQL."""

from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Optional

import typer

if TYPE_CHECKING:
    from pyarrow import Table


def sql_cmd(
    query: Annotated[str, typer.Argument(help="SQL query (table name is 'files')")],
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
) -> None:
    """Query the file index with SQL via DuckDB."""
    from mm.display import resolve_format

    fmt = resolve_format(format)
    cached_tsv: str | None = None
    cache_key: str | None = None
    if not no_cache:
        cache_key = _make_cache_key(directory, query)
        if cache_key:
            from mm.lancedb.db import MmDatabase

            cached_tsv = MmDatabase()._cache_get(cache_key)

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
    """Render TSV string in the requested format. No pyarrow import."""
    if fmt in ("tsv", "csv"):
        if fmt == "csv":
            # Convert TSV → CSV
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
                    val = int(v)
                elif v in ("True", "False"):
                    val = True if v == "True" else False
                elif v == "None":
                    val = None
                styled.append(_style_cell(h, val))
            rich_table.add_row(*styled)
        output_console.print(rich_table)
