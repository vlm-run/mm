"""Pipe detection and stdin/stdout helpers for Unix-philosophy composability."""

from __future__ import annotations

import select
import sys


def is_piped_input() -> bool:
    """Check if stdin is being piped (not a TTY) AND has data ready."""
    if sys.stdin.isatty():
        return False
    try:
        ready, _, _ = select.select([sys.stdin], [], [], 0.0)
        return bool(ready)
    except (ValueError, OSError):
        return False


def is_piped_output() -> bool:
    """Check if stdout should receive plain (machine-readable) output.

    Uses Rich Console's terminal detection which inspects TERM, COLORTERM,
    and other env vars — more reliable than bare sys.stdout.isatty() in
    pseudo-terminal environments (e.g. IDE shells, tmux).
    """
    from vlmctx.display import output_console

    return not output_console.is_terminal


def read_paths_from_stdin() -> list[str]:
    """Read newline-delimited paths from stdin when piped."""
    if not is_piped_input():
        return []
    return [line.strip() for line in sys.stdin if line.strip()]
