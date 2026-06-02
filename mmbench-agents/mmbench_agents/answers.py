"""Extract a structured answer from an assistant's free-text output.

Assistants are instructed to end with a JSON object. This module recovers that
object robustly: it prefers a fenced ```json block, then falls back to the last
balanced top-level ``{...}`` span. Returns ``None`` when nothing parses, which
the harness records as :data:`FailureMode.NO_ANSWER`.
"""

from __future__ import annotations

import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _balanced_spans(text: str) -> list[str]:
    """Yield top-level ``{...}`` substrings, ignoring braces inside strings."""
    spans: list[str] = []
    depth = 0
    start = -1
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start >= 0:
                spans.append(text[start : i + 1])
    return spans


def parse_answer(text: str) -> dict | None:
    """Parse the answer object from ``text`` or return ``None`` if absent."""
    candidates = _FENCE.findall(text)
    candidates += reversed(_balanced_spans(text))
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None
