"""vlmctx tree -- hierarchical directory listing with metadata."""

from __future__ import annotations

import json as json_mod
from pathlib import Path, PurePosixPath
from typing import Annotated, Optional

import typer

from vlmctx.pipe import is_piped_output

KIND_RICH_STYLES: dict[str, str] = {
    "image": "yellow",
    "video": "magenta",
    "code": "green",
    "document": "cyan",
    "audio": "red",
    "data": "dim",
    "config": "dim",
    "text": "white",
}


def _build_tree(entries: list[dict]) -> dict:
    """Build a nested dict from flat file entries."""
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
    """Return (file_count, total_bytes) for a subtree."""
    files = len(node["__files__"])
    size = sum(f["size"] for f in node["__files__"])
    for child in node["__dirs__"].values():
        cf, cs = _count_subtree(child)
        files += cf
        size += cs
    return files, size


def _add_to_rich_tree(
    node: dict,
    rich_node,
    depth: int,
    max_depth: int | None,
    show_size: bool,
    format_size,
) -> None:
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
        _add_to_rich_tree(branch, child_data, depth + 1, max_depth, show_size, format_size)

    for f in sorted(node["__files__"], key=lambda x: x["name"]):
        label = Text()
        style = KIND_RICH_STYLES.get(f["kind"], "")
        label.append(f["name"], style=style)
        if show_size:
            label.append(f"  {format_size(f['size'])}", style="dim")
        rich_node.add(label)


def _render_plain(
    node: dict,
    prefix: str,
    lines: list[str],
    depth: int,
    max_depth: int | None,
    show_size: bool,
    format_size,
) -> None:
    if max_depth is not None and depth > max_depth:
        return

    dirs = sorted(node["__dirs__"].keys())
    files = sorted(node["__files__"], key=lambda f: f["name"])
    items: list[tuple[str, bool, dict | None]] = []

    for d in dirs:
        items.append((d, True, node["__dirs__"][d]))
    for f in files:
        items.append((f["name"], False, f))

    for i, (name, is_dir, data) in enumerate(items):
        is_last = i == len(items) - 1
        connector = "└── " if is_last else "├── "
        next_prefix = prefix + ("    " if is_last else "│   ")

        if is_dir and data is not None:
            fc, fs = _count_subtree(data)
            suffix = f"  ({fc:,} files, {format_size(fs)})" if show_size else f"  ({fc:,} files)"
            lines.append(f"{prefix}{connector}{name}/{suffix}")
            _render_plain(data, next_prefix, lines, depth + 1, max_depth, show_size, format_size)
        else:
            suffix = f"  [{format_size(data['size'])}]" if show_size and data else ""
            lines.append(f"{prefix}{connector}{name}{suffix}")


def _tree_to_json(node: dict, name: str = ".") -> dict:
    result: dict = {"name": name, "type": "directory"}
    children = []

    for dname in sorted(node["__dirs__"].keys()):
        children.append(_tree_to_json(node["__dirs__"][dname], dname))

    for f in sorted(node["__files__"], key=lambda x: x["name"]):
        children.append({
            "name": f["name"],
            "type": "file",
            "kind": f["kind"],
            "size": f["size"],
        })

    result["children"] = children
    fc, fs = _count_subtree(node)
    result["files"] = fc
    result["bytes"] = fs
    return result


def tree_cmd(
    directory: Annotated[Path, typer.Argument(help="Directory to display")] = Path("."),
    depth: Annotated[Optional[int], typer.Option("--depth", "-d", help="Max depth")] = None,
    kind: Annotated[Optional[str], typer.Option("--kind", "-k", help="Filter by kind")] = None,
    size: Annotated[bool, typer.Option("--size", "-s", help="Show file sizes")] = True,
    json_output: Annotated[bool, typer.Option("--json", help="JSON output")] = False,
) -> None:
    """Hierarchical directory listing with metadata (like tree + du)."""
    from vlmctx._vlmctx import Scanner

    scanner = Scanner(str(Path(directory).resolve()))
    scanner.scan()

    raw = json_mod.loads(scanner.to_json_fast(kind=kind))
    tree = _build_tree(raw)
    total_files, total_bytes = _count_subtree(tree)

    if json_output:
        print(json_mod.dumps(_tree_to_json(tree, str(directory)), indent=2))
        return

    from vlmctx.display import format_size

    if is_piped_output():
        header = f"{directory}  ({total_files:,} files, {format_size(total_bytes)})"
        lines: list[str] = [header]
        _render_plain(tree, "", lines, 0, depth, show_size=size, format_size=format_size)
        print("\n".join(lines))
    else:
        from rich.text import Text
        from rich.tree import Tree

        from vlmctx.display import output_console

        root_label = Text()
        root_label.append(f"{directory}", style="bold")
        root_label.append(f"  {total_files:,} files, {format_size(total_bytes)}", style="dim")
        rich_tree = Tree(root_label)
        _add_to_rich_tree(rich_tree, tree, 0, depth, show_size=size, format_size=format_size)
        output_console.print(rich_tree)
