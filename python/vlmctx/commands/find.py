"""vlmctx find -- find files matching criteria."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from vlmctx.pipe import is_piped_output


def _parse_size(size_str: str) -> int:
    size_str = size_str.strip().upper()
    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    for suffix, mult in sorted(multipliers.items(), key=lambda x: -len(x[0])):
        if size_str.endswith(suffix):
            num = size_str[: -len(suffix)].strip()
            return int(float(num) * mult)
    return int(size_str)


def find_cmd(
    directory: Annotated[Path, typer.Argument(help="Directory to search")] = Path("."),
    kind: Annotated[Optional[str], typer.Option("--kind", "-k", help="Filter by kind")] = None,
    ext: Annotated[
        Optional[str], typer.Option("--ext", "-e", help="Filter by extension(s), comma-separated")
    ] = None,
    min_size: Annotated[
        Optional[str], typer.Option("--min-size", help="Minimum file size (e.g., 1kb, 1mb)")
    ] = None,
    max_size: Annotated[Optional[str], typer.Option("--max-size", help="Maximum file size")] = None,
    depth: Annotated[
        Optional[int], typer.Option("--depth", "-d", help="Maximum directory depth")
    ] = None,
    sort: Annotated[Optional[str], typer.Option("--sort", "-s", help="Sort by column")] = None,
    reverse: Annotated[bool, typer.Option("--reverse", "-r", help="Reverse sort order")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Force JSON output")] = False,
    limit: Annotated[Optional[int], typer.Option("--limit", help="Max results")] = None,
) -> None:
    """Find files matching criteria (like fd/find)."""

    # Fast path: --json or piped output bypass pyarrow entirely
    if (json_output or is_piped_output()) and depth is None:
        from vlmctx._vlmctx import Scanner

        scanner = Scanner(str(Path(directory).resolve()))
        scanner.scan()

        min_bytes = _parse_size(min_size) if min_size else None
        max_bytes = _parse_size(max_size) if max_size else None

        filter_args = dict(
            kind=kind,
            ext=ext,
            min_size=min_bytes,
            max_size=max_bytes,
            limit=limit,
            sort_by=sort,
            descending=reverse,
        )

        if json_output:
            from vlmctx.display import json_dumps

            import json as json_mod

            print(json_dumps(json_mod.loads(scanner.to_json_fast(**filter_args))))
        else:
            # Compact kind<TAB>size<TAB>path per line (richer than bare paths).
            import json as json_mod

            for entry in json_mod.loads(scanner.to_json_fast(**filter_args)):
                print(f"{entry['kind']}\t{entry['size']}\t{entry['path']}")
        return

    from vlmctx.context import Context

    ctx = Context(directory)

    if kind or ext or min_size or max_size:
        ctx = ctx.filter(kind=kind, ext=ext, min_size=min_size, max_size=max_size)

    table = ctx.to_arrow()

    if depth is not None:
        from vlmctx.duck import query_arrow_table

        table = query_arrow_table(table, f"SELECT * FROM files WHERE depth <= {depth}")

    if sort:
        from vlmctx.duck import query_arrow_table

        order = "DESC" if reverse else "ASC"
        table = query_arrow_table(table, f"SELECT * FROM files ORDER BY {sort} {order}")

    if limit:
        table = table.slice(0, limit)

    if is_piped_output() and not json_output:
        # Compact one-line-per-file: kind<TAB>size<TAB>path — gives LLMs
        # enough context to reason about file types without --json overhead.
        for i in range(table.num_rows):
            kind_val = table.column("kind")[i].as_py()
            size_val = table.column("size")[i].as_py()
            path_val = table.column("path")[i].as_py()
            print(f"{kind_val}\t{size_val}\t{path_val}")
    elif json_output:
        from vlmctx.display import json_dumps

        rows = []
        for i in range(table.num_rows):
            row = {col: table.column(col)[i].as_py() for col in table.column_names}
            rows.append(row)
        print(json_dumps(rows))
    else:
        from vlmctx.display import arrow_table_to_rich, output_console

        rich_table = arrow_table_to_rich(
            table,
            columns=["path", "kind", "size", "ext"],
            limit=limit,
        )
        output_console.print(rich_table)
