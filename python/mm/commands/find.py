"""mm find -- find and list files with metadata, tree view, schema."""

from __future__ import annotations

import json as json_mod
from pathlib import Path, PurePosixPath
from typing import Annotated, Optional

import typer

from mm.utils import Format

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
    "image": "",
    "video": "",
    "code": "",
    "document": "",
    "audio": "",
    "data": "",
    "config": "",
    "text": "",
}


def _apply_ignore_case(pattern: str | None, ignore_case: bool) -> str | None:
    """Prepend the regex ``(?i)`` flag when case-insensitive matching is requested - supports both py and rs"""
    if pattern is None or not ignore_case:
        return pattern
    return f"(?i){pattern}"


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
    name: Annotated[
        Optional[str], typer.Option("--name", "-n", help="Filter by file name (string or regex)")
    ] = None,
    ignore_case: Annotated[
        bool,
        typer.Option("--ignore-case", "-i", help="Case-insensitive name matching"),
    ] = False,
    kind: Annotated[
        Optional[str],
        typer.Option(
            "--kind", "-k", help="Filter by kind (supports comma-separated - image,document)"
        ),
    ] = None,
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
    columns: Annotated[
        Optional[str], typer.Option("--columns", "-c", help="Columns to show, comma-separated")
    ] = None,
    tree: Annotated[bool, typer.Option("--tree", help="Hierarchical tree view")] = False,
    size: Annotated[bool, typer.Option("--size", help="Show file sizes in tree")] = True,
    schema: Annotated[
        bool, typer.Option("--schema", help="Show table schema (column names, types, descriptions)")
    ] = False,
    format: Annotated[
        Optional[Format],
        typer.Option(
            "--format", "-f", help="Output format: json, tsv, csv, dataset-jsonl, dataset-hf"
        ),
    ] = None,
    limit: Annotated[Optional[int], typer.Option("--limit", help="Max results")] = None,
    no_ignore: Annotated[
        bool, typer.Option("--no-ignore", help="Don't respect .gitignore rules")
    ] = False,
    session: Annotated[
        Optional[str],
        typer.Option(
            "--session",
            help="Session id to tag results with (enables global <session>/<ref_id> refs)",
        ),
    ] = None,
    refs: Annotated[
        bool,
        typer.Option(
            "--refs",
            help="Include ref_id column (requires --session; opt-in, hidden by default)",
        ),
    ] = False,
) -> None:
    """Find files matching criteria (like fd/find).

    \b
    Modes:
      mm find ~/data                      # tabular listing (default)
      mm find ~/data --tree --depth 2     # hierarchical tree view
      mm find ~/data --schema             # column schema introspection

    \b
    Examples:
      mm find ~/data --kind image                           # images only
      mm find ~/data --kind image,document                  # images + documents
      mm find ~/data --ext .pdf,.docx --sort size -r        # docs by size
      mm find ~/data --columns name,kind,size --limit 20    # custom columns
      mm find ~/data --tree --kind video                    # video tree
      mm find ~/data --min-size 1mb --sort size -r          # large files
      mm find ~/data --name "test_.*\\.py"                  # regex name match
      mm find ~/data -n config                              # substring name match
      mm find ~/data -n CONFIG -i                           # case-insensitive match
      mm find ~/data --no-ignore                            # include gitignored files
      mm find ~/data --session my-sess --refs               # show <session>/<ref_id>
    """
    from mm.display import resolve_format

    fmt = resolve_format(format.value if format else None)
    if refs and not session:
        raise typer.BadParameter("--refs requires --session <id>")
    if ignore_case and not name:
        raise typer.BadParameter("--ignore-case requires --name/-n <pattern>")
    if tree:
        _find_tree(
            directory, kind, name, depth, size, fmt, no_ignore=no_ignore, ignore_case=ignore_case
        )
        return
    if schema:
        _find_schema(directory, fmt, no_ignore=no_ignore)
        return

    _find_table(
        directory,
        kind,
        ext,
        min_size,
        max_size,
        name,
        depth,
        sort,
        reverse,
        columns,
        limit,
        fmt,
        no_ignore=no_ignore,
        session=session,
        refs=refs,
        ignore_case=ignore_case,
    )


# ---------------------------------------------------------------------------
# Table mode (default)
# ---------------------------------------------------------------------------


