"""mm wc -- count files, bytes, lines, and estimated tokens."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from mm.results import F_FILES, F_LINES, F_SIZE, F_TOK_MB, F_TOKENS
from mm.utils import Format


def wc_cmd(
    directory: Annotated[Path, typer.Argument(help="Directory to count")] = Path("."),
    kind: Annotated[
        Optional[str],
        typer.Option(
            "--kind", "-k", help="Filter by kind (supports comma-separated, e.g. image,document)"
        ),
    ] = None,
    by_kind: Annotated[bool, typer.Option("--by-kind", help="Break down by file kind")] = False,
    format: Annotated[
        Optional[Format],
        typer.Option(
            "--format", "-f", help="Output format: json, tsv, csv, dataset-jsonl, dataset-hf"
        ),
    ] = None,
) -> None:
    """Count files, bytes, lines, and estimated tokens (like wc for LLM context).

    \b
    Examples:
      mm wc ~/project                        # summary panel
      mm wc ~/project --by-kind              # breakdown by file kind
      mm wc ~/project --kind code            # code files only
      mm wc ~/project --format json          # JSON output
    """
    from mm.display import console, resolve_format
    from mm.pipe import read_paths_from_stdin
    from mm.stats import compute_wc

    if not Path(directory).exists():
        console.print(f"Directory not found: {directory}")
        raise typer.Exit(1)

    fmt = resolve_format(format.value if format else None)
    root = Path(directory).resolve()
    stdin_paths = read_paths_from_stdin()

    # All computation lives in the library; the command only renders.
    stats = compute_wc(root, kind=kind, stdin_paths=stdin_paths or None)
    kind_stats = stats.by_kind
    total_files = stats.files
    total_size = stats.size
    total_tokens = stats.tokens
    total_lines = stats.lines
    tok_per_mb = stats.tok_per_mb

    # Auto-enable by-kind when multiple kinds exist
    if not by_kind and len(kind_stats) > 1:
        by_kind = True

    result = stats.to_dict(by_kind=by_kind)

    # ── Render ──────────────────────────────────────────────────────

    from mm.display import format_number, format_size

    if fmt in ("json", "dataset-jsonl", "dataset-hf"):
        from mm.display import emit_rows

        if fmt == "json":
            from mm.display import json_dumps

            print(json_dumps(result))
        else:
            if by_kind and kind_stats:
                rows = [{"kind": k, **s} for k, s in kind_stats.items()]
                emit_rows(fmt, rows)
            else:
                emit_rows(fmt, [result])
        return

    if fmt in ("tsv", "csv"):
        sep = "\t" if fmt == "tsv" else ","
        if by_kind:
            print(f"kind{sep}{F_FILES}{sep}{F_SIZE}{sep}{F_LINES}{sep}{F_TOKENS}{sep}{F_TOK_MB}")
            for k, s in sorted(kind_stats.items()):
                stm = s.get(F_TOK_MB)
                print(
                    f"{k}{sep}{s[F_FILES]}{sep}{format_size(int(s[F_SIZE]))}"
                    f"{sep}{format_number(int(s[F_LINES]))}{sep}{format_number(int(s[F_TOKENS]))}"
                    f"{sep}{format_number(stm) if stm else '—'}"
                )
            print(f"{'—' * 5}")
            print(
                f"total{sep}{total_files}{sep}{format_size(total_size)}"
                f"{sep}{format_number(total_lines)}{sep}{format_number(total_tokens)}"
                f"{sep}{format_number(tok_per_mb) if tok_per_mb else '—'}"
            )
        else:
            print(f"{F_FILES}{sep}{F_SIZE}{sep}{F_LINES}{sep}{F_TOKENS}{sep}{F_TOK_MB}")
            print(
                f"{total_files}{sep}{format_size(total_size)}{sep}{format_number(total_lines)}"
                f"{sep}{format_number(total_tokens)}{sep}{format_number(tok_per_mb) if tok_per_mb else '—'}"
            )
        return

    # ── Rich output ─────────────────────────────────────────────────

    from mm.display import output_console

    if by_kind:
        from rich import box
        from rich.table import Table as RichTable
        from rich.text import Text

        caption = f"{total_files:,} files  {format_size(total_size)}"

        tbl = RichTable(
            caption=caption,
            caption_style="dim",
            caption_justify="right",
            show_header=True,
            header_style="bold",
            padding=(0, 1),
            expand=False,
            box=box.ROUNDED,
        )
        tbl.add_column("kind", no_wrap=True)
        tbl.add_column(F_FILES, justify="right")
        tbl.add_column(F_SIZE, justify="right")
        tbl.add_column(F_LINES, justify="right")
        tbl.add_column(F_TOKENS, justify="right")
        tbl.add_column(F_TOK_MB, justify="right")

        for k in sorted(kind_stats.keys()):
            s = kind_stats[k]
            tok_mb_str = format_number(s[F_TOK_MB]) if s.get(F_TOK_MB) else "—"
            tbl.add_row(
                k,
                f"{int(s[F_FILES]):,}",
                format_size(int(s[F_SIZE])),
                format_number(int(s[F_LINES])),
                format_number(int(s[F_TOKENS])),
                tok_mb_str,
            )

        tbl.add_section()
        tbl.add_row(
            Text("total", style="bold"),
            f"[bold]{total_files:,}[/bold]",
            f"[bold]{format_size(total_size)}[/bold]",
            f"[bold]{format_number(total_lines)}[/bold]",
            f"[bold]{format_number(total_tokens)}[/bold]",
            f"[bold]{format_number(tok_per_mb)}[/bold]" if tok_per_mb else "—",
        )

        output_console.print(tbl)
    else:
        from rich import box
        from rich.table import Table as RichTable

        _caption = (
            f"{total_files:,} file{'s' if total_files > 1 else ''}  {format_size(total_size)}"
            if total_files > 1
            else None
        )
        tbl = RichTable(
            caption=_caption,
            caption_style="dim",
            caption_justify="right",
            show_header=True,
            header_style="bold",
            padding=(0, 1),
            expand=False,
            box=box.ROUNDED,
        )
        tbl.add_column("metric")
        tbl.add_column("value", justify="right")
        tbl.add_row(F_FILES, f"[bold]{total_files:,}[/bold]")
        tbl.add_row(F_SIZE, f"[bold]{format_size(total_size)}[/bold]")
        tbl.add_row(F_LINES, f"[bold]{format_number(total_lines)}[/bold]")
        tbl.add_row(
            F_TOKENS,
            f"[bold]{format_number(total_tokens)}[/bold]",
        )
        tbl.add_row(
            F_TOK_MB,
            f"[bold]{format_number(tok_per_mb)}[/bold]" if tok_per_mb else "—",
        )

        output_console.print(tbl)
