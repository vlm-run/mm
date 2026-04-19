"""Optional Logfire OpenAI instrumentation. No-op unless logfire + LOGFIRE_TOKEN are present."""

from __future__ import annotations

import os
from contextlib import nullcontext
from functools import cache
from typing import Any, ContextManager


@cache
def configure_logfire(service_name: str = "mm") -> None:
    """Configure Logfire and instrument the OpenAI SDK. Runs at most once per process.

    No-op when ``LOGFIRE_TOKEN`` is unset, ``logfire`` isn't installed, or
    configuration/instrumentation raises for any reason (version mismatch,
    missing OTel deps, etc.). Failure is cached so ``LlmBackend`` creation
    stays fast on subsequent calls.
    """
    if not os.getenv("LOGFIRE_TOKEN"):
        return
    try:
        import logfire

        logfire.configure(
            send_to_logfire="if-token-present",
            service_name=service_name,
            environment=os.getenv("LOGFIRE_ENVIRONMENT", "local"),
            token=os.getenv("LOGFIRE_TOKEN"),
            scrubbing=False,
        )
        logfire.instrument_openai()
    except Exception:
        return


def cli_span(*, command: str, profile: str, model: str) -> ContextManager[Any]:
    """Return an ``mm.cli`` Logfire span (or a no-op) wrapping the current command."""
    if not os.getenv("LOGFIRE_TOKEN"):
        return nullcontext()
    try:
        import logfire
    except ImportError:
        return nullcontext()
    configure_logfire()
    return logfire.span(
        "mm.cli.{command} [profile={profile}, model={model}]",
        _span_name=f"mm.cli.{command}",
        command=command,
        profile=profile,
        model=model,
    )
