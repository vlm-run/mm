"""vlmctx ls -- tabular file listing with metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from vlmctx.context import Context
from vlmctx.display import arrow_table_to_rich, output_console
from vlmctx.pipe import is_piped_output, read_paths_from_stdin


def ls_cmd(
    directory: Annotated[Path, typer.Argument(help="Directory to list")] = Path("."),
    sort: Annotated[Optional[str], typer.Option("--sort", "-s", help="Sort by column")] = None,
    desc: Annotated[bool, typer.Option("--desc", help="Sort descending")] = False,
    columns: Annotated[Optional[str], typer.Option("--columns", "-c", help="Columns to show, comma-separated")] = None,
    limit: Annotated[Optional[int], typer.Option("--limit", "-n", help="Max rows to display")] = None,
    kind: Annotated[Optional[str], typer.Option("--kind", "-k", help="Filter by kind")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Force JSON output")] = False,
) -> None:
    """Tabular file listing with metadata (like eza/ls -l)."""
    stdin_paths = read_paths_from_stdin()

    ctx = Context(directory)
    if kind:
        ctx = ctx.filter(kind=kind)

    table = ctx.to_arrow()

    if stdin_paths:
        from vlmctx.duck import query_arrow_table

        path_list = ", ".join(f"'{p}'" for p in stdin_paths)
        table = query_arrow_table(table, f"SELECT * FROM files WHERE path IN ({path_list})")

    if sort:
        from vlmctx.duck import query_arrow_table

        order = "DESC" if desc else "ASC"
        table = query_arrow_table(table, f"SELECT * FROM files ORDER BY {sort} {order}")

    cols = columns.split(",") if columns else None

    if is_piped_output() and not json_output:
        import csv
        import io

        display_cols = cols or table.column_names
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter="\t")
        writer.writerow(display_cols)
        n = table.num_rows if limit is None else min(limit, table.num_rows)
        for i in range(n):
            writer.writerow(str(table.column(c)[i].as_py()) for c in display_cols)
        print(buf.getvalue(), end="")
    elif json_output:
        import json

        display_cols = cols or table.column_names
        rows = []
        n = table.num_rows if limit is None else min(limit, table.num_rows)
        for i in range(n):
            rows.append({c: table.column(c)[i].as_py() for c in display_cols})
        print(json.dumps(rows, indent=2, default=str))
    else:
        default_cols = ["name", "kind", "size", "ext"]
        display_cols = cols or default_cols

        title_parts = [f"vlmctx ls [dim]{directory}[/dim]"]
        if kind:
            title_parts.append(f"[dim]--kind {kind}[/dim]")
        title = "  ".join(title_parts)

        rich_table = arrow_table_to_rich(table, columns=display_cols, limit=limit, title=title)
        output_console.print(rich_table)
