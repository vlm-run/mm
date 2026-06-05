"""Sweep orchestrator: build the trial matrix and run it, resumably.

A sweep is the cartesian product of assistants × profiles × tasks × repeats
crossed with the baseline/``mm`` conditions, with one rule: the baseline arm has
no backend, so it runs once under ``Profile.none()`` while the ``mm`` arm runs
under each configured profile. :class:`SweepMode` records intent (vary the
profile vs. vary the assistant) for the dashboard; the matrix itself is general.

Runs are idempotent: trials already in the store are skipped, so an interrupted
sweep resumes where it left off. A cost guard stops launching new trials once
the accumulated spend exceeds the configured budget.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from mmbench.harness import Harness
from mmbench.store import Store
from mmbench.tasks import TASKS, TaskSpec
from mmbench.types import (
    AssistantSpec,
    MmCondition,
    Profile,
    SweepMode,
    TrialKey,
    TrialResult,
)


@dataclass
class TrialPlan:
    """One planned trial coordinate, before execution."""

    assistant: AssistantSpec
    profile: Profile
    condition: MmCondition
    task: TaskSpec
    repeat: int


@dataclass
class SweepConfig:
    """Declarative description of a sweep.

    Args:
        sweep_mode: Whether this sweep varies the profile or the assistant.
        assistants: Assistant harnesses to evaluate.
        profiles: ``mm`` backend profiles for the ``mm`` arm.
        tasks: Tasks to run (defaults to the full catalogue).
        conditions: Arms to run (defaults to baseline + ``mm``).
        repeats: Repeats per cell (for variance).
        max_turns: Per-trial turn budget.
        timeout_s: Per-trial wall budget.
        max_cost_usd: Stop launching trials past this accumulated spend.
        label: Human-readable run label.
    """

    sweep_mode: SweepMode
    assistants: list[AssistantSpec]
    profiles: list[Profile] = field(default_factory=lambda: [Profile.none()])
    tasks: list[TaskSpec] = field(default_factory=lambda: list(TASKS))
    conditions: list[MmCondition] = field(
        default_factory=lambda: [MmCondition.BASELINE, MmCondition.MM]
    )
    repeats: int = 1
    max_turns: int = 20
    timeout_s: float = 120.0
    max_cost_usd: float = 0.0
    label: str = ""

    def plan(self) -> Iterator[TrialPlan]:
        """Enumerate every trial this config expands to."""
        for task in self.tasks:
            for assistant in self.assistants:
                for condition in self.conditions:
                    profiles = (
                        [Profile.none()] if condition is MmCondition.BASELINE else self.profiles
                    )
                    for profile in profiles:
                        for repeat in range(self.repeats):
                            yield TrialPlan(assistant, profile, condition, task, repeat)


class Sweep:
    """Runs a :class:`SweepConfig` against a store using a harness."""

    def __init__(self, harness: Harness, store: Store) -> None:
        self.harness = harness
        self.store = store

    def run(self, config: SweepConfig, dataset_hash: str = "") -> int:
        """Execute the sweep and return the persisted ``run_id``."""
        run_id = self.store.start_run(
            sweep_mode=config.sweep_mode.value,
            label=config.label,
            dataset_hash=dataset_hash,
            meta={
                "assistants": [a.name for a in config.assistants],
                "profiles": [p.name for p in config.profiles],
                "repeats": config.repeats,
            },
        )
        spent = 0.0
        for plan in config.plan():
            if config.max_cost_usd and spent >= config.max_cost_usd:
                break
            result = self._run_or_skip(run_id, config, plan)
            spent += result.metrics.cost_usd
        return run_id

    def _run_or_skip(self, run_id: int, config: SweepConfig, plan: TrialPlan) -> TrialResult:
        """Run a planned trial, or return a cheap skip if already recorded."""
        key = TrialKey(
            plan.assistant.name, plan.profile.name, plan.condition, plan.task.id, plan.repeat
        )
        if self.store.has_trial(run_id, key):
            return TrialResult(key=key)
        result = self.harness.run_trial(
            assistant=plan.assistant,
            task=plan.task,
            condition=plan.condition,
            profile=plan.profile,
            repeat=plan.repeat,
            max_turns=config.max_turns,
            timeout_s=config.timeout_s,
        )
        self.store.save_trial(run_id, result)
        return result
