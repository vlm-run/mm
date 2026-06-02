"""Assistant adapters: a pluggable registry of harnesses under evaluation.

An adapter knows how to drive one universal assistant (Claude, Codex, Gemini,
a deterministic mock, …) on a single task inside a prepared sandbox, and to
report back what it did. The harness owns the sandbox, environment, and
scoring; adapters only run the agent.

Register an adapter under a name and look it up via :func:`get`. The built-in
mock and CLI adapters self-register on import.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from mmbench_agents.tasks import TaskSpec
from mmbench_agents.types import AssistantSpec, FailureMode, MmCondition, Profile


@dataclass
class AdapterRequest:
    """Everything an adapter needs to run one trial.

    Args:
        assistant: The assistant spec (carries the binary name for CLI adapters).
        task: The task being attempted.
        workdir: Sandbox directory; the corpus lives at ``workdir/corpus``.
        mm_condition: Whether ``mm`` is available this trial.
        profile: The ``mm`` backend profile (``Profile.none()`` at baseline).
        env: Environment for any subprocess (fresh ``MM_*`` paths already set).
        max_turns: Soft cap on agent turns.
        timeout_s: Wall-clock budget for the whole attempt.
    """

    assistant: AssistantSpec
    task: TaskSpec
    workdir: Path
    mm_condition: MmCondition
    profile: Profile
    env: dict[str, str]
    max_turns: int
    timeout_s: float
    repeat: int = 0


@dataclass
class AdapterResult:
    """What an adapter reports after attempting a trial.

    ``wall_s`` is optional: when zero the harness uses its own measured wall
    time; adapters (e.g. the mock) may set it to provide a synthetic duration.
    """

    raw_output: str = ""
    turns: int = 0
    tool_calls: int = 0
    mm_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    wall_s: float = 0.0
    mm_commands: list[str] = field(default_factory=list)
    failure_mode: FailureMode = FailureMode.NONE


class AssistantAdapter(ABC):
    """Drives a single assistant harness on one task."""

    name: str

    def available(self) -> bool:
        """Whether this adapter can run now (binary present, keys set, …)."""
        return True

    @abstractmethod
    def run(self, request: AdapterRequest) -> AdapterResult:
        """Attempt the task and report metrics, output, and any failure."""


_REGISTRY: dict[str, AssistantAdapter] = {}


def register(adapter: AssistantAdapter) -> AssistantAdapter:
    """Register ``adapter`` under ``adapter.name`` (idempotent overwrite)."""
    _REGISTRY[adapter.name] = adapter
    return adapter


def get(name: str) -> AssistantAdapter:
    """Look up a registered adapter by name."""
    return _REGISTRY[name]


def available_names() -> list[str]:
    """Names of registered adapters that report themselves runnable."""
    return sorted(name for name, a in _REGISTRY.items() if a.available())


from mmbench_agents.adapters import cli as cli  # noqa: E402,F401
from mmbench_agents.adapters import mock as mock  # noqa: E402,F401
