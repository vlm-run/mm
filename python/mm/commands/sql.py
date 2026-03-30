"""mm sql -- query the index via DuckDB."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer


def sql_cmd(
    query: Annotated[str, typer.Argument(help="SQL query (table name is 'files')")],
    directory: Annotated[Path, typer.Option("--dir", "-d", help="Directory to index")] = Path("."),
    format: Annotated[
        Optional[str], typer.Option("--format", help="Output format: json, tsv, csv, dataset-jsonl, dataset-hf")
    ] = None,
) -> None:
    """Query the file index with SQL via DuckDB."""
    from mm.context import Context
    from mm.display import resolve_format
    from mm.duck import query_arrow_table

    fmt = resolve_format(format)

    ctx = Context(directory)
    result = query_arrow_table(ctx.to_arrow(), query)

    if fmt in ("dataset-jsonl", "dataset-hf"):
        rows = []
        for i in range(result.num_rows):
            rows.append({c: result.column(c)[i].as_py() for c in result.column_names})
        if fmt == "dataset-jsonl":
            from mm.display import emit_dataset_jsonl

            emit_dataset_jsonl(rows)
        else:
            from mm.display import emit_dataset_hf

            emit_dataset_hf(rows)
        return

    if fmt == "json":
        from mm.display import json_dumps

        rows = []
        for i in range(result.num_rows):
            rows.append({c: result.column(c)[i].as_py() for c in result.column_names})
        print(json_dumps(rows))
    elif fmt in ("tsv", "csv"):
        import csv
        import io

        sep = "\t" if fmt == "tsv" else ","
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=sep)
        writer.writerow(result.column_names)
        for i in range(result.num_rows):
            writer.writerow(str(result.column(c)[i].as_py()) for c in result.column_names)
        print(buf.getvalue(), end="")
    else:
        from mm.display import arrow_table_to_rich, output_console

        rich_table = arrow_table_to_rich(result)
        output_console.print(rich_table)
