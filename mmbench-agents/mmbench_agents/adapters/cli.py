"""Generic CLI adapter for headless assistants (Claude, Codex, Gemini, …).

Drives an assistant binary in non-interactive ("print") mode inside the sandbox
and recovers what it did from stdout. Each assistant is registered by name with
an argv builder; availability is gated on the binary being present, so a host
without a given CLI simply records the trial as skipped rather than failing.

Real assistants must inspect the corpus themselves — this adapter passes only
the task prompt (with ``CORPUS`` resolved to the sandbox path) and never names
an ``mm`` command.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Callable

from mmbench_agents.adapters import AdapterRequest, AdapterResult, AssistantAdapter, register
from mmbench_agents.types import FailureMode, MmCondition

_MM_CALL = re.compile(r"\bmm\s+(find|sql|peek|wc|grep|cat)\b")
_MAX_OUTPUT = 20_000

_ArgvBuilder = Callable[[str], list[str]]
_ARGV: dict[str, _ArgvBuilder] = {
    "claude": lambda prompt: ["claude", "-p", prompt],
    "codex": lambda prompt: ["codex", "exec", prompt],
    "gemini": lambda prompt: ["gemini", "-p", prompt],
}

_PREAMBLE = (
    "You are operating in the current working directory with whatever native tools are "
    "available. Investigate as needed, then answer the task. End your response with the "
    "required JSON object inside a ```json code block and nothing after it.\n\n"
)


class CliAdapter(AssistantAdapter):
    """Run a headless assistant CLI as a subprocess.

    Args:
        name: Leaderboard/registry name.
        command: Binary to invoke (also the availability preflight target).
    """

    def __init__(self, name: str, command: str) -> None:
        self.name = name
        self.command = command

    def available(self) -> bool:
        """True when the assistant binary is on ``PATH``."""
        return shutil.which(self.command) is not None

    def _prompt(self, request: AdapterRequest) -> str:
        corpus = str((request.workdir / "corpus").resolve())
        return _PREAMBLE + request.task.prompt.replace("CORPUS", corpus)

    def run(self, request: AdapterRequest) -> AdapterResult:
        build = _ARGV.get(request.assistant.command or self.command)
        if build is None:
            return AdapterResult(failure_mode=FailureMode.ERROR, raw_output="no argv builder")
        argv = build(self._prompt(request))
        try:
            proc = subprocess.run(
                argv,
                cwd=request.workdir,
                env=request.env,
                capture_output=True,
                text=True,
                timeout=request.timeout_s,
            )
        except subprocess.TimeoutExpired:
            return AdapterResult(failure_mode=FailureMode.TIMEOUT)
        except OSError as exc:
            return AdapterResult(failure_mode=FailureMode.ERROR, raw_output=str(exc))

        output = (proc.stdout or "") + (proc.stderr or "")
        commands = [f"mm {m.group(1)}" for m in _MM_CALL.finditer(output)]
        allowed = request.mm_condition is MmCondition.MM
        failure = FailureMode.NONE
        if proc.returncode != 0 and not proc.stdout:
            failure = FailureMode.ERROR
        return AdapterResult(
            raw_output=output[:_MAX_OUTPUT],
            tool_calls=len(commands),
            mm_calls=len(commands) if allowed else 0,
            mm_commands=commands,
            failure_mode=failure,
        )


for _name in ("claude", "codex", "gemini"):
    register(CliAdapter(_name, _name))
