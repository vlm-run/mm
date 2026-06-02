"""Core vocabulary for the mmbench-agents benchmark.

Defines the trial-matrix axes (see ``README.md`` §2) and the result records
that verifiers produce. Kept dependency-free so tasks, verifiers, and the
(future) harness all share one set of types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Scope(str, Enum):
    """What a task operates on."""

    FILE = "F"
    DIRECTORY = "D"
    MIXED = "M"


class MmCondition(str, Enum):
    """Whether the agent may use ``mm`` or only native tools.

    ``baseline`` = no ``mm`` on PATH; ``mm`` = ``mm`` available. The
    baseline-vs-mm contrast is the headline output of the benchmark.
    """

    BASELINE = "baseline"
    MM = "mm"


class SweepMode(str, Enum):
    """The two ways the trial matrix is swept.

    ``PROFILE`` fixes the assistant and varies ``mm``'s backend profile;
    ``ASSISTANT`` fixes the profile and varies the assistant harness.
    """

    PROFILE = "profile"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class SubCheck:
    """One named pass/fail check within a :class:`VerifierReport`."""

    name: str
    passed: bool
    detail: str = ""


@dataclass
class VerifierReport:
    """Deterministic outcome of checking one answer against ground truth.

    ``score`` is the fraction of sub-checks that passed (0..1); ``passed``
    is True only when every sub-check passed. The free-text rubric judge is
    layered on separately and never overrides a deterministic failure.
    """

    sub_checks: list[SubCheck] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        """Append a sub-check result."""
        self.sub_checks.append(SubCheck(name=name, passed=passed, detail=detail))

    @property
    def score(self) -> float:
        """Fraction of sub-checks that passed (0.0 when there are none)."""
        if not self.sub_checks:
            return 0.0
        return sum(c.passed for c in self.sub_checks) / len(self.sub_checks)

    @property
    def passed(self) -> bool:
        """True only when there is at least one sub-check and all passed."""
        return bool(self.sub_checks) and all(c.passed for c in self.sub_checks)
