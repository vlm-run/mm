"""Optional Logfire OpenAI instrumentation. No-op unless logfire + LOGFIRE_TOKEN are present."""

from __future__ import annotations

import os
from contextlib import nullcontext
from functools import cache
from typing import Any, ContextManager


@cache
def configure_logfire(service_name: str = "mm") -> None:
    """Configure Logfire and instrument the OpenAI SDK. Runs at most once per process."""
    try:
        import logfire
    except ImportError:
        return
    logfire.configure(
        send_to_logfire="if-token-present",
        service_name=service_name,
        token=os.getenv("LOGFIRE_TOKEN") or None,
        scrubbing=False,
    )
    logfire.instrument_openai()


def cli_span(**attrs: Any) -> ContextManager[Any]:
    """Return an ``mm.cli`` Logfire span (or a no-op) wrapping the current command."""
    if not os.getenv("LOGFIRE_TOKEN"):
        return nullcontext()
    try:
        import logfire
    except ImportError:
        return nullcontext()
    configure_logfire()
    fmt = ", ".join(f"{k}={{{k}}}" for k in attrs)
    return logfire.span(f"mm.cli [{fmt}]", _span_name="mm.cli", **attrs)
