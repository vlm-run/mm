"""Grade an agent's run against a case: deterministic checks + LLM judge.

Correctness is a 50/50 blend of:

  - **checks**: deterministic, partial-credit checks (``Check`` kinds) run against
    the agent's final answer, the sandbox's final filesystem state, and any
    artifact it wrote. These anchor the score so a flaky judge cannot swing it.
  - **LLM judge**: a single 0-5 score against the case's ``judge_objective``,
    grounded in its ``ground_truth``.

    Correctness is checks-only **only** when the judge is explicitly
    disabled (``--no-judge``) or the task produced no answer to judge. A judge
    call that errors mid-run is retried up to ``JUDGE_RETRIES`` times; if it still
    fails it raises :class:`JudgeError` and the caller voids the run.

Override the judge model/endpoint with ``MMBENCH_JUDGE_MODEL`` /
``MMBENCH_JUDGE_BASE_URL`` if needed.

Example:
    >>> g = Grader()
    >>> gr = g.grade(case, result, sandbox_path)
    >>> gr.correctness, gr.checkpoint_score, gr.judge_score
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .assistants import AssistantResult
from .cases import Check, EvalCase

JUDGE_RETRIES = 3
JUDGE_BASE_URL = os.environ.get("MMBENCH_JUDGE_BASE_URL", "https://openrouter.ai/api/v1")
JUDGE_MODEL = os.environ.get("MMBENCH_JUDGE_MODEL", "google/gemini-3.1-flash-lite")
JUDGE_API_KEY = os.environ.get("MMBENCH_JUDGE_API_KEY") or os.environ["OPENROUTER_API_KEY"]

_JUDGE_SYSTEM = (
    "You are a strict evaluator. Score how well the model response satisfies the "
    "evaluation objective on an integer scale from 0 to 5 (5 = fully correct and "
    "complete, 3 = partially correct, 0 = entirely wrong or missing). Respond with "
    "ONLY a single integer 0-5. No explanation."
)


class JudgeError(RuntimeError):
    """The LLM judge could not produce a score after retries."""


def judge_client() -> tuple:
    """Build the judge's OpenAI client + model from env (no mm profile).

    Key is read live from ``MMBENCH_JUDGE_API_KEY``;
    raises :class:`JudgeError` if neither is set.
    """
    from openai import OpenAI

    return OpenAI(base_url=JUDGE_BASE_URL, api_key=JUDGE_API_KEY), JUDGE_MODEL


def ping_judge() -> tuple[bool, str]:
    """Confirm the judge endpoint is reachable with a 1-token call."""
    try:
        client, model = judge_client()
        client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": "ping"}], max_tokens=1, temperature=0
        )
        return True, f"{model} @ {JUDGE_BASE_URL}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:160]}"


def _norm_text(s: str) -> str:
    """Lowercase and collapse whitespace for substring matching."""
    return re.sub(r"\s+", " ", s).strip().lower()


def _norm_number(s: str) -> str:
    """Strip thousands separators and spaces so 342,775.48 matches 342775.48."""
    return s.replace(",", "").replace(" ", "")


@dataclass
class CheckOutcome:
    """Per-check result: which check, whether it passed, its weight."""

    kind: str
    weight: float
    passed: bool
    detail: str = ""


@dataclass
class GradeResult:
    """The full grade for one (case, arm) run."""

    correctness: float
    checkpoint_score: float
    judge_score: int | None
    task_completion: int
    failure_mode: str | None
    outcomes: list[CheckOutcome] = field(default_factory=list)


class Grader:
    """Scores agent runs. Optionally calls the fixed LLM judge (see module docs).

    Args:
        use_judge: whether to call the LLM judge at all (``--no-judge`` -> False).
    """

    def __init__(self, use_judge: bool = True) -> None:
        self.use_judge = use_judge

    def grade(self, case: EvalCase, result: AssistantResult, sandbox_path: Path) -> GradeResult:
        """Grade one run. ``sandbox_path`` is the agent's final working tree."""
        outcomes = [self._run_check(c, result.final_output, sandbox_path) for c in case.checks]
        total_w = sum(o.weight for o in outcomes)
        checkpoint_score = sum(o.weight for o in outcomes if o.passed) / total_w if total_w else 0.0

        task_completion = int(bool(result.final_output.strip()) and not result.timed_out)
        failure_mode = self._failure_mode(result)

        judge_score = None
        if self.use_judge and task_completion:
            judge_score = self._judge(case, result.final_output)

        if judge_score is not None:
            correctness = 0.5 * (checkpoint_score * 100) + 0.5 * (judge_score / 5 * 100)
        else:
            correctness = checkpoint_score * 100

        return GradeResult(
            correctness=round(correctness, 2),
            checkpoint_score=round(checkpoint_score, 4),
            judge_score=judge_score,
            task_completion=task_completion,
            failure_mode=failure_mode,
            outcomes=outcomes,
        )

    def _failure_mode(self, result: AssistantResult) -> str | None:
        """Map a run's exit state to the failure taxonomy (None if clean)."""
        if result.timed_out:
            return "timeout"
        if result.exit_code not in (0, None):
            return "tool_error"
        return None

    def _run_check(self, check: Check, answer: str, sandbox: Path) -> CheckOutcome:
        """Dispatch one check to its executor."""
        p = check.params
        try:
            passed, detail = _CHECK_FNS[check.kind](p, answer, sandbox)
        except Exception as exc:  # a malformed artifact should fail the check, not crash
            passed, detail = False, f"error: {exc}"
        return CheckOutcome(kind=check.kind, weight=check.weight, passed=passed, detail=detail)

    def _judge(self, case: EvalCase, answer: str) -> int:
        """0-5 LLM-judge score, retried up to ``JUDGE_RETRIES`` times.

        Reachability is asserted by preflight before the run, so a failure here is
        a mid-run transport/format problem. After exhausting retries it raises
        :class:`JudgeError` (no fallback): the caller nullifies the run rather
        than leave it with a mix of judged and checks-only cells.
        """
        client, model = judge_client()
        user = (
            f"Evaluation objective:\n{case.judge_objective}\n\n"
            f"Ground truth:\n{case.ground_truth}\n\n"
            f"Model response:\n{answer}"
        )
        last = ""
        for _ in range(JUDGE_RETRIES):
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": _JUDGE_SYSTEM},
                        {"role": "user", "content": user},
                    ],
                    temperature=0,
                )
                score = _clamp_score(resp.choices[0].message.content or "")
                if score is not None:
                    return score
                last = "non-numeric judge reply"
            except Exception as e:
                last = f"{type(e).__name__}: {str(e)[:160]}"
        raise JudgeError(f"judge ({model}) failed after {JUDGE_RETRIES} tries: {last}")


