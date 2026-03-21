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
    """Check if stdout is piped (not a terminal).

    Respects --color always/never: when color is forced on, we treat
    output as non-piped (rich) even if stdout is a pipe.
    """
    from vlmctx.display import _color_override

    if _color_override is True:
        return False
    if _color_override is False:
        return True
    return not sys.stdout.isatty()


def read_paths_from_stdin() -> list[str]:
    """Read paths from stdin when piped.

    Handles two formats transparently:
      1. Bare paths (one per line):  ``src/main.py``
      2. TSV with path in last column:  ``code\\t4301\\tsrc/main.py``

    The heuristic is simple: if a line contains a tab, take the last field.
    This lets ``vlmctx find | vlmctx cat`` work regardless of whether
    find emits bare paths or the richer ``kind\\tsize\\tpath`` format.
    """
    if not is_piped_input():
        return []
    paths: list[str] = []
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        # TSV: take last field (the path column)
        if "\t" in line:
            line = line.rsplit("\t", 1)[-1]
        paths.append(line)
    return paths
