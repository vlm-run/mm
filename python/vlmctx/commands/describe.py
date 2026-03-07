"""vlmctx describe -- describe the file index table schema."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from vlmctx.context import Context
from vlmctx.display import format_size, output_console
from vlmctx.pipe import is_piped_output

COLUMN_DOCS: dict[str, str] = {
    "path": "Relative path from the scanned root directory",
    "name": "File name with extension",
    "stem": "File name without extension",
    "ext": "File extension including dot (.png, .pdf, .mp4)",
    "size": "File size in bytes",
    "modified": "Last modification timestamp (UTC)",
    "created": "Creation timestamp (UTC)",
    "mime": "MIME type inferred from extension",
    "kind": "Semantic category: image | video | document | code | audio | data | config | text | other",
    "is_binary": "True if the file is detected as binary content",
    "depth": "Directory depth relative to scan root (0 = top-level)",
    "parent": "Parent directory name (empty string for top-level)",
    "width": "Pixel width (images from header, videos via ffprobe). Null for non-media.",
    "height": "Pixel height (images from header, videos via ffprobe). Null for non-media.",
}


def describe_cmd(
    directory: Annotated[Path, typer.Argument(help="Directory to inspect")] = Path("."),
    json_output: Annotated[bool, typer.Option("--json", help="Force JSON output")] = False,
) -> None:
    """Describe the file index table -- columns, types, and what they contain."""
    ctx = Context(directory)
    table = ctx.to_arrow()

    if json_output:
        import json

        info = []
        for field in table.schema:
            col = table.column(field.name)
            sample = col[0].as_py() if table.num_rows > 0 else None
            if field.name == "size" and isinstance(sample, (int, float)):
                sample = f"{sample} ({format_size(int(sample))})"
            info.append({
                "column": field.name,
                "type": str(field.type),
                "description": COLUMN_DOCS.get(field.name, ""),
                "sample": sample,
            })
        print(json.dumps(info, indent=2, default=str))
        return

    if is_piped_output():
        print("column\ttype\tdescription\tsample")
        for field in table.schema:
            col = table.column(field.name)
            sample = col[0].as_py() if table.num_rows > 0 else ""
            desc = COLUMN_DOCS.get(field.name, "")
            print(f"{field.name}\t{field.type}\t{desc}\t{sample}")
        return

    from rich.table import Table as RichTable

    rich_table = RichTable(
        title=f"files  [dim]({table.num_rows} rows)[/dim]",
        show_lines=True,
        padding=(0, 1),
        border_style="dim",
        header_style="bold",
    )
    rich_table.add_column("column", style="bold cyan", no_wrap=True)
    rich_table.add_column("type", style="green", no_wrap=True)
    rich_table.add_column("description", style="white")
    rich_table.add_column("sample", style="dim italic", max_width=50)

    for field in table.schema:
        col = table.column(field.name)
        desc = COLUMN_DOCS.get(field.name, "")
        sample = ""
        if table.num_rows > 0:
            val = col[0].as_py()
            if field.name == "size" and isinstance(val, (int, float)):
                sample = f"{val:,} ({format_size(int(val))})"
            elif val is not None:
                s = str(val)
                sample = s[:45] + "..." if len(s) > 45 else s
        rich_table.add_row(field.name, str(field.type), desc, sample)

    output_console.print(rich_table)
    output_console.print(
        f"\n[dim]Query with:[/dim] [bold]vlmctx sql[/bold] [dim]\"SELECT ... FROM files\" --dir {directory}[/dim]"
    )
