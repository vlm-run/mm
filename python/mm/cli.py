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
from mm.commands.config import config_app
from mm.commands.profile import profile_app

app = typer.Typer(
    name="mm",
    help=f"High-performance multi-modal context management - v{__version__}.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

_TIMED_COMMANDS = {"find", "cat", "grep", "sql", "wc"}

# Each top-level command lives in its own module. Importing a module
# pulls in its transitive deps (openai, pyarrow, pypdfium2, ffmpeg
# shims, …), so we register only the command the user is actually
# running. For `mm --help`, `mm --version`, or an unrecognised command
# we fall back to registering everything so the help output stays
# complete.
_COMMAND_MODULES: dict[str, tuple[str, str]] = {
    "bench": ("mm.commands.bench", "bench_cmd"),
    "cat": ("mm.commands.cat", "cat_cmd"),
    "find": ("mm.commands.find", "find_cmd"),
    "grep": ("mm.commands.grep", "grep_cmd"),
    "sql": ("mm.commands.sql", "sql_cmd"),
    "wc": ("mm.commands.wc", "wc_cmd"),
}

# Sub-apps are registered unconditionally (they're tiny).
_SUB_APPS = {"config", "profile"}


def _detect_subcommand(argv: list[str]) -> Optional[str]:
    """Return the first argv token that names a known command or sub-app.

    Scans in order and ignores anything else (flags, values, paths) so
    unusual flag placement (``mm --profile X find …``) still hits the
    fast path.
    """
    for arg in argv:
        if arg in _COMMAND_MODULES or arg in _SUB_APPS:
            return arg
    return None


def _is_cli_entrypoint() -> bool:
    """True when imported by the installed ``mm`` script or ``python -m mm``.

    When imported from a test runner, a notebook, or any other host we
    cannot trust ``sys.argv`` to describe a ``mm`` invocation, so we
    fall back to eagerly registering every command.
    """
    if not sys.argv:
        return False
    prog = sys.argv[0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return prog in {"mm", "mm.exe", "__main__.py"}


def _register_one(name: str) -> None:
    """Import a single command module and register it with Typer."""
    import importlib

    modname, attr = _COMMAND_MODULES[name]
    mod = importlib.import_module(modname)
    app.command(name=name)(getattr(mod, attr))


def _register_all() -> None:
    """Import and register every top-level command.

    Used for ``mm --help``, ``mm --version``, any non-CLI host (tests,
    notebooks), or when the user invokes an unknown command so help
    output lists everything.
    """
    for name in _COMMAND_MODULES:
        _register_one(name)


@app.callback(invoke_without_command=True)
def _main(
    profile: Annotated[
        Optional[str],
        typer.Option("--profile", "-p", help="Config profile to use (see: mm profile list)"),
    ] = None,
    color: Annotated[
        str, typer.Option("--color", help="Color output: auto, always, never")
    ] = "auto",
    version: Annotated[bool, typer.Option("--version", "-v", help="Show version and exit")] = False,
) -> None:
    """High-performance multi-modal context management."""
    if version:
        typer.echo(f"mm v{__version__}")
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


app.add_typer(config_app, name="config")
app.add_typer(profile_app, name="profile")

if _is_cli_entrypoint():
    _sub = _detect_subcommand(sys.argv[1:])
    if _sub in _COMMAND_MODULES:
        _register_one(_sub)
    elif _sub in _SUB_APPS:
        # Sub-apps are already wired up; skip heavy top-level commands.
        pass
    else:
        _register_all()
else:
    _register_all()


if __name__ == "__main__":
    app()
