"""Core vocabulary for the mmbench-agents benchmark.

Defines the trial-matrix axes (see ``README.md`` §2) and the result records
that verifiers produce. Kept dependency-free so tasks, verifiers, and the
(future) harness all share one set of types.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
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


class FailureMode(str, Enum):
    """Why a trial did not yield a scoreable answer (``NONE`` = it did)."""

    NONE = "none"
    TIMEOUT = "timeout"
    BUDGET = "budget"
    ERROR = "error"
    SKIPPED = "skipped"
    NO_ANSWER = "no_answer"


@dataclass(frozen=True)
class Profile:
    """An ``mm`` backend profile (model + endpoint) the agent's tools call.

    ``Profile.none()`` marks the baseline arm, where ``mm`` is unavailable and
    no backend is exercised.
    """

    name: str
    model: str = ""
    endpoint: str = ""

    @classmethod
    def none(cls) -> Profile:
        """The sentinel profile used by the baseline (no-``mm``) arm."""
        return cls(name="none")


@dataclass(frozen=True)
class AssistantSpec:
    """A universal assistant harness under evaluation.

    Args:
        name: Stable identifier shown on the leaderboard (e.g. ``claude``).
        adapter: Key into the adapter registry that knows how to drive it.
        command: Optional binary name used for availability preflight.
    """

    name: str
    adapter: str
    command: str = ""


@dataclass(frozen=True)
class TrialKey:
    """The atomic, idempotent coordinate of one benchmark trial."""

    assistant: str
    profile: str
    mm_condition: MmCondition
    task_id: str
    repeat: int

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly mapping of the key fields."""
        return {
            "assistant": self.assistant,
            "profile": self.profile,
            "mm_condition": self.mm_condition.value,
            "task_id": self.task_id,
            "repeat": self.repeat,
        }


@dataclass
class TrialMetrics:
    """Performance signals captured while running a trial."""

    wall_s: float = 0.0
    turns: int = 0
    tool_calls: int = 0
    mm_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


@dataclass
class Score:
    """Qualitative scoring for a trial, kept separate from performance.

    ``completion``/``grounding`` are 0/1, ``correctness`` and ``rubric`` are
    0..1, and ``overall`` is the 0..100 headline. The deterministic verifier
    drives ``correctness``/``grounding``; ``rubric`` (the optional free-text
    judge) can only adjust within a passing answer and never rescues a
    deterministic failure.
    """

    completion: float = 0.0
    correctness: float = 0.0
    grounding: float = 0.0
    rubric: float | None = None
    overall: float = 0.0


@dataclass
class TrialResult:
    """Everything recorded about a single executed trial."""

    key: TrialKey
    failure_mode: FailureMode = FailureMode.NONE
    metrics: TrialMetrics = field(default_factory=TrialMetrics)
    score: Score = field(default_factory=Score)
    answer: dict = field(default_factory=dict)
    mm_commands: list[str] = field(default_factory=list)
    sub_checks: list[SubCheck] = field(default_factory=list)
    raw_output: str = ""

    def to_row(self) -> dict[str, object]:
        """Flatten into a JSON-serialisable row for the store."""
        return {
            **self.key.as_dict(),
            "failure_mode": self.failure_mode.value,
            "metrics": asdict(self.metrics),
            "score": asdict(self.score),
            "answer": self.answer,
            "mm_commands": self.mm_commands,
            "sub_checks": [asdict(c) for c in self.sub_checks],
            "raw_output": self.raw_output,
        }
