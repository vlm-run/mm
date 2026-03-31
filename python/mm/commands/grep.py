"""mm grep -- content search across files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Optional

import typer

from mm.pipe import read_paths_from_stdin


def grep_cmd(
    pattern: Annotated[str, typer.Argument(help="Search pattern (regex)")],
    directory: Annotated[Path, typer.Argument(help="Directory to search")] = Path("."),
    kind: Annotated[Optional[str], typer.Option("--kind", "-k", help="Filter by file kind")] = None,
    ext: Annotated[
        Optional[str], typer.Option("--ext", "-e", help="Filter by extension(s)")
    ] = None,
    context_lines: Annotated[int, typer.Option("-C", help="Context lines around match")] = 0,
    count: Annotated[
        bool, typer.Option("--count", "-c", help="Show only match counts per file")
    ] = False,
    level: Annotated[int, typer.Option("--level", "-l", help="Processing level")] = 1,
    format: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: json, tsv, csv, dataset-jsonl, dataset-hf"),
    ] = None,
) -> None:
    """Search file contents -- text and semantic (like rg/grep)."""
    from mm.display import resolve_format

    fmt = resolve_format(format)

    from mm.context import Context

    ctx = Context(directory)
    if kind:
        ctx = ctx.filter(kind=kind)
    if ext:
        ctx = ctx.filter(ext=ext)

    stdin_paths = read_paths_from_stdin()

    try:
        regex = re.compile(pattern)
    except re.error as e:
        typer.echo(f"Invalid regex: {e}", err=True)
        raise typer.Exit(1)

    all_matches: list[dict] = []
    file_counts: dict[str, int] = {}

    files_to_search = ctx.files
    if stdin_paths:
        stdin_set = set(stdin_paths)
        files_to_search = [f for f in files_to_search if f.path in stdin_set]

    for f in files_to_search:
        try:
            full_path = ctx.root / f.path
            if f.is_binary and f.kind not in ("document",):
                continue

            if level >= 1 and f.kind == "document":
                from mm.commands.cat import _l1_document

                content = _l1_document(full_path)
            elif f.is_binary:
                continue
            else:
                content = full_path.read_text(errors="replace")
            lines = content.splitlines()

            file_match_count = 0
            for i, line in enumerate(lines):
                if regex.search(line):
                    file_match_count += 1
                    if not count:
                        match_entry: dict = {
                            "path": f.path,
                            "line_number": i + 1,
                            "line": line,
                        }
                        if context_lines > 0:
                            start = max(0, i - context_lines)
                            end = min(len(lines), i + context_lines + 1)
                            match_entry["context"] = lines[start:end]
                        all_matches.append(match_entry)

            if file_match_count > 0:
                file_counts[f.path] = file_match_count
        except Exception:
            continue

    # Exit 1 on no matches (standard grep/rg behaviour for composability).
    has_matches = bool(file_counts)

    if fmt in ("json", "dataset-jsonl", "dataset-hf"):
        from mm.display import emit_rows

        if count:
            # json emits the raw dict; dataset formats need a list of rows
            if fmt == "json":
                from mm.display import json_dumps

                print(json_dumps(file_counts))
            else:
                emit_rows(fmt, [{"path": p, "count": c} for p, c in file_counts.items()])
        else:
            emit_rows(fmt, all_matches)
        if not has_matches:
            raise typer.Exit(1)
        return

    if count:
        if fmt == "rich":
            from rich import box
            from rich.table import Table as RichTable

            from mm.display import output_console

            t = RichTable(
                caption=f"{sum(file_counts.values())} matches in {len(file_counts)} files",
                caption_style="dim",
                caption_justify="right",
                show_lines=False,
                padding=(0, 1),
                border_style="dim",
                header_style="bold white",
                box=box.ROUNDED,
            )
            t.add_column("file", style="white")
            t.add_column("matches", justify="right", style="bright_blue")
            for path, cnt in sorted(file_counts.items(), key=lambda x: -x[1]):
                t.add_row(path, str(cnt))
            output_console.print(t)
        else:
            for path, cnt in sorted(file_counts.items()):
                print(f"{path}:{cnt}")
        return

    total_matches = len(all_matches)
    total_files = len(file_counts)

    if fmt == "rich":
        from rich.text import Text

        from mm.display import output_console

        output_console.print()
        current_file = None
        for m in all_matches:
            if m["path"] != current_file:
                current_file = m["path"]
                output_console.print(f"[bold magenta]{current_file}[/bold magenta]")

            line_text = Text()
            line_text.append(f" {m['line_number']:>4} ", style="dim green")

            line = m["line"]
            parts = regex.split(line)
            found = regex.findall(line)
            for j, part in enumerate(parts):
                line_text.append(part)
                if j < len(found):
                    line_text.append(found[j], style="bold red on bright_black")
            output_console.print(line_text)

        output_console.print()
        output_console.print(
            f"[dim]{total_matches} match{'es' if total_matches != 1 else ''} "
            f"in {total_files} file{'s' if total_files != 1 else ''}[/dim]"
        )
    else:
        for m in all_matches:
            print(f"{m['path']}:{m['line_number']}:{m['line']}")

    if not has_matches:
        raise typer.Exit(1)
