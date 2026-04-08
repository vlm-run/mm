"""mm CLI -- Unix-philosophy multi-modal context management."""

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

app = typer.Typer(
    name="mm",
    help=f"High-performance multi-modal context management - v{__version__}.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

_TIMED_COMMANDS = {"find", "cat", "grep", "sql", "wc"}


@app.callback()
def _main(
    profile: Annotated[
        Optional[str],
        typer.Option("--profile", "-p", help="Config profile to use (see: mm profile list)"),
    ] = None,
    color: Annotated[
        str, typer.Option("--color", help="Color output: auto, always, never")
    ] = "auto",
) -> None:
    """High-performance multi-modal context management."""
    start_time = perf_counter()

    from mm.config import set_cli_overrides
    from mm.display import display_elapsed, set_color_mode

    set_cli_overrides(profile=profile)
    if color != "auto":
        set_color_mode(color)

    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd in _TIMED_COMMANDS:
        atexit.register(display_elapsed, start_time)


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