def _has_media_dimensions(table) -> bool:
    """Check if any rows have non-null width/height."""
    if "width" not in table.column_names:
        return False
    col = table.column("width")
    return bool(col.null_count < col.length())


def _find_table(
    directory: Path,
    kind: str | None,
    ext: str | None,
    min_size: str | None,
    max_size: str | None,
    name: str | None,
    depth: int | None,
    sort: str | None,
    reverse: bool,
    columns: str | None,
    limit: int | None,
    fmt: str,
    *,
    no_ignore: bool = False,
    session: str | None = None,
    refs: bool = False,
    ignore_case: bool = False,
) -> None:
    """Default tabular listing."""
    from mm.pipe import read_paths_from_stdin, resolve_piped_paths

    stdin_paths = read_paths_from_stdin()
    # Fast path: non-rich output without columns/stdin bypasses pyarrow.
    # --session alone is a no-op for display; only --refs forces the slow
    # path to attach the ref_id column.
    if fmt != "rich" and not stdin_paths and not columns and depth is None and not refs:
        from mm._mm import Scanner

        scanner = Scanner(str(Path(directory).resolve()), None, no_ignore=no_ignore)
        scanner.scan()

        min_bytes = _parse_size(min_size) if min_size else None
        max_bytes = _parse_size(max_size) if max_size else None

        filter_args: dict = dict(
            kind=kind,
            ext=ext,
            min_size=min_bytes,
            max_size=max_bytes,
            name=_apply_ignore_case(name, ignore_case),
            limit=limit,
            sort_by=sort,
            descending=reverse,
        )

        rows = json_mod.loads(scanner.to_json_fast(**filter_args))
        for row in rows:
            row["path"] = f"{str(directory)}/{row['path']}"
        if fmt in ("json", "dataset-jsonl", "dataset-hf"):
            from mm.display import emit_rows

            emit_rows(fmt, rows)
        else:
            sep = "," if fmt == "csv" else "\t"
            print(f"kind{sep}size{sep}path")
            for row in rows:
                print(f"{row['kind']}{sep}{row['size']}{sep}{row['path']}")
        return

    from mm.context import Context

    # The library owns all row selection (filter / name / depth / sort).
    ctx = Context(directory, no_ignore=no_ignore, session_id=session)
    ctx = ctx.filter(
        kind=kind,
        ext=ext,
        min_size=min_size,
        max_size=max_size,
        name=name,
        ignore_case=ignore_case,
        depth=depth,
        sort=sort,
        reverse=reverse,
    )

    table = ctx.to_arrow(refs=refs)

    if stdin_paths:
        from mm.pipe import resolve_piped_paths

        # Arrow table has relative paths; resolve both sides to absolute for matching.
        stdin_set = set(resolve_piped_paths(stdin_paths))
        root = Path(directory).resolve()
        mask = [str(root / p) in stdin_set for p in table.column("path").to_pylist()]
        table = table.filter(mask)

    cols = columns.split(",") if columns else None

    if fmt in ("json", "dataset-jsonl", "dataset-hf"):
        from mm.display import emit_rows

        display_cols = cols or table.column_names
        n = table.num_rows if limit is None else min(limit, table.num_rows)
        rows = [{c: table.column(c)[i].as_py() for c in display_cols} for i in range(n)]
        emit_rows(fmt, rows)
        return

    elif fmt == "csv":
        import csv
        import io

        display_cols = cols or table.column_names
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(display_cols)
        n = table.num_rows if limit is None else min(limit, table.num_rows)
        for i in range(n):
            writer.writerow(str(table.column(c)[i].as_py()) for c in display_cols)
        print(buf.getvalue(), end="")
    elif fmt == "tsv":
        display_cols = cols or table.column_names
        n = table.num_rows if limit is None else min(limit, table.num_rows)
        print("\t".join(display_cols))
        for i in range(n):
            print("\t".join(str(table.column(c)[i].as_py()) for c in display_cols))
    else:
        from mm.display import arrow_table_to_rich, output_console

        default_cols = ["path", "kind", "size", "ext"]
        if not cols and _has_media_dimensions(table):
            default_cols = ["path", "kind", "size", "width", "height", "ext"]
        if not cols and refs and "ref_id" in table.column_names:
            default_cols = [*default_cols, "ref_id"]

        display_cols = cols or default_cols
        rich_table = arrow_table_to_rich(table, columns=display_cols, limit=limit)
        output_console.print(rich_table)


