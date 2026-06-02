"""mmbench-agents: an agent-capability benchmark for ``mm``.

Measures how well universal assistants accomplish hard, multi-turn,
action-based multimodal tasks — with and without ``mm`` — across model
profiles. The package provides a frozen corpus + independent ground truth, a
task catalogue with deterministic verifiers, a sandboxing trial harness with
pluggable assistant adapters, a SQLite scoring store, a sweep orchestrator, and
a Plotly/FastAPI dashboard. See ``README.md`` for the run/test guide.

Heavy, optional dependencies (Plotly, FastAPI) live in ``report``/``app`` and
are imported lazily, so importing this package stays dependency-free.
"""

from __future__ import annotations

from mmbench_agents.tasks import TASKS, TASKS_BY_ID, TaskSpec
from mmbench_agents.types import (
    AssistantSpec,
    FailureMode,
    MmCondition,
    Profile,
    Score,
    Scope,
    SubCheck,
    SweepMode,
    TrialKey,
    TrialMetrics,
    TrialResult,
    VerifierReport,
)

__all__ = [
    "TASKS",
    "TASKS_BY_ID",
    "TaskSpec",
    "AssistantSpec",
    "FailureMode",
    "MmCondition",
    "Profile",
    "Score",
    "Scope",
    "SubCheck",
    "SweepMode",
    "TrialKey",
    "TrialMetrics",
    "TrialResult",
    "VerifierReport",
]
