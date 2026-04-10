"""mm wc -- count files, bytes, lines, and estimated tokens."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from mm.pipe import read_paths_from_stdin

TOKEN_CHARS_RATIO = 4

# Canonical field names — used in data dicts, JSON keys, column headers, row
# labels.  Every output format (json, tsv, csv, rich) uses these exact strings
# so the output is identical regardless of --format.
F_FILES = "files"
F_SIZE = "size"
F_LINES = "lines (est.)"
F_TOKENS = "tokens (est.)"
F_TOK_MB = "tok_per_mb"
F_TOK_IMG = "tok_per_img"


def wc_cmd(
    directory: Annotated[Path, typer.Argument(help="Directory to count")] = Path("."),
    kind: Annotated[Optional[str], typer.Option("--kind", "-k", help="Filter by kind")] = None,
    by_kind: Annotated[bool, typer.Option("--by-kind", help="Break down by file kind")] = False,
    format: Annotated[
        Optional[str],
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
    from mm._mm import Scanner
    from mm.display import console, resolve_format

    if not Path(directory).exists():
        console.print(f"[red]Directory not found: {directory}[/red]")
        raise typer.Exit(1)

    fmt = resolve_format(format)
    root = Path(directory).resolve()

    stdin_paths = read_paths_from_stdin()

    scanner = Scanner(str(root))
    scanner.scan()

    import json as json_mod

    if stdin_paths:
        # Piped input: compute stats only for the specified files.
        kind_stats, total_files, total_size, total_tokens, total_lines = _wc_from_paths(
            root, stdin_paths, kind
        )
    else:
        # Rust handles all kinds except documents (which need pypdfium2).
        # Rust JSON uses internal names; we normalize to canonical field names here.
        base = json_mod.loads(scanner.wc(kind=kind))
        kind_stats = {}
        for k, s in base.get("by_kind", {}).items():
            kind_stats[k] = {
                F_FILES: s["files"],
                F_SIZE: s["bytes"],
                F_LINES: s["lines"],
                F_TOKENS: s["tokens"],
            }
        total_files = base["files"]
        total_size = base["bytes"]
        total_tokens = base["estimated_tokens"]
        total_lines = base["lines"]

    doc_entries = []
    # Overlay document counts from Python (pypdfium2 extraction)
    if not stdin_paths and "document" in kind_stats and kind_stats["document"].get(F_FILES, 0) > 0:
        doc_entries = json_mod.loads(scanner.to_json_fast(kind="document"))
    if doc_entries:
        from mm.commands.cat import _l1_document

        for entry in doc_entries:
            content = _l1_document(root / entry["path"])
            char_len = len(content)
            lines = content.count("\n")
            if content and not content.endswith("\n"):
                lines += 1
            lines = max(1, lines)
            tokens = char_len // TOKEN_CHARS_RATIO

            total_tokens += tokens
            total_lines += lines

            if "document" not in kind_stats:
                kind_stats["document"] = {F_FILES: 0, F_SIZE: 0, F_TOKENS: 0, F_LINES: 0}
            kind_stats["document"][F_TOKENS] = int(kind_stats["document"].get(F_TOKENS, 0)) + tokens
            kind_stats["document"][F_LINES] = int(kind_stats["document"].get(F_LINES, 0)) + lines

    # Information-theoretic density metrics
    total_mb = total_size / (1024 * 1024) if total_size else 0
    tok_per_mb = round(total_tokens / total_mb) if total_mb > 0 else 0
    if kind_stats:
        for k, s in kind_stats.items():
            mb = s[F_SIZE] / (1024 * 1024) if s[F_SIZE] else 0
            if mb > 0:
                s[F_TOK_MB] = round(s[F_TOKENS] / mb)
            if k == "image" and s[F_FILES] > 0:
                s[F_TOK_IMG] = round(s[F_TOKENS] / s[F_FILES])

    # Auto-enable by-kind when multiple kinds exist
    if not by_kind and len(kind_stats) > 1:
        by_kind = True

    # Canonical result — same fields regardless of output format
    result: dict[str, int | float | dict] = {
        F_FILES: total_files,
        F_SIZE: total_size,
        F_LINES: total_lines,
        F_TOKENS: total_tokens,
        F_TOK_MB: tok_per_mb,
    }
    if by_kind:
        result["by_kind"] = kind_stats

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

    from mm.display import KIND_STYLES, output_console

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
            header_style="bold white",
            padding=(0, 1),
            border_style="dim",
            expand=False,
            box=box.ROUNDED,
        )
        tbl.add_column("kind", style="cyan", no_wrap=True)
        tbl.add_column(F_FILES, justify="right")
        tbl.add_column(F_SIZE, justify="right", style="bright_blue")
        tbl.add_column(F_LINES, justify="right")
        tbl.add_column(F_TOKENS, justify="right", style="bright_green")
        tbl.add_column(F_TOK_MB, justify="right", style="dim")

        for k in sorted(kind_stats.keys()):
            s = kind_stats[k]
            style = KIND_STYLES.get(k, "dim")
            tok_mb_str = format_number(s[F_TOK_MB]) if s.get(F_TOK_MB) else "—"
            tbl.add_row(
                Text(k, style=style),
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
            header_style="bold white",
            padding=(0, 1),
            border_style="dim",
            expand=False,
            box=box.ROUNDED,
        )
        tbl.add_column("metric", style="dim")
        tbl.add_column("value", justify="right")
        tbl.add_row(F_FILES, f"[bold bright_blue]{total_files:,}[/bold bright_blue]")
        tbl.add_row(F_SIZE, f"[bold bright_blue]{format_size(total_size)}[/bold bright_blue]")
        tbl.add_row(F_LINES, f"[bold]{format_number(total_lines)}[/bold]")
        tbl.add_row(
            F_TOKENS,
            f"[bold bright_green]{format_number(total_tokens)}[/bold bright_green]",
        )
        tbl.add_row(
            F_TOK_MB,
            f"[bold]{format_number(tok_per_mb)}[/bold]" if tok_per_mb else "—",
        )

        output_console.print(tbl)


# ---------------------------------------------------------------------------
# Piped-input helper
# ---------------------------------------------------------------------------

_IMAGE_EXTS = frozenset((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".svg"))
_VIDEO_EXTS = frozenset((".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"))
_AUDIO_EXTS = frozenset((".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus"))
_DOC_EXTS = frozenset((".pdf", ".docx", ".pptx"))
_CODE_EXTS = frozenset(
    (".py", ".rs", ".js", ".ts", ".go", ".c", ".cpp", ".h", ".java", ".rb", ".sh", ".toml", ".yaml", ".yml")
)


def _kind_from_ext(ext: str) -> str:
    ext = ext.lower()
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _VIDEO_EXTS:
        return "video"
    if ext in _AUDIO_EXTS:
        return "audio"
    if ext in _DOC_EXTS:
        return "document"
    if ext in _CODE_EXTS:
        return "code"
    return "other"


def _wc_from_paths(
    root: Path, paths: list[str], kind_filter: str | None
) -> tuple[dict[str, dict[str, int | float]], int, int, int, int]:
    """Compute wc stats for a specific set of piped file paths."""
    kind_stats: dict[str, dict[str, int | float]] = {}
    total_files = 0
    total_size = 0
    total_tokens = 0
    total_lines = 0

    for p_str in paths:
        p = Path(p_str)
        if not p.is_absolute():
            p = root / p
        if not p.is_file():
            continue

        fkind = _kind_from_ext(p.suffix)
        if kind_filter and fkind != kind_filter:
            continue

        stat = p.stat()
        fsize = stat.st_size

        # Estimate lines/tokens for text-like files
        if fkind in ("code", "other", "text"):
            try:
                content = p.read_text(errors="replace")
                flines = content.count("\n") or 1
                ftokens = len(content) // TOKEN_CHARS_RATIO
            except Exception:
                flines = fsize // 40  # rough estimate
                ftokens = fsize // TOKEN_CHARS_RATIO
        elif fkind == "document":
            try:
                from mm.commands.cat import _l1_document

                content = _l1_document(p)
                flines = max(1, content.count("\n"))
                ftokens = len(content) // TOKEN_CHARS_RATIO
            except Exception:
                flines = 0
                ftokens = 0
        else:
            # binary: image, video, audio — no text lines/tokens
            flines = 0
            ftokens = 0

        total_files += 1
        total_size += fsize
        total_lines += flines
        total_tokens += ftokens

        if fkind not in kind_stats:
            kind_stats[fkind] = {F_FILES: 0, F_SIZE: 0, F_LINES: 0, F_TOKENS: 0}
        kind_stats[fkind][F_FILES] = int(kind_stats[fkind][F_FILES]) + 1
        kind_stats[fkind][F_SIZE] = int(kind_stats[fkind][F_SIZE]) + fsize
        kind_stats[fkind][F_LINES] = int(kind_stats[fkind][F_LINES]) + flines
        kind_stats[fkind][F_TOKENS] = int(kind_stats[fkind][F_TOKENS]) + ftokens

    return kind_stats, total_files, total_size, total_tokens, total_lines
