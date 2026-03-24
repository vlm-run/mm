"""mm wc -- count files, bytes, lines, and estimated tokens."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

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
    format: Annotated[
        Optional[str], typer.Option("--format", help="Output format: json, tsv, csv")
    ] = None,
) -> None:
    """Count files, bytes, lines, and estimated tokens (like wc for LLM context)."""
    from mm._mm import Scanner
    from mm.display import resolve_format

    fmt = resolve_format(format)

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

    # Add information-theoretic density metrics.
    total_mb = total_bytes / (1024 * 1024) if total_bytes else 0
    if total_mb > 0:
        result["tok_per_mb"] = round(total_tokens / total_mb)
    if kind_stats:
        for k, s in kind_stats.items():
            mb = s["bytes"] / (1024 * 1024) if s["bytes"] else 0
            if mb > 0:
                s["tok_per_mb"] = round(s["tokens"] / mb)
            if k == "image" and s["files"] > 0:
                s["tok_per_img"] = round(s["tokens"] / s["files"])

    if fmt == "json":
        from mm.display import json_dumps

        print(json_dumps(result))
        return

    from mm.display import format_number, format_size

    if fmt in ("tsv", "csv"):
        sep = "\t" if fmt == "tsv" else ","
        tok_mb = result.get("tok_per_mb", 0)
        print(f"files{sep}size{sep}lines{sep}tokens{sep}tok/MB")
        print(f"{total_files}{sep}{format_size(total_bytes)}{sep}{format_number(total_lines)}{sep}{format_number(total_tokens)}{sep}{format_number(tok_mb) if tok_mb else '—'}")
        if by_kind:
            print(f"\nkind{sep}files{sep}size{sep}lines{sep}tokens{sep}tok/MB")
            for k, s in sorted(kind_stats.items()):
                stm = s.get("tok_per_mb")
                print(
                    f"{k}{sep}{s['files']}{sep}{format_size(int(s['bytes']))}"
                    f"{sep}{format_number(int(s['lines']))}{sep}{format_number(int(s['tokens']))}"
                    f"{sep}{format_number(stm) if stm else '—'}"
                )
        return

    from mm.display import KIND_STYLES, output_console

    # Auto-enable by-kind when multiple kinds exist (richer default).
    if not by_kind and len(kind_stats) > 1:
        by_kind = True

    if by_kind:
        from rich.table import Table as RichTable
        from rich.text import Text

        from rich import box

        caption = f"{total_files:,} files  {format_size(total_bytes)}"

        tbl = RichTable(
            caption=caption,
            caption_style="dim",
            caption_justify="right",
            show_header=True,
            header_style="bold white",
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
        tbl.add_column("tok/MB", justify="right", style="dim")

        for k in sorted(kind_stats.keys()):
            s = kind_stats[k]
            style = KIND_STYLES.get(k, "dim")
            tok_mb = s.get("tok_per_mb")
            tok_mb_str = format_number(tok_mb) if tok_mb else "—"
            tbl.add_row(
                Text(k, style=style),
                f"{int(s['files']):,}",
                format_size(int(s["bytes"])),
                format_number(int(s["lines"])),
                format_number(int(s["tokens"])),
                tok_mb_str,
            )

        total_tok_mb = round(total_tokens / (total_bytes / (1024 * 1024))) if total_bytes else 0
        tbl.add_section()
        tbl.add_row(
            Text("total", style="bold"),
            f"[bold]{total_files:,}[/bold]",
            f"[bold]{format_size(total_bytes)}[/bold]",
            f"[bold]{format_number(total_lines)}[/bold]",
            f"[bold]{format_number(total_tokens)}[/bold]",
            f"[bold]{format_number(total_tok_mb)}[/bold]" if total_tok_mb else "—",
        )

        output_console.print(tbl)
    else:
        from rich import box
        from rich.table import Table as RichTable

        caption = f"{total_files:,} files  {format_size(total_bytes)}"

        tbl = RichTable(
            caption=caption,
            caption_style="dim",
            caption_justify="right",
            show_header=True,
            header_style="bold white",
            padding=(0, 1),
            border_style="dim",
            expand=False,
            box=box.ROUNDED,
        )
        tbl.add_column("metric", style="dim")
        tbl.add_column("value", justify="right")
        tbl.add_row("files", f"[bold bright_blue]{total_files:,}[/bold bright_blue]")
        tbl.add_row("size", f"[bold bright_blue]{format_size(total_bytes)}[/bold bright_blue]")
        tbl.add_row("lines (est.)", f"[bold]{format_number(total_lines)}[/bold]")
        tbl.add_row("tokens (est.)", f"[bold bright_green]{format_number(total_tokens)}[/bold bright_green]")

        output_console.print(tbl)
