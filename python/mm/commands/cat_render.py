"""Rendering logic for ``mm cat`` — display, format dispatch, and output.

Extracted from ``cat.py`` to separate the render/display path from the
extraction/accumulation path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mm.utils import file_kind


def display_rich(
    path: Path, content: str, mode: str, *, n: int | None, skip_formatting: bool = False
) -> None:
    """Render file content with rich syntax highlighting when applicable."""
    from mm.display import output_console

    ext = path.suffix.lstrip(".")
    kind = file_kind(path)
    is_binary = kind in ("image", "document", "video", "audio") or "\x00" in content[:512]

    if (
        not skip_formatting
        and not is_binary
        and ext
        in (
            "py",
            "rs",
            "js",
            "ts",
            "tsx",
            "jsx",
            "go",
            "java",
            "c",
            "cpp",
            "h",
            "hpp",
            "rb",
            "sh",
            "bash",
            "zsh",
            "yaml",
            "yml",
            "toml",
            "json",
            "md",
            "html",
            "css",
            "sql",
            "xml",
        )
    ):
        from rich.syntax import Syntax

        syntax = Syntax(
            content,
            ext
            if ext
            in (
                "py",
                "rs",
                "js",
                "ts",
                "go",
                "java",
                "c",
                "cpp",
                "rb",
                "bash",
                "yaml",
                "json",
                "md",
                "html",
                "css",
                "sql",
                "xml",
            )
            else "text",
            theme="monokai",
            line_numbers=True,
        )
        output_console.print(syntax)
    else:
        output_console.print(content)


class RenderContext:
    """Stateful renderer for batch ``mm cat`` output.

    Encapsulates the format dispatch (json, rich, plain), multi-file
    separators, and the results accumulator that were previously a
    closure inside ``cat_cmd``.

    Attributes:
        fmt: Output format (json, pretty-json, rich, plain, dataset-*).
        mode: Extraction mode (fast, accurate).
        n: Optional line limit (head/tail).
        multi_file: Whether multiple files are being rendered.
        dry_run: Skip syntax formatting (dry-run preview).
        results: Accumulated entries for json/dataset formats.
    """

    def __init__(
        self,
        fmt: str,
        mode: str,
        n: int | None,
        multi_file: bool,
        dry_run: bool,
    ) -> None:
        self.fmt = fmt
        self.mode = mode
        self.n = n
        self.multi_file = multi_file
        self.dry_run = dry_run
        self.results: list[dict[str, Any]] = []
        self._emitted = 0

    def render(self, p: Path, content: str) -> None:
        """Render a single file's content according to the configured format."""
        if self.fmt in ("json", "pretty-json", "dataset-jsonl", "dataset-hf"):
            if self.fmt in ("json", "pretty-json"):
                entry: dict[str, Any] = {"path": str(p), "mode": self.mode, "content": content}
            else:
                entry = {
                    "path": str(p),
                    "mode": self.mode,
                    "content": content,
                    "name": p.name,
                    "type": file_kind(p),
                    "size": p.stat().st_size,
                }
            self.results.append(entry)
        elif self.fmt == "rich":
            if self.multi_file:
                from mm.display import output_console

                if self._emitted > 0:
                    output_console.print("\n====")
                output_console.print(f"<{p.name}>")
            display_rich(p, content, self.mode, n=self.n, skip_formatting=self.dry_run)
            self._emitted += 1
        else:
            if self.multi_file:
                if self._emitted > 0:
                    print("\n====")
                print(f"<{p.name}>")

            dim_prefix = "[dim]"
            lines = content.split("\n")
            plain_lines: list[str] = []
            rich_lines: list[str] = []

            for ln in lines:
                if dim_prefix in ln:
                    rich_lines.append(ln)
                else:
                    plain_lines.append(ln)

            if plain_lines:
                print("\n".join(plain_lines))
            if rich_lines:
                from mm.display import output_console

                output_console.print("\n".join(rich_lines))
            self._emitted += 1

    def emit_results(self, output_dir: Path | None) -> None:
        """Flush accumulated json/dataset results to disk or stdout."""
        if self.fmt not in ("json", "pretty-json", "dataset-jsonl", "dataset-hf"):
            return
        if not self.results:
            return
        from mm.display import emit_rows

        emit_rows(
            self.fmt,
            self.results,
            output_dir=str(output_dir) if output_dir else "mm_dataset",
        )
