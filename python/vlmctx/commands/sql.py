"""vlmctx sql -- query the index via DuckDB."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from vlmctx.pipe import is_piped_output


def sql_cmd(
    query: Annotated[str, typer.Argument(help="SQL query (table name is 'files')")],
    directory: Annotated[Path, typer.Option("--dir", "-d", help="Directory to index")] = Path("."),
    json_output: Annotated[bool, typer.Option("--json", help="Force JSON output")] = False,
) -> None:
    """Query the file index with SQL via DuckDB."""
    from vlmctx.context import Context
    from vlmctx.duck import query_arrow_table

    ctx = Context(directory)
    result = query_arrow_table(ctx.to_arrow(), query)

    if is_piped_output() and not json_output:
        import csv
        import io

        buf = io.StringIO()
        writer = csv.writer(buf, delimiter="\t")
        writer.writerow(result.column_names)
        for i in range(result.num_rows):
            writer.writerow(str(result.column(c)[i].as_py()) for c in result.column_names)
        print(buf.getvalue(), end="")
    elif json_output:
        from vlmctx.display import json_dumps

        rows = []
        for i in range(result.num_rows):
            rows.append({c: result.column(c)[i].as_py() for c in result.column_names})
        print(json_dumps(rows))
    else:
        from vlmctx.display import arrow_table_to_rich, output_console

        rich_table = arrow_table_to_rich(result, title="[dim]sql[/dim]")
        output_console.print(rich_table)
