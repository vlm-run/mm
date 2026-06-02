"""Run a single benchmark trial in an isolated sandbox.

One trial = ``(assistant, profile, mm_condition, task, repeat)``. The harness:

1. Builds a throwaway sandbox holding a fresh copy of the frozen corpus.
2. Constructs an environment with fresh ``MM_*`` paths so no extraction cache,
   DB, or blob store leaks between trials, and toggles ``mm`` on/off on ``PATH``
   to realise the baseline-vs-``mm`` contrast.
3. Invokes the assistant adapter under a turn/time budget and captures metrics.
4. Parses the structured answer, runs the task's deterministic verifier, and
   scores the result.

The harness never inspects the answer itself beyond delegating to the verifier,
keeping scoring auditable and arm-symmetric.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

from mmbench_agents import adapters
from mmbench_agents.adapters import AdapterRequest
from mmbench_agents.answers import parse_answer
from mmbench_agents.dataset import ensure_corpus, load_ground_truth
from mmbench_agents.judge import Judge, NullJudge
from mmbench_agents.scoring import score_trial
from mmbench_agents.tasks import TaskSpec
from mmbench_agents.types import (
    AssistantSpec,
    FailureMode,
    MmCondition,
    Profile,
    Score,
    TrialKey,
    TrialMetrics,
    TrialResult,
)

_MM_ENV_DIRS = ("MM_DATA_DIR", "MM_CACHE_DIR", "MM_CONFIG_DIR", "MM_BLOBS_DIR")


class Harness:
    """Executes trials with per-trial sandboxing and cache isolation.

    Args:
        base_env: Environment to derive each trial's environment from.
        mm_bindir: Directory containing the ``mm`` binary; prepended to ``PATH``
            on the ``mm`` arm and stripped on the baseline arm.
        judge: Optional free-text rubric judge (defaults to abstaining).
        sandbox_root: Parent directory for throwaway sandboxes.
        keep_sandbox: Retain sandboxes after each trial (for debugging).
    """

    def __init__(
        self,
        base_env: dict[str, str] | None = None,
        mm_bindir: str | None = None,
        judge: Judge | None = None,
        sandbox_root: Path | None = None,
        keep_sandbox: bool = False,
    ) -> None:
        self.base_env = dict(base_env if base_env is not None else os.environ)
        self.mm_bindir = mm_bindir or self._discover_mm_bindir()
        self.judge = judge or NullJudge()
        self.sandbox_root = sandbox_root
        self.keep_sandbox = keep_sandbox

    @staticmethod
    def _discover_mm_bindir() -> str | None:
        """Locate the directory of the ``mm`` binary, if installed."""
        found = shutil.which("mm")
        return str(Path(found).parent) if found else None

    def _build_env(self, sandbox: Path, condition: MmCondition, profile: Profile) -> dict[str, str]:
        """Build a fresh, cache-isolated environment for one trial."""
        env = dict(self.base_env)
        for var in _MM_ENV_DIRS:
            path = sandbox / "mm_state" / var.lower()
            path.mkdir(parents=True, exist_ok=True)
            env[var] = str(path)
        env["MM_DB_PATH"] = str(sandbox / "mm_state" / "mm.db")

        path_parts = [p for p in env.get("PATH", "").split(":") if p]
        if condition is MmCondition.BASELINE and self.mm_bindir:
            path_parts = [p for p in path_parts if p != self.mm_bindir]
        if condition is MmCondition.MM and self.mm_bindir:
            path_parts = [self.mm_bindir, *[p for p in path_parts if p != self.mm_bindir]]
        env["PATH"] = ":".join(path_parts)
        env["MMBENCH_PROFILE"] = profile.name
        return env

    def _sandbox(self) -> Path:
        """Create a sandbox with a fresh copy of the corpus."""
        root = Path(tempfile.mkdtemp(prefix="mmbench-", dir=self.sandbox_root))
        shutil.copytree(ensure_corpus(), root / "corpus")
        return root

    def run_trial(
        self,
        assistant: AssistantSpec,
        task: TaskSpec,
        condition: MmCondition,
        profile: Profile,
        repeat: int = 0,
        max_turns: int = 20,
        timeout_s: float = 120.0,
    ) -> TrialResult:
        """Run one trial end-to-end and return its scored result."""
        key = TrialKey(assistant.name, profile.name, condition, task.id, repeat)
        adapter = adapters.get(assistant.adapter)
        if not adapter.available():
            return TrialResult(key=key, failure_mode=FailureMode.SKIPPED)

        sandbox = self._sandbox()
        try:
            env = self._build_env(sandbox, condition, profile)
            request = AdapterRequest(
                assistant=assistant,
                task=task,
                workdir=sandbox,
                mm_condition=condition,
                profile=profile,
                env=env,
                max_turns=max_turns,
                timeout_s=timeout_s,
                repeat=repeat,
            )
            start = time.perf_counter()
            result = adapter.run(request)
            measured = time.perf_counter() - start
        finally:
            if not self.keep_sandbox:
                shutil.rmtree(sandbox, ignore_errors=True)

        metrics = TrialMetrics(
            wall_s=round(result.wall_s or measured, 3),
            turns=result.turns,
            tool_calls=result.tool_calls,
            mm_calls=result.mm_calls,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost_usd=result.cost_usd,
        )
        if result.failure_mode is not FailureMode.NONE:
            return TrialResult(
                key=key,
                failure_mode=result.failure_mode,
                metrics=metrics,
                score=Score(),
                mm_commands=result.mm_commands,
                raw_output=result.raw_output,
            )

        answer = parse_answer(result.raw_output)
        if answer is None:
            return TrialResult(
                key=key,
                failure_mode=FailureMode.NO_ANSWER,
                metrics=metrics,
                mm_commands=result.mm_commands,
                raw_output=result.raw_output,
            )

        gt = load_ground_truth()
        report = task.verifier.verify(answer, gt)
        rubric = self.judge.score(task, answer, gt)
        score = score_trial(report, FailureMode.NONE, rubric)
        return TrialResult(
            key=key,
            failure_mode=FailureMode.NONE,
            metrics=metrics,
            score=score,
            answer=answer,
            mm_commands=result.mm_commands,
            sub_checks=report.sub_checks,
            raw_output=result.raw_output,
        )
