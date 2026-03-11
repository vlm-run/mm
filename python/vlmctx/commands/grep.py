"""vlmctx grep -- content search across files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Optional

import typer

from vlmctx.pipe import is_piped_output, read_paths_from_stdin


def grep_cmd(
    pattern: Annotated[str, typer.Argument(help="Search pattern (regex)")],
    directory: Annotated[Path, typer.Argument(help="Directory to search")] = Path("."),
    kind: Annotated[Optional[str], typer.Option("--kind", "-k", help="Filter by file kind")] = None,
    ext: Annotated[
        Optional[str], typer.Option("--ext", "-e", help="Filter by extension(s)")
    ] = None,
    context_lines: Annotated[int, typer.Option("-C", help="Context lines around match")] = 0,
    count: Annotated[bool, typer.Option("--count", help="Show only match counts per file")] = False,
    level: Annotated[int, typer.Option("--level", "-l", help="Processing level")] = 1,
    json_output: Annotated[bool, typer.Option("--json", help="Force JSON output")] = False,
) -> None:
    """Search file contents -- text and semantic (like rg/grep)."""
    from vlmctx.context import Context

    ctx = Context(directory)
    if kind:
        ctx = ctx.filter(kind=kind)
    if ext:
        ctx = ctx.filter(ext=ext)

    stdin_paths = read_paths_from_stdin()
    use_rich = not is_piped_output() and not json_output

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
                from vlmctx.commands.cat import _extract_l1_content

                content = _extract_l1_content(full_path)
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

    if json_output:
        import json

        if count:
            print(json.dumps(file_counts, indent=2))
        else:
            print(json.dumps(all_matches, indent=2, default=str))
        return

    if count:
        if use_rich:
            from rich.table import Table as RichTable

            from vlmctx.display import output_console

            from rich import box

            t = RichTable(
                caption=f"{sum(file_counts.values())} matches in {len(file_counts)} files",
                caption_style="dim",
                show_lines=False,
                padding=(0, 1),
                border_style="dim",
                header_style="bold",
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

    if use_rich:
        from rich.text import Text

        from vlmctx.display import output_console

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
