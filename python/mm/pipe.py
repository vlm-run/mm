"""Pipe detection and stdin/stdout helpers for Unix-philosophy composability."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def is_piped_input() -> bool:
    """Check if stdin is being piped (not a TTY)"""
    return not sys.stdin.isatty()


def is_piped_output() -> bool:
    """Check if stdout is piped (not a terminal).

    Respects --color always/never: when color is forced on, we treat
    output as non-piped (rich) even if stdout is a pipe.
    """
    from mm.display import _color_override

    if _color_override is True:
        return False
    if _color_override is False:
        return True
    return not sys.stdout.isatty()


# Header values that indicate a TSV/CSV header row rather than data.
_HEADER_TOKENS = frozenset(
    ("path", "uri", "name", "file", "kind", "size", "ext", "mime", "column", "type", "table")
)


def read_paths_from_stdin() -> list[str]:
    """Read file paths from stdin when piped.

    Handles three input formats transparently:

      1. **Bare paths** (one per line)::

           src/main.py

      2. **TSV / CSV** with a path-like field in the last column::

           code\\t4301\\tsrc/main.py

         Header rows are detected and skipped automatically.

      3. **JSON** — an array of objects with a ``"path"`` key, or an
         array of plain strings::

           [{"path": "src/main.py", ...}, ...]
           ["src/main.py", ...]

    This lets ``mm find | mm cat`` and ``mm find -f json | mm cat``
    both work seamlessly.
    """
    if not is_piped_input():
        return []

    raw = sys.stdin.read()
    stripped = raw.strip()
    if not stripped:
        return []

    # ── JSON input ───────────────────────────────────────────────
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            data = json.loads(stripped)
            return _paths_from_json(data)
        except (json.JSONDecodeError, TypeError):
            pass  # fall through to line-based parsing

    # ── Line-based input (bare paths or TSV/CSV) ────────────────
    paths: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # TSV: take last field (the path column)
        if "\t" in line:
            value = line.rsplit("\t", 1)[-1]
        elif "," in line:
            # CSV: take last field
            value = line.rsplit(",", 1)[-1].strip().strip('"')
        else:
            value = line
        # Skip header rows
        if value.lower() in _HEADER_TOKENS:
            continue
        paths.append(value)
    return paths


def resolve_piped_paths(paths: list[str]) -> set[str]:
    """Resolve piped paths to be relative to a scan *root*."""
    result: set[str] = set()
    for p in paths:
        result.add(str(Path(p).resolve()))
    return result


def _paths_from_json(data: object) -> list[str]:
    """Extract paths from parsed JSON (array of objects or strings)."""
    if isinstance(data, dict):
        # Single object — look for a path key
        for key in ("path", "uri", "name"):
            if key in data and isinstance(data[key], str):
                return [data[key]]
        return []
    if not isinstance(data, list) or not data:
        return []
    first = data[0]
    if isinstance(first, str):
        return [s for s in data if isinstance(s, str)]
    if isinstance(first, dict):
        # Find the best path key
        for key in ("path", "uri", "name"):
            if key in first:
                return [row[key] for row in data if isinstance(row, dict) and key in row]
    return []
