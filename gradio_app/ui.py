"""Gradio UI for the mm app.

Calls the same in-process route handlers as the FastAPI surface — no
HTTP round-trip. The Modern Organic Editorial design system is loaded
via ``mount_gradio_app(head=DESIGN_HEAD)``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import gradio as gr

from gradio_app.design import DESIGN_HEAD, FOOTER_HTML, HEADER_HTML

__all__ = ["DESIGN_HEAD", "FOOTER_HTML", "HEADER_HTML", "build_ui"]


def _ascii_tree(node: dict[str, Any], prefix: str = "", is_last: bool = True) -> list[str]:
    """Render a tree dict (as produced by /list-directory) as ASCII lines."""
    name = node["name"]
    if node["type"] == "directory":
        size_label = f"  ({node.get('files', 0)} files, {node.get('bytes', 0)} bytes)"
        line = f"{prefix}{'└── ' if is_last else '├── '}{Path(name).name}/{size_label}"
    else:
        line = f"{prefix}{'└── ' if is_last else '├── '}{name}  [{node.get('size', 0)} bytes, {node.get('kind', '?')}]"

    lines = [line]
    children = node.get("children", []) or []
    next_prefix = prefix + ("    " if is_last else "│   ")
    for i, child in enumerate(children):
        lines.extend(_ascii_tree(child, next_prefix, i == len(children) - 1))
    return lines


_TERMINAL_HTML = '<div class="mm-terminal-wrap"><div id="mm-terminal"></div></div>'


def build_ui() -> gr.Blocks:
    """Single-page UI: header + xterm.js terminal + footer.

    The terminal is mounted into ``#mm-terminal`` by the script in
    ``DESIGN_HEAD``. It opens a WebSocket to ``/ws/terminal`` (served by
    ``gradio_app.main``) which bridges to a PTY-backed login shell with
    ``mm`` on PATH and the data directory as cwd. The previous custom
    Browse/Cat/Grep/Profiles forms are gone — users now run the
    corresponding ``mm`` commands directly.

    The ``_do_*`` helpers above are retained because ``spaces_app.py``
    monkeypatches them; they are no longer wired into the UI.
    """
    with gr.Blocks(title="mm app") as demo:
        gr.HTML(HEADER_HTML)
        gr.HTML(_TERMINAL_HTML)
        gr.HTML(FOOTER_HTML)
    return demo
