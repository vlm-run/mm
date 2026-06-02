"""Every task's verifier must pass the reference answer and fail a corruption.

Uses :mod:`mmbench_agents.oracle` to derive a schema-correct answer and a
deterministically wrong one for each task, exercising the whole catalogue
(including the PDF, line-count, and image-width tasks) against frozen GT.
"""

from __future__ import annotations

import pytest

from mmbench_agents import dataset
from mmbench_agents.oracle import correct_answer, corrupt_answer
from mmbench_agents.tasks import TASKS_BY_ID


@pytest.mark.parametrize("task_id", sorted(TASKS_BY_ID))
def test_verifier_passes_correct_and_fails_corrupt(task_id):
    gt = dataset.load_ground_truth()
    verifier = TASKS_BY_ID[task_id].verifier
    assert verifier.verify(correct_answer(task_id, gt), gt).passed
    assert not verifier.verify(corrupt_answer(task_id, gt), gt).passed


def test_catalogue_covers_every_action_command():
    commands = {c for task in TASKS_BY_ID.values() for c in task.intended_mm_commands}
    assert {"find", "wc", "sql", "peek", "grep", "cat"} <= commands
