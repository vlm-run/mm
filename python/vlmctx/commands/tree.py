"""vlmctx tree -- hierarchical directory listing with metadata."""

from __future__ import annotations

import json as json_mod
from pathlib import Path, PurePosixPath
from typing import Annotated, Optional

import typer

from vlmctx.pipe import is_piped_output


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


def _format_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024  # type: ignore[assignment]
    return f"{size:.1f}TB"


def _count_subtree(node: dict) -> tuple[int, int]:
    """Return (file_count, total_bytes) for a subtree."""
    files = len(node["__files__"])
    size = sum(f["size"] for f in node["__files__"])
    for child in node["__dirs__"].values():
        cf, cs = _count_subtree(child)
        files += cf
        size += cs
    return files, size


def _render_tree(
    node: dict,
    prefix: str,
    lines: list[str],
    depth: int,
    max_depth: int | None,
    show_size: bool,
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
            suffix = f"  ({fc} files, {_format_size(fs)})" if show_size else f"  ({fc} files)"
            lines.append(f"{prefix}{connector}\033[1;34m{name}/\033[0m{suffix}")
            _render_tree(data, next_prefix, lines, depth + 1, max_depth, show_size)
        else:
            if show_size and data is not None:
                suffix = f"  [{_format_size(data['size'])}]"
            else:
                suffix = ""
            kind_str = data["kind"] if data else ""
            kind_color = {
                "image": "\033[33m",
                "video": "\033[35m",
                "code": "\033[32m",
                "document": "\033[36m",
                "audio": "\033[31m",
                "data": "\033[90m",
                "config": "\033[90m",
                "text": "\033[37m",
            }.get(kind_str, "")
            reset = "\033[0m" if kind_color else ""
            lines.append(f"{prefix}{connector}{kind_color}{name}{reset}{suffix}")


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

    header = f"\033[1m{directory}\033[0m  ({total_files} files, {_format_size(total_bytes)})"
    lines: list[str] = [header]
    _render_tree(tree, "", lines, 0, depth, show_size=size)

    output = "\n".join(lines)

    if is_piped_output():
        import re
        print(re.sub(r"\033\[[0-9;]*m", "", output))
    else:
        print(output)
