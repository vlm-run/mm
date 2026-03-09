"""vlmctx wc -- count files, bytes, lines, and estimated tokens."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from vlmctx.pipe import is_piped_output

TOKEN_CHARS_RATIO = 4


def _estimate_tokens_for_image(width: int | None, height: int | None) -> int:
    """Rough token estimate for images (OpenAI-style tiling)."""
    if not width or not height:
        return 85
    tiles = ((width + 511) // 512) * ((height + 511) // 512)
    return 85 + tiles * 170


def _format_number(n: int | float) -> str:
    if isinstance(n, float):
        return f"{n:,.1f}"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def wc_cmd(
    directory: Annotated[Path, typer.Argument(help="Directory to count")] = Path("."),
    kind: Annotated[Optional[str], typer.Option("--kind", "-k", help="Filter by kind")] = None,
    by_kind: Annotated[bool, typer.Option("--by-kind", help="Break down by file kind")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Force JSON output")] = False,
) -> None:
    """Count files, bytes, lines, and estimated tokens (like wc for LLM context)."""
    from vlmctx._vlmctx import Scanner

    scanner = Scanner(str(Path(directory).resolve()))
    scanner.scan()

    import json as json_mod

    raw = json_mod.loads(scanner.to_json_fast(kind=kind))

    kind_stats: dict[str, dict[str, int | float]] = {}
    total_files = 0
    total_bytes = 0
    total_tokens = 0
    total_lines = 0

    for entry in raw:
        fk = entry["kind"]
        size = entry["size"]
        w = entry.get("width")
        h = entry.get("height")

        if fk == "image":
            tokens = _estimate_tokens_for_image(w, h)
            lines = 0
        elif fk == "video":
            tokens = 85
            lines = 0
        elif fk in ("code", "text", "config", "data"):
            tokens = size // TOKEN_CHARS_RATIO
            lines = max(1, size // 40)
        elif fk == "document":
            tokens = size // TOKEN_CHARS_RATIO
            lines = max(1, size // 60)
        else:
            tokens = size // TOKEN_CHARS_RATIO
            lines = 0

        total_files += 1
        total_bytes += size
        total_tokens += tokens
        total_lines += lines

        if fk not in kind_stats:
            kind_stats[fk] = {"files": 0, "bytes": 0, "tokens": 0, "lines": 0}
        kind_stats[fk]["files"] += 1
        kind_stats[fk]["bytes"] += size
        kind_stats[fk]["tokens"] += tokens
        kind_stats[fk]["lines"] += lines

    result = {
        "files": total_files,
        "bytes": total_bytes,
        "lines": total_lines,
        "estimated_tokens": total_tokens,
    }
    if by_kind:
        result["by_kind"] = kind_stats  # type: ignore[assignment]

    if json_output:
        print(json_mod.dumps(result, indent=2))
        return

    if is_piped_output():
        print(f"{total_files}\t{total_bytes}\t{total_lines}\t{total_tokens}")
        if by_kind:
            for k, s in sorted(kind_stats.items()):
                print(f"{k}\t{s['files']}\t{s['bytes']}\t{s['lines']}\t{s['tokens']}")
        return

    from vlmctx.display import format_size, output_console

    output_console.print(
        f"[bold]vlmctx wc[/bold] [dim]{directory}[/dim]\n"
    )
    output_console.print(f"  [bold]{total_files:,}[/bold] files")
    output_console.print(f"  [bold]{format_size(total_bytes)}[/bold] total size")
    output_console.print(f"  [bold]{_format_number(total_lines)}[/bold] lines (est.)")
    output_console.print(
        f"  [bold]{_format_number(total_tokens)}[/bold] tokens (est. ~{total_tokens * TOKEN_CHARS_RATIO:,} chars / {TOKEN_CHARS_RATIO})"
    )

    if by_kind:
        output_console.print("")

        from rich.table import Table as RichTable

        tbl = RichTable(
            title="By Kind",
            border_style="dim",
            header_style="bold",
            padding=(0, 1),
        )
        tbl.add_column("kind", style="cyan")
        tbl.add_column("files", justify="right")
        tbl.add_column("size", justify="right")
        tbl.add_column("lines", justify="right")
        tbl.add_column("tokens", justify="right")

        for k in sorted(kind_stats.keys()):
            s = kind_stats[k]
            tbl.add_row(
                k,
                str(s["files"]),
                format_size(int(s["bytes"])),
                _format_number(int(s["lines"])),
                _format_number(int(s["tokens"])),
            )

        output_console.print(tbl)
