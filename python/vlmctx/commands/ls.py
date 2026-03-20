"""vlmctx ls -- tabular file listing, tree view, and schema introspection."""

from __future__ import annotations

import json as json_mod
from pathlib import Path, PurePosixPath
from typing import Annotated, Optional

import typer

from vlmctx.pipe import is_piped_output, read_paths_from_stdin

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

KIND_TREE_STYLES: dict[str, str] = {
    "image": "yellow",
    "video": "magenta",
    "code": "green",
    "document": "cyan",
    "audio": "red",
    "data": "dim",
    "config": "dim",
    "text": "white",
}


def ls_cmd(
    directory: Annotated[Path, typer.Argument(help="Directory to list")] = Path("."),
    sort: Annotated[Optional[str], typer.Option("--sort", "-s", help="Sort by column")] = None,
    reverse: Annotated[bool, typer.Option("--reverse", "-r", help="Reverse sort order")] = False,
    columns: Annotated[
        Optional[str], typer.Option("--columns", "-c", help="Columns to show, comma-separated")
    ] = None,
    limit: Annotated[
        Optional[int], typer.Option("--limit", help="Max rows to display")
    ] = None,
    kind: Annotated[Optional[str], typer.Option("--kind", "-k", help="Filter by kind")] = None,
    tree: Annotated[bool, typer.Option("--tree", help="Hierarchical tree view")] = False,
    depth: Annotated[
        Optional[int], typer.Option("--depth", "-d", help="Max tree depth")
    ] = None,
    size: Annotated[bool, typer.Option("--size", help="Show file sizes in tree")] = True,
    schema: Annotated[
        bool, typer.Option("--schema", help="Show table schema (column names, types, descriptions)")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Force JSON output")] = False,
) -> None:
    """Tabular file listing with metadata (like eza/ls -l).

    \b
    Modes:
      vlmctx ls ~/data                     # tabular listing (default)
      vlmctx ls ~/data --tree --depth 2    # hierarchical tree view
      vlmctx ls ~/data --schema            # column schema introspection
    """
    if tree:
        _ls_tree(directory, kind, depth, size, json_output)
        return

    if schema:
        _ls_schema(directory, json_output)
        return

    _ls_table(directory, sort, reverse, columns, limit, kind, json_output)


def _has_media_dimensions(table) -> bool:
    """Check if any rows have non-null width/height (i.e. images/video present)."""
    if "width" not in table.column_names:
        return False
    col = table.column("width")
    return col.null_count < col.length()


def _ls_table(
    directory: Path,
    sort: str | None,
    reverse: bool,
    columns: str | None,
    limit: int | None,
    kind: str | None,
    json_output: bool,
) -> None:
    """Default tabular listing."""
    stdin_paths = read_paths_from_stdin()

    if json_output and not stdin_paths and not columns:
        from vlmctx._vlmctx import Scanner

        import json as _json

        from vlmctx.display import json_dumps

        scanner = Scanner(str(Path(directory).resolve()))
        scanner.scan()
        print(
            json_dumps(
                _json.loads(
                    scanner.to_json_fast(
                        kind=kind, sort_by=sort, descending=reverse, limit=limit,
                    )
                )
            )
        )
        return

    from vlmctx.context import Context

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

        order = "DESC" if reverse else "ASC"
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
        from vlmctx.display import json_dumps

        display_cols = cols or table.column_names
        rows = []
        n = table.num_rows if limit is None else min(limit, table.num_rows)
        for i in range(n):
            rows.append({c: table.column(c)[i].as_py() for c in display_cols})
        print(json_dumps(rows))
    else:
        from vlmctx.display import arrow_table_to_rich, output_console

        # Smart defaults: include width/height when media files are present.
        default_cols = ["name", "kind", "size", "ext"]
        if not cols and _has_media_dimensions(table):
            default_cols = ["name", "kind", "size", "width", "height", "ext"]
        display_cols = cols or default_cols

        rich_table = arrow_table_to_rich(table, columns=display_cols, limit=limit)
        output_console.print(rich_table)


# --- Tree mode ---


def _build_tree(entries: list[dict]) -> dict:
    root: dict = {"__files__": [], "__dirs__": {}}
    for entry in entries:
        parts = PurePosixPath(entry["path"]).parts
        node = root
        for part in parts[:-1]:
            if part not in node["__dirs__"]:
                node["__dirs__"][part] = {"__files__": [], "__dirs__": {}}
            node = node["__dirs__"][part]
        node["__files__"].append(entry)
    return root


def _count_subtree(node: dict) -> tuple[int, int]:
    files = len(node["__files__"])
    sz = sum(f["size"] for f in node["__files__"])
    for child in node["__dirs__"].values():
        cf, cs = _count_subtree(child)
        files += cf
        sz += cs
    return files, sz


def _add_to_rich_tree(node, rich_node, depth, max_depth, show_size, format_size) -> None:
    from rich.text import Text

    if max_depth is not None and depth > max_depth:
        return

    for dname in sorted(node["__dirs__"].keys()):
        child_data = node["__dirs__"][dname]
        fc, fs = _count_subtree(child_data)
        label = Text()
        label.append(f"{dname}/", style="bold bright_blue")
        if show_size:
            label.append(f"  {fc:,} files, {format_size(fs)}", style="dim")
        else:
            label.append(f"  {fc:,} files", style="dim")
        branch = rich_node.add(label)
        _add_to_rich_tree(child_data, branch, depth + 1, max_depth, show_size, format_size)

    for f in sorted(node["__files__"], key=lambda x: x["name"]):
        label = Text()
        style = KIND_TREE_STYLES.get(f["kind"], "")
        label.append(f["name"], style=style)
        if show_size:
            label.append(f"  {format_size(f['size'])}", style="dim")
        rich_node.add(label)


def _render_plain_tree(node, prefix, lines, depth, max_depth, show_size, format_size) -> None:
    if max_depth is not None and depth > max_depth:
        return

    dirs = sorted(node["__dirs__"].keys())
    files = sorted(node["__files__"], key=lambda f: f["name"])
    items = [(d, True, node["__dirs__"][d]) for d in dirs]
    items += [(f["name"], False, f) for f in files]

    for i, (name, is_dir, data) in enumerate(items):
        is_last = i == len(items) - 1
        connector = "└── " if is_last else "├── "
        next_prefix = prefix + ("    " if is_last else "│   ")

        if is_dir and data is not None:
            fc, fs = _count_subtree(data)
            suffix = f"  ({fc:,} files, {format_size(fs)})" if show_size else f"  ({fc:,} files)"
            lines.append(f"{prefix}{connector}{name}/{suffix}")
            _render_plain_tree(data, next_prefix, lines, depth + 1, max_depth, show_size, format_size)
        else:
            suffix = f"  [{format_size(data['size'])}]" if show_size and data else ""
            lines.append(f"{prefix}{connector}{name}{suffix}")


def _tree_to_json(node: dict, name: str = ".") -> dict:
    result: dict = {"name": name, "type": "directory"}
    children = []
    for dname in sorted(node["__dirs__"].keys()):
        children.append(_tree_to_json(node["__dirs__"][dname], dname))
    for f in sorted(node["__files__"], key=lambda x: x["name"]):
        children.append({"name": f["name"], "type": "file", "kind": f["kind"], "size": f["size"]})
    result["children"] = children
    fc, fs = _count_subtree(node)
    result["files"] = fc
    result["bytes"] = fs
    return result


def _ls_tree(
    directory: Path, kind: str | None, depth: int | None, show_size: bool, json_output: bool
) -> None:
    from vlmctx._vlmctx import Scanner

    scanner = Scanner(str(Path(directory).resolve()))
    scanner.scan()

    raw = json_mod.loads(scanner.to_json_fast(kind=kind))
    tree_data = _build_tree(raw)
    total_files, total_bytes = _count_subtree(tree_data)

    if json_output:
        from vlmctx.display import json_dumps

        print(json_dumps(_tree_to_json(tree_data, str(directory))))
        return

    from vlmctx.display import format_size

    effective_depth = depth

    if is_piped_output():
        header = f"{directory}  ({total_files:,} files, {format_size(total_bytes)})"
        lines: list[str] = [header]
        _render_plain_tree(tree_data, "", lines, 0, effective_depth, show_size=show_size, format_size=format_size)
        print("\n".join(lines))
    else:
        from rich.text import Text
        from rich.tree import Tree

        from vlmctx.display import output_console

        if effective_depth is None and total_files > 500:
            effective_depth = 1

        root_label = Text()
        root_label.append(f"{directory}", style="bold")
        root_label.append(f"  {total_files:,} files, {format_size(total_bytes)}", style="dim")
        rich_tree = Tree(root_label)
        _add_to_rich_tree(tree_data, rich_tree, 0, effective_depth, show_size=show_size, format_size=format_size)
        output_console.print(rich_tree)
        if effective_depth is not None and depth is None:
            output_console.print(
                f"\n[dim]Showing depth {effective_depth} (capped for {total_files:,} files). "
                f"Use [bold]--depth N[/bold] for more.[/dim]"
            )


# --- Schema mode ---


def _ls_schema(directory: Path, json_output: bool) -> None:
    from vlmctx.context import Context

    ctx = Context(directory)
    table = ctx.to_arrow()

    from vlmctx.display import format_size

    def _desc_with_example(field_name: str, table) -> str:
        desc = COLUMN_DOCS.get(field_name, "")
        if table.num_rows == 0:
            return desc
        val = table.column(field_name)[0].as_py()
        if val is None:
            return desc
        if field_name == "size" and isinstance(val, (int, float)):
            example = f"{val:,} ({format_size(int(val))})"
        else:
            s = str(val)
            example = s[:60] + "..." if len(s) > 60 else s
        return f"{desc} (e.g. {example})" if desc else f"e.g. {example}"

    if json_output:
        from vlmctx.display import json_dumps

        info = []
        for field in table.schema:
            info.append({
                "column": field.name,
                "type": str(field.type),
                "description": _desc_with_example(field.name, table),
            })
        print(json_dumps(info))
        return

    if is_piped_output():
        print("column\ttype\tdescription")
        for field in table.schema:
            print(f"{field.name}\t{field.type}\t{_desc_with_example(field.name, table)}")
        return

    from rich.table import Table as RichTable

    from vlmctx.display import output_console

    from rich import box

    rich_table = RichTable(
        caption=f"[dim]{table.num_rows} rows[/dim]",
        show_lines=True, padding=(0, 1), border_style="dim", header_style="bold",
        box=box.ROUNDED,
    )
    rich_table.add_column("column", style="bold cyan", no_wrap=True)
    rich_table.add_column("type", style="green", no_wrap=True)
    rich_table.add_column("description", style="white")

    for field in table.schema:
        rich_table.add_row(field.name, str(field.type), _desc_with_example(field.name, table))

    output_console.print(rich_table)
    output_console.print(
        f'\n[dim]Query with:[/dim] [bold]vlmctx sql[/bold] [dim]"SELECT ... FROM files" --dir {directory}[/dim]'
    )
