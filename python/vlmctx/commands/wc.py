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

    from vlmctx.display import format_number, format_size

    if is_piped_output():
        print("files\tsize\tlines\ttokens")
        print(f"{total_files}\t{format_size(total_bytes)}\t{format_number(total_lines)}\t{format_number(total_tokens)}")
        if by_kind:
            print("\nkind\tfiles\tsize\tlines\ttokens")
            for k, s in sorted(kind_stats.items()):
                print(
                    f"{k}\t{s['files']}\t{format_size(int(s['bytes']))}"
                    f"\t{format_number(int(s['lines']))}\t{format_number(int(s['tokens']))}"
                )
        return

    from vlmctx.display import KIND_STYLES, output_console

    if by_kind:
        from rich.console import Group
        from rich.panel import Panel
        from rich.table import Table as RichTable
        from rich.text import Text

        from rich import box

        tbl = RichTable(
            show_header=True,
            header_style="bold",
            padding=(0, 1),
            border_style="dim",
            expand=False,
            box=box.ROUNDED,
        )
        tbl.add_column("kind", style="cyan", no_wrap=True)
        tbl.add_column("files", justify="right")
        tbl.add_column("size", justify="right", style="bright_blue")
        tbl.add_column("lines", justify="right")
        tbl.add_column("tokens", justify="right", style="bright_green")

        for k in sorted(kind_stats.keys()):
            s = kind_stats[k]
            style = KIND_STYLES.get(k, "dim")
            tbl.add_row(
                Text(k, style=style),
                f"{int(s['files']):,}",
                format_size(int(s["bytes"])),
                format_number(int(s["lines"])),
                format_number(int(s["tokens"])),
            )

        tbl.add_section()
        tbl.add_row(
            Text("total", style="bold"),
            f"[bold]{total_files:,}[/bold]",
            f"[bold]{format_size(total_bytes)}[/bold]",
            f"[bold]{format_number(total_lines)}[/bold]",
            f"[bold]{format_number(total_tokens)}[/bold]",
        )

        subtitle = Text.assemble(
            ("~", "dim"),
            (f"{format_number(total_tokens)}", "bold bright_green"),
            (" tokens  ", "dim"),
            (f"{total_files:,}", "bold"),
            (" files  ", "dim"),
            (format_size(total_bytes), "bright_blue"),
        )

        panel = Panel(
            Group(tbl),
            subtitle=subtitle,
            expand=False,
            padding=(1, 2),
            box=box.ROUNDED,
        )
        output_console.print(panel)
    else:
        from rich import box
        from rich.panel import Panel
        from rich.text import Text

        body = Text()
        body.append(f"  {total_files:,}", style="bold bright_blue")
        body.append("  files\n", style="dim")
        body.append(f"  {format_size(total_bytes)}", style="bold bright_blue")
        body.append("  total size\n", style="dim")
        body.append(f"  {format_number(total_lines)}", style="bold")
        body.append("  lines (est.)\n", style="dim")
        body.append(f"  {format_number(total_tokens)}", style="bold bright_green")
        body.append("  tokens (est.)", style="dim")

        panel = Panel(
            body,
            expand=False,
            padding=(1, 2),
            box=box.ROUNDED,
        )
        output_console.print(panel)
