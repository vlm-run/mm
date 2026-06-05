"""Optional free-text rubric judge.

Deterministic verifiers carry the scoring; the judge exists only for genuinely
free-text quality and is layered on top — it can adjust the headline score
within a passing answer but never rescues a deterministic failure (the harness
enforces that). The default :class:`NullJudge` does not judge, keeping runs
offline and reproducible. An LLM-backed judge can be registered in its place
(temperature 0, strict rubric, content-hash-cached) for free-text tasks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from mmbench.tasks import TaskSpec


class Judge(ABC):
    """Rates a free-text answer in [0, 1], or returns ``None`` to abstain."""

    @abstractmethod
    def score(self, task: TaskSpec, answer: dict[str, Any], gt: dict[str, Any]) -> float | None:
        """Return a rubric score in [0, 1], or ``None`` if not applicable."""


class NullJudge(Judge):
    """A judge that always abstains (no network, fully reproducible)."""

    def score(self, task: TaskSpec, answer: dict[str, Any], gt: dict[str, Any]) -> float | None:
        """Abstain from judging."""
        return None
