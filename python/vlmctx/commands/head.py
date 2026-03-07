"""vlmctx head -- first N lines/pages/frames."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from vlmctx.commands.cat import _extract_l1_content
from vlmctx.pipe import is_piped_output


def head_cmd(
    files: Annotated[Optional[list[Path]], typer.Argument(help="Files to read")] = None,
    n: Annotated[int, typer.Option("-n", help="Number of lines/pages")] = 10,
    level: Annotated[int, typer.Option("--level", "-l", help="Processing level")] = 1,
) -> None:
    """First N lines/pages of a file (like head)."""
    from vlmctx.pipe import read_paths_from_stdin

    paths: list[str] = []

    stdin_paths = read_paths_from_stdin()
    if stdin_paths:
        paths.extend(stdin_paths)
    if files:
        paths.extend(str(f) for f in files)

    if not paths:
        typer.echo("Error: No files specified.", err=True)
        raise typer.Exit(1)

    use_rich = not is_piped_output()

    for file_path in paths:
        p = Path(file_path)
        if not p.exists():
            typer.echo(f"Error: {file_path} not found.", err=True)
            continue

        if level == 0:
            content = p.read_text(errors="replace")
        else:
            content = _extract_l1_content(p)

        all_lines = content.splitlines()
        lines = all_lines[:n]
        output = "\n".join(lines)

        if use_rich:
            from rich.panel import Panel
            from rich.text import Text

            from vlmctx.display import output_console

            subtitle = Text()
            subtitle.append(f"lines 1-{len(lines)}", style="dim")
            if len(all_lines) > n:
                subtitle.append(f" of {len(all_lines)}", style="dim")

            output_console.print(
                Panel(
                    output,
                    title=f"[bold]{p}[/bold]",
                    subtitle=subtitle,
                    expand=False,
                    border_style="blue",
                )
            )
        else:
            if len(paths) > 1:
                print(f"==> {p} <==")
            print(output)
