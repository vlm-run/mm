"""Deterministic mock adapters for end-to-end runs without external creds.

A mock adapter emits a reference answer (optionally degraded by a per-adapter
skill level) and synthesizes plausible, reproducible metrics. The ``mm`` arm is
modelled as faster and slightly more accurate than baseline so the pipeline,
scoring, and dashboard can be exercised and an ``mm``-uplift signal is visible.
These adapters do **not** evaluate a real assistant — they validate the harness.
"""

from __future__ import annotations

import hashlib
import json

from mmbench.adapters import AdapterRequest, AdapterResult, AssistantAdapter, register
from mmbench.dataset import load_ground_truth
from mmbench.oracle import correct_answer, corrupt_answer
from mmbench.types import FailureMode, MmCondition


def _unit(*parts: object) -> float:
    """A deterministic pseudo-random float in [0, 1) from the given parts."""
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


class MockAdapter(AssistantAdapter):
    """A reproducible synthetic assistant parameterised by skill.

    Args:
        name: Registry/leaderboard name.
        skill: Baseline probability (0..1) of producing a correct answer.
        mm_bonus: Added to ``skill`` when ``mm`` is available.
    """

    def __init__(self, name: str, skill: float, mm_bonus: float) -> None:
        self.name = name
        self.skill = skill
        self.mm_bonus = mm_bonus

    def run(self, request: AdapterRequest) -> AdapterResult:
        task = request.task
        is_mm = request.mm_condition is MmCondition.MM
        gt = load_ground_truth()

        roll = _unit(self.name, task.id, request.mm_condition.value, request.repeat)
        p_correct = min(1.0, self.skill + (self.mm_bonus if is_mm else 0.0))
        answer = correct_answer(task.id, gt) if roll < p_correct else corrupt_answer(task.id, gt)

        if is_mm:
            commands = [f"mm {c}" for c in task.intended_mm_commands]
            turns = 3 + round(_unit("turns", task.id, request.repeat))
            wall = 3.0 + 4.0 * _unit("wall-mm", task.id, request.repeat)
        else:
            commands = []
            turns = 6 + round(2 * _unit("turns", task.id, request.repeat))
            wall = 7.0 + 6.0 * _unit("wall-base", task.id, request.repeat)

        narrative = f"Worked on {task.id} ({'mm' if is_mm else 'baseline'}).\n"
        raw = narrative + "```json\n" + json.dumps(answer) + "\n```"
        return AdapterResult(
            raw_output=raw,
            turns=turns,
            tool_calls=turns,
            mm_calls=len(commands),
            tokens_in=400 * turns,
            tokens_out=120 * turns,
            cost_usd=round(0.002 * turns, 4),
            wall_s=round(wall, 3),
            mm_commands=commands,
            failure_mode=FailureMode.NONE,
        )


register(MockAdapter("mock-strong", skill=0.85, mm_bonus=0.10))
register(MockAdapter("mock-weak", skill=0.50, mm_bonus=0.25))
