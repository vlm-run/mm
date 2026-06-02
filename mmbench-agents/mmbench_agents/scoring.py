"""Combine a verifier report (and optional rubric) into a :class:`Score`.

Scoring is deliberately conservative: a trial that did not finish cleanly
(``failure_mode != NONE``) scores zero across the board, and the optional
free-text ``rubric`` only re-weights the headline among answers that already
completed — it can never turn a deterministic failure into a pass.
"""

from __future__ import annotations

from mmbench_agents.types import FailureMode, Score, VerifierReport

_RUBRIC_WEIGHT = 0.3


def score_trial(
    report: VerifierReport,
    failure_mode: FailureMode,
    rubric: float | None = None,
) -> Score:
    """Map a verifier report + failure mode + optional rubric to a Score."""
    if failure_mode is not FailureMode.NONE:
        return Score()
    correctness = report.score
    grounding = 1.0 if report.passed else 0.0
    if rubric is None:
        overall = 100.0 * correctness
    else:
        overall = 100.0 * ((1 - _RUBRIC_WEIGHT) * correctness + _RUBRIC_WEIGHT * rubric)
    return Score(
        completion=1.0,
        correctness=round(correctness, 4),
        grounding=grounding,
        rubric=rubric,
        overall=round(overall, 2),
    )