# ---------------------------------------------------------------------------
# Tree mode
# ---------------------------------------------------------------------------


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
        label.append(f"{dname}/", style="bold")
        if show_size:
            label.append(f"  {fc:,} files, {format_size(fs)}")
        else:
            label.append(f"  {fc:,} files")
        branch = rich_node.add(label)
        _add_to_rich_tree(child_data, branch, depth + 1, max_depth, show_size, format_size)

    for f in sorted(node["__files__"], key=lambda x: x["name"]):
        label = Text()
        style = KIND_TREE_STYLES.get(f["kind"], "")
        label.append(f["name"], style=style)
        if show_size:
            label.append(f"  {format_size(f['size'])}")
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
            _render_plain_tree(
                data, next_prefix, lines, depth + 1, max_depth, show_size, format_size
            )
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


def _find_tree(
    directory: Path,
    kind: str | None,
    name: str | None,
    depth: int | None,
    show_size: bool,
    fmt: str,
    *,
    no_ignore: bool = False,
    ignore_case: bool = False,
) -> None:
    from mm._mm import Scanner

    scanner = Scanner(str(Path(directory).resolve()), no_ignore=no_ignore)
    scanner.scan()

    raw = json_mod.loads(
        scanner.to_json_fast(kind=kind, name=_apply_ignore_case(name, ignore_case))
    )
    tree_data = _build_tree(raw)
    total_files, total_bytes = _count_subtree(tree_data)

    if fmt == "json":
        from mm.display import json_dumps

        print(json_dumps(_tree_to_json(tree_data, str(directory))))
        return

    from mm.display import format_size

    effective_depth = depth

    if fmt in ("tsv", "csv", "text"):
        header = f"{directory}  ({total_files:,} files, {format_size(total_bytes)})"
        lines: list[str] = [header]
        _render_plain_tree(
            tree_data,
            "",
            lines,
            0,
            effective_depth,
            show_size=show_size,
            format_size=format_size,
        )
        print("\n".join(lines))
    else:
        from rich.text import Text
        from rich.tree import Tree

        from mm.display import output_console

        if effective_depth is None and total_files > 500:
            effective_depth = 1

        root_label = Text()
        root_label.append(f"{directory}", style="bold")
        root_label.append(f"  {total_files:,} files, {format_size(total_bytes)}")
        rich_tree = Tree(root_label)
        _add_to_rich_tree(
            tree_data,
            rich_tree,
            0,
            effective_depth,
            show_size=show_size,
            format_size=format_size,
        )
        output_console.print(rich_tree)
        if effective_depth is not None and depth is None:
            output_console.print(
                f"\nShowing depth {effective_depth} (capped for {total_files:,} files). "
                f"Use [bold]--depth N[/bold] for more."
            )


# ---------------------------------------------------------------------------
# Schema mode
# ---------------------------------------------------------------------------


def _find_schema(directory: Path, fmt: str, *, no_ignore: bool = False) -> None:
    from mm.context import Context

    ctx = Context(directory, no_ignore=no_ignore)
    table = ctx.to_arrow()

    from mm.display import format_size

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

    if fmt == "json":
        from mm.display import json_dumps

        info = []
        for field in table.schema:
            info.append(
                {
                    "column": field.name,
                    "type": str(field.type),
                    "description": _desc_with_example(field.name, table),
                }
            )
        print(json_dumps(info))
        return

    if fmt in ("tsv", "csv"):
        sep = "\t" if fmt == "tsv" else ","
        print(f"column{sep}type{sep}description")
        for field in table.schema:
            print(f"{field.name}{sep}{field.type}{sep}{_desc_with_example(field.name, table)}")
        return

    from rich import box
    from rich.table import Table as RichTable

    from mm.display import output_console

    rich_table = RichTable(
        caption=f"{table.num_rows} rows",
        caption_style="dim",
        caption_justify="right",
        show_lines=True,
        padding=(0, 1),
        header_style="bold",
        box=box.ROUNDED,
    )
    rich_table.add_column("column", no_wrap=True)
    rich_table.add_column("type", no_wrap=True)
    rich_table.add_column("description")

    for field in table.schema:
        rich_table.add_row(field.name, str(field.type), _desc_with_example(field.name, table))

    output_console.print(rich_table)
    output_console.print(
        f'\nQuery with: [bold]mm sql[/bold] "SELECT ... FROM files" --dir {directory}'
    )
