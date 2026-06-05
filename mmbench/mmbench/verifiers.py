"""Deterministic verifiers for mmbench-agents tasks.

Each verifier compares a structured agent answer (a ``dict`` parsed from the
agent's final output) against frozen ground truth and returns a
:class:`VerifierReport` of named sub-checks. Verifiers never call ``mm`` and
hold no per-task data — task-specific keys and tolerances are injected at
construction, so the same verifier class serves many tasks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from mmbench.types import VerifierReport


def _as_set(value: Any) -> set[str]:
    """Coerce a scalar or iterable of strings into a set of strings."""
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    return {str(v) for v in value}


class Verifier(ABC):
    """Checks one structured answer against ground truth."""

    @abstractmethod
    def verify(self, answer: dict[str, Any], gt: dict[str, Any]) -> VerifierReport:
        """Return a deterministic report of sub-checks for ``answer``."""


class ManifestVerifier(Verifier):
    """Verify a per-kind manifest: counts, total bytes, and largest files.

    Args:
        byte_tol: Fractional tolerance on ``total_bytes`` (0.0 = exact).
    """

    def __init__(self, byte_tol: float = 0.0) -> None:
        self.byte_tol = byte_tol

    def verify(self, answer: dict[str, Any], gt: dict[str, Any]) -> VerifierReport:
        report = VerifierReport()

        got_counts = {str(k): int(v) for k, v in (answer.get("counts_by_kind") or {}).items()}
        report.add(
            "counts_by_kind",
            got_counts == gt["counts_by_kind"],
            f"got {got_counts}, want {gt['counts_by_kind']}",
        )

        want_bytes = gt["total_bytes"]
        got_bytes = answer.get("total_bytes")
        within = (
            isinstance(got_bytes, (int, float))
            and abs(got_bytes - want_bytes) <= self.byte_tol * want_bytes
        )
        report.add(
            "total_bytes", bool(within), f"got {got_bytes}, want {want_bytes} (tol {self.byte_tol})"
        )

        report.add(
            "top_files",
            _as_set(answer.get("top_files")) == set(gt["top_files"]),
            f"got {_as_set(answer.get('top_files'))}, want {set(gt['top_files'])}",
        )
        return report


class SetMembershipVerifier(Verifier):
    """Verify that an answer field equals a ground-truth set (order-insensitive).

    Args:
        answer_field: Key in the agent answer holding the set.
        gt_field: Key in ground truth holding the expected set.
    """

    def __init__(self, answer_field: str, gt_field: str) -> None:
        self.answer_field = answer_field
        self.gt_field = gt_field

    def verify(self, answer: dict[str, Any], gt: dict[str, Any]) -> VerifierReport:
        report = VerifierReport()
        got = _as_set(answer.get(self.answer_field))
        want = _as_set(_flatten(gt[self.gt_field]))
        report.add(self.gt_field, got == want, f"got {got}, want {want}")
        return report


class ExactValueVerifier(Verifier):
    """Verify named scalar fields against ground truth, with numeric tolerance.

    Args:
        fields: Maps answer field name -> ``(gt_keys, tol)``. ``gt_keys`` is a
            tuple of keys locating the value in the ground-truth dict (keys may
            themselves contain dots, e.g. a filename); ``tol`` is an absolute
            numeric tolerance (``None`` = exact equality, e.g. for strings).
    """

    def __init__(self, fields: dict[str, tuple[tuple[str, ...], float | None]]) -> None:
        self.fields = fields

    def verify(self, answer: dict[str, Any], gt: dict[str, Any]) -> VerifierReport:
        report = VerifierReport()
        for field_name, (gt_keys, tol) in self.fields.items():
            want = _dig(gt, gt_keys)
            got = answer.get(field_name)
            if tol is None:
                ok = got == want
            else:
                ok = isinstance(got, (int, float)) and abs(got - want) <= tol
            report.add(field_name, bool(ok), f"got {got!r}, want {want!r} (tol {tol})")
        return report


class ContainsVerifier(Verifier):
    """Verify that a ground-truth string appears within an answer field.

    Rewards grounding without demanding an exact full-text match: the agent's
    free-text answer must contain the expected token/snippet (case-insensitive,
    whitespace-collapsed).

    Args:
        answer_field: Key in the agent answer holding the free text.
        gt_field: Key in ground truth holding the required substring.
    """

    def __init__(self, answer_field: str, gt_field: str) -> None:
        self.answer_field = answer_field
        self.gt_field = gt_field

    @staticmethod
    def _norm(value: Any) -> str:
        return " ".join(str(value).split()).casefold()

    def verify(self, answer: dict[str, Any], gt: dict[str, Any]) -> VerifierReport:
        report = VerifierReport()
        want = self._norm(gt[self.gt_field])
        got = self._norm(answer.get(self.answer_field, ""))
        report.add(self.gt_field, want in got, f"want {want!r} in answer {self.answer_field!r}")
        return report


class CompositeVerifier(Verifier):
    """Run several verifiers and merge their sub-checks into one report.

    Args:
        verifiers: Verifiers whose sub-checks are concatenated; the task passes
            only if every sub-check across all of them passes.
    """

    def __init__(self, *verifiers: Verifier) -> None:
        self.verifiers = verifiers

    def verify(self, answer: dict[str, Any], gt: dict[str, Any]) -> VerifierReport:
        report = VerifierReport()
        for verifier in self.verifiers:
            report.sub_checks.extend(verifier.verify(answer, gt).sub_checks)
        return report


def _flatten(value: Any) -> list[str]:
    """Flatten one level of nested lists (e.g. duplicate groups) into strings."""
    out: list[str] = []
    for item in value:
        if isinstance(item, (list, tuple)):
            out.extend(str(x) for x in item)
        else:
            out.append(str(item))
    return out


def _dig(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Resolve a sequence of keys into a nested dict."""
    cur: Any = data
    for key in keys:
        cur = cur[key]
    return cur
