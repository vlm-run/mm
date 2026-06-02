"""mmbench-agents: an agent-capability benchmark for ``mm``.

Measures how well universal assistants accomplish hard, multi-turn,
action-based multimodal tasks — with and without ``mm`` — across model
profiles. This package currently ships the foundational layer: the trial-matrix
types, a frozen corpus + independent ground truth, the task catalogue, and
deterministic verifiers. The trial harness, scoring store, and dashboard are
added in later slices (see ``README.md``).
"""

from __future__ import annotations

from mmbench_agents.tasks import TASKS, TASKS_BY_ID, TaskSpec
from mmbench_agents.types import MmCondition, Scope, SubCheck, SweepMode, VerifierReport

__all__ = [
    "TASKS",
    "TASKS_BY_ID",
    "TaskSpec",
    "MmCondition",
    "Scope",
    "SubCheck",
    "SweepMode",
    "VerifierReport",
]
