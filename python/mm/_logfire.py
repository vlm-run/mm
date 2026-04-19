"""Optional Logfire OpenAI instrumentation. No-op unless logfire + LOGFIRE_TOKEN are present."""

from __future__ import annotations

import os
from functools import cache


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