def client_for(profile_name: str | None):
    """Build an OpenAI client + model for an mm profile (None = active profile).

    Raises on an unresolvable profile so callers can fail loudly.
    """
    from mm.profile import get_profile
    from openai import OpenAI

    prev = os.environ.get("MM_PROFILE")
    if profile_name:
        os.environ["MM_PROFILE"] = profile_name
    try:
        profile = get_profile()
    finally:
        if profile_name:
            if prev is None:
                os.environ.pop("MM_PROFILE", None)
            else:
                os.environ["MM_PROFILE"] = prev
    if not profile.base_url or not profile.model:
        raise RuntimeError(f"profile {profile_name or '<active>'} has no base_url/model")
    client = OpenAI(base_url=profile.base_url.rstrip("/"), api_key=profile.api_key or "noop")
    return client, profile.model


def ping_profile(profile_name: str | None) -> tuple[bool, str]:
    """Confirm a profile's chat endpoint is reachable with a 1-token call."""
    try:
        client, model = client_for(profile_name)
    except Exception as e:
        return False, str(e)
    try:
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0,
        )
        return True, "ok"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:160]}"


def _clamp_score(text: str) -> int | None:
    """Extract the first integer in 0-5 from judge text."""
    m = re.search(r"[0-5]", text)
    return int(m.group()) if m else None


def _check_names_file(p: dict, answer: str, sandbox: Path) -> tuple[bool, str]:
    base = Path(p["path"]).name
    return (base.lower() in _norm_text(answer)), base


def _check_contains_number(p: dict, answer: str, sandbox: Path) -> tuple[bool, str]:
    needle = _norm_number(str(p["value"]))
    return (needle in _norm_number(answer)), needle


def _check_contains_text(p: dict, answer: str, sandbox: Path) -> tuple[bool, str]:
    needle = _norm_text(str(p["value"]))
    return (needle in _norm_text(answer)), needle


def _check_path_exists(p: dict, answer: str, sandbox: Path) -> tuple[bool, str]:
    return (sandbox / p["path"]).exists(), p["path"]


def _check_path_absent(p: dict, answer: str, sandbox: Path) -> tuple[bool, str]:
    return (not (sandbox / p["path"]).exists()), p["path"]


def _check_artifact_exists(p: dict, answer: str, sandbox: Path) -> tuple[bool, str]:
    return (sandbox / p["path"]).is_file(), p["path"]


def _check_artifact_contains(p: dict, answer: str, sandbox: Path) -> tuple[bool, str]:
    f = sandbox / p["path"]
    if not f.is_file():
        return False, "artifact missing"
    needle = _norm_number(_norm_text(str(p["value"])))
    return (needle in _norm_number(_norm_text(f.read_text(errors="ignore")))), str(p["value"])


def _check_artifact_row_count(p: dict, answer: str, sandbox: Path) -> tuple[bool, str]:
    f = sandbox / p["path"]
    if not f.is_file():
        return False, "artifact missing"
    rows = [
        r
        for r in csv.reader(f.read_text(errors="ignore").splitlines())
        if any(c.strip() for c in r)
    ]
    data_rows = max(0, len(rows) - 1)  # exclude header
    return (data_rows == int(p["count"])), f"{data_rows} data rows"


_CHECK_FNS = {
    "names_file": _check_names_file,
    "contains_number": _check_contains_number,
    "contains_text": _check_contains_text,
    "path_exists": _check_path_exists,
    "path_absent": _check_path_absent,
    "artifact_exists": _check_artifact_exists,
    "artifact_contains": _check_artifact_contains,
    "artifact_row_count": _check_artifact_row_count,
}
