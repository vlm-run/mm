"""mm CLI -- Unix-philosophy multimodal context management."""

from __future__ import annotations

import atexit
import signal
import sys
from time import perf_counter
from typing import Annotated, Optional

import typer

# Restore default SIGPIPE handling so piping to head/tail/etc. doesn't
# produce "BrokenPipeError: [Errno 32] Broken pipe" on stderr.
if hasattr(signal, "SIGPIPE"):
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
else:
    # Windows: no SIGPIPE, suppress BrokenPipeError at exit instead.
    _orig_excepthook = sys.excepthook

    def _quiet_broken_pipe(exc_type, exc_val, exc_tb):  # type: ignore[no-untyped-def]
        if exc_type is BrokenPipeError:
            sys.exit(141)
        _orig_excepthook(exc_type, exc_val, exc_tb)

    sys.excepthook = _quiet_broken_pipe

from mm import __version__
from mm.commands import bench, cat, find, grep, sql, wc
from mm.commands.config import config_app
from mm.commands.profile import profile_app

_ART = [
    "███╗   ███╗███╗   ███╗",
    "████╗ ████║████╗ ████║",
    "██╔████╔██║██╔████╔██║",
    "██║╚██╔╝██║██║╚██╔╝██║",
    "██║ ╚═╝ ██║██║ ╚═╝ ██║",
    "╚═╝     ╚═╝╚═╝     ╚═╝",
]

_STEEL_BLUE = "#4682B4"


def _print_banner() -> None:
    """Print the mm banner with a silver-to-steel-blue gradient."""
    from rich.console import Console
    from rich.text import Text

    console = Console(stderr=True)
    console.print()

    if console.width >= 50:
        # Right-side labels aligned to art lines 1–4
        _right = {
            1: "  ◈ pdf · ⬡ image · ▶ video",
            2: "  ♫ audio · ⟨/⟩ code",
            3: "  ≡ data · T text",
        }
        art_width = max(len(line) for line in _ART)

        # Silver (#C0D0E8) → Steel blue (#4682B4)
        n = len(_ART)
        s, e = (0xC0, 0xD0, 0xE8), (0x46, 0x82, 0xB4)
        for i, line in enumerate(_ART):
            t = i / max(n - 1, 1)
            r = int(s[0] + (e[0] - s[0]) * t)
            g = int(s[1] + (e[1] - s[1]) * t)
            b = int(s[2] + (e[2] - s[2]) * t)
            padded = line.ljust(art_width)
            row = Text(f"  {padded}", style=f"#{r:02x}{g:02x}{b:02x}")
            if i in _right:
                row.append_text(Text(_right[i], style="dim"))
            console.print(row)

        console.print(
            f"  [bold {_STEEL_BLUE}]mm (v{__version__})[/bold {_STEEL_BLUE}]"
            " [dim]— High-performance multimodal context management[/dim]"
        )
    else:
        console.print(f"  [bold {_STEEL_BLUE}]mm (v{__version__})[/bold {_STEEL_BLUE}]")

    console.print()


app = typer.Typer(
    name="mm",
    no_args_is_help=False,
    pretty_exceptions_enable=False,
)

_TIMED_COMMANDS = {"find", "cat", "grep", "sql", "wc"}


@app.callback(invoke_without_command=True)
def _main(
    ctx: typer.Context,
    profile: Annotated[
        Optional[str],
        typer.Option("--profile", "-p", help="Config profile to use (see: mm profile list)"),
    ] = None,
    color: Annotated[
        str, typer.Option("--color", help="Color output: auto, always, never")
    ] = "auto",
    version: Annotated[bool, typer.Option("--version", "-v", help="Show version and exit")] = False,
) -> None:
    """High-performance multimodal context management."""
    if version:
        typer.echo(f"mm v{__version__}")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        _print_banner()
        typer.echo(ctx.get_help())
        raise typer.Exit()

    start_time = perf_counter()

    from mm.config import set_cli_overrides
    from mm.display import display_elapsed_wrapper, set_color_mode

    set_cli_overrides(profile=profile)
    if color != "auto":
        set_color_mode(color)

    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd in _TIMED_COMMANDS:
        _check_exit, _display_elapsed = display_elapsed_wrapper(start_time)
        sys.exit = _check_exit
        atexit.register(_display_elapsed)


app.command(name="bench")(bench.bench_cmd)
app.command(name="find")(find.find_cmd)
app.command(name="cat")(cat.cat_cmd)
app.command(name="grep")(grep.grep_cmd)
app.command(name="sql")(sql.sql_cmd)
app.command(name="wc")(wc.wc_cmd)
app.add_typer(config_app, name="config")
app.add_typer(profile_app, name="profile")


if __name__ == "__main__":
    app()
