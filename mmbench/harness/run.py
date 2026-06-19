"""Orchestrator: run the assistant x profile x case x arm matrix into SQLite.

The unit of work is an ``(assistant, profile)`` cell. A run takes the cartesian
product of ``--assistants`` and ``--profiles`` and benchmarks each cell as one
**session**; within a session each run executes every case under both arms
(without_mm, with_mm) in its own disposable sandbox, grades, and persists. So
``--assistants a,b --profiles p,q`` runs a/p, a/q, b/p, b/q. The dashboard then
filters/compares any subset of cells.

The with_mm arm uses the session's profile (``MM_PROFILE``) as mm's backend;
the without_mm arm has no mm at all (PATH shim).

Usage:
    uv run python -m mmbench.harness.run --assistants claude --profiles gateway
    uv run python -m mmbench.harness.run --assistants claude,codex --profiles gateway,orion-2
"""

from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

from .assistants import DEFAULT_TIMEOUT_S, PRIMER_PATH, SUPPORTED, Assistant
from .cases import EvalCase, load_cases
from .grader import Grader, JudgeError
from .preflight import preflight
from .sandbox import SandboxManager
from .store import CaseResult, MmBenchStore

DATASETS_ROOT = Path(__file__).resolve().parents[1] / "data"  # mmbench/data (gitignored)
ARTIFACTS_ROOT = DATASETS_ROOT / "_artifacts"  # persisted agent-written files for UI review
HF_DATASET = "vlm-run/mmbench"
ARMS = ("without_mm", "with_mm")
ARTIFACT_KINDS = ("artifact_exists", "artifact_contains", "artifact_row_count")


def _profile_meta(profile_name: str) -> tuple[str | None, str | None]:
    """Resolve a profile's (base_url, model) via mm, for the session record."""
    try:
        import os

        from mm.profile import get_profile

        prev = os.environ.get("MM_PROFILE")
        os.environ["MM_PROFILE"] = profile_name
        try:
            p = get_profile()
            return p.base_url, p.model
        finally:
            if prev is None:
                os.environ.pop("MM_PROFILE", None)
            else:
                os.environ["MM_PROFILE"] = prev
    except Exception:
        return None, None


def _persist_artifacts(case: EvalCase, sandbox_path: Path, session_id: str, arm: str) -> None:
    """Copy the files an agent wrote (named by artifact_* checks) out of the sandbox.

    Sandboxes are disposed after grading, so the artifact bytes are saved under
    ``ARTIFACTS_ROOT/<session>/<case>/<arm>/`` for later review in the dashboard.
    The latest run for a (session, case, arm) overwrites earlier ones.
    """
    rels = {c.params["path"] for c in case.checks if c.kind in ARTIFACT_KINDS}
    if not rels:
        return
    dest_root = ARTIFACTS_ROOT / session_id / case.id / arm
    for rel in rels:
        src = sandbox_path / rel
        if src.is_file():
            dest = dest_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)


class Orchestrator:
    """Drives the (assistant x profile) x case x arm matrix and persists every cell.

    Args:
        assistants: assistant names to sweep.
        profiles: mm profile names to sweep.
        cases: cases to run.
        runs: repetitions per cell (variance control).
        timeout_s: per-agent hard cap.
        store: results store.
        grader: scorer.
        keep_sandboxes: retain sandboxes for review instead of disposing.
    """

    def __init__(
        self,
        *,
        assistants: list[str],
        profiles: list[str],
        cases: list[EvalCase],
        runs: int,
        timeout_s: int,
        store: MmBenchStore,
        grader: Grader,
        keep_sandboxes: bool = False,
        resume: bool = False,
        stream: bool = False,
    ) -> None:
        self.assistants = assistants
        self.profiles = profiles
        self.cases = cases
        self.runs = runs
        self.timeout_s = timeout_s
        self.store = store
        self.grader = grader
        self.sandboxes = SandboxManager()
        self.keep_sandboxes = keep_sandboxes
        self.resume = resume
        self.stream = stream
        self.primer = PRIMER_PATH.read_text()

    def run(self) -> None:
        """Execute every (assistant, profile) cell (cartesian product)."""
        for assistant_name in self.assistants:
            adapter = Assistant.get(assistant_name)
            if not adapter.is_installed():
                print(f"skip {assistant_name}: not installed")
                continue
            for profile_name in self.profiles:
                self._run_session(adapter, profile_name)

    def _run_session(self, adapter: Assistant, profile_name: str) -> None:
        base_url, model = _profile_meta(profile_name)
        done: set[tuple[str, str]] = set()
        sid = self.store.latest_session_id(adapter.name, profile_name) if self.resume else None
        if sid:
            done = self.store.completed_cells(sid)
            print(
                f"\n== resume {adapter.name} / {profile_name} (session {sid[:8]}, {len(done)} cells done) =="
            )
        else:
            sid = self.store.start_session(
                assistant=adapter.name,
                profile_name=profile_name,
                base_url=base_url,
                model=model,
            )
            print(
                f"\n== session {adapter.name} / {profile_name} ({base_url or 'n/a'} / {model or 'n/a'}) =="
            )
        for run_index in range(self.runs):
            rid = self.store.start_run(sid, run_index)
            t0 = time.perf_counter()
            try:
                for case in self.cases:
                    self._run_case(adapter, profile_name, case, sid, rid, run_index, done)
            except JudgeError as e:
                # Judge unreachable mid-run: void just this run (drop its rows) so it cannot leave a gap.
                self.store.void_run(rid)
                raise SystemExit(
                    f"judge failed in run {run_index}; voided that run "
                    f"(session {sid[:8]} kept its other runs): {e}"
                ) from e
            self.store.finish_run(rid, round(time.perf_counter() - t0, 2))
        self.store.finish_session(sid)

    def _run_case(
        self,
        adapter: Assistant,
        profile_name: str,
        case: EvalCase,
        sid: str,
        rid: str,
        run_index: int,
        done: set[tuple[str, str]],
    ) -> None:
        source = case.resolve_dataset(DATASETS_ROOT)  # preflight already verified
        for arm in ARMS:
            if (case.id, arm) in done:
                print(f"  {case.id:32} {arm:9} skip (resume)")
                continue
            sandbox = self.sandboxes.materialize(
                source,
                assistant=adapter.name,
                profile=profile_name,
                case_id=case.id,
                arm=arm,
                run_index=run_index,
                keep=self.keep_sandboxes,
            )
            if self.stream:
                print(f"\n┌─ {adapter.name}/{profile_name} · {case.id} · {arm} " + "─" * 24)
            try:
                result = adapter.run(
                    case,
                    arm=arm,
                    input_path=sandbox.path,
                    primer=self.primer,
                    profile_name=profile_name,
                    timeout_s=self.timeout_s,
                    stream=self.stream,
                )
                grade = self.grader.grade(case, result, sandbox.path)
                self.store.record_case_result(
                    rid,
                    sid,
                    CaseResult(
                        case_id=case.id,
                        arm=arm,
                        title=case.title,
                        difficulty=case.difficulty,
                        archetype=case.archetype,
                        modality=case.modality,
                        mm_commands=case.mm_commands,
                        correctness=grade.correctness,
                        checkpoint_score=grade.checkpoint_score,
                        judge_score=grade.judge_score,
                        speed_s=round(result.elapsed_s, 2),
                        task_completion=grade.task_completion,
                        mm_used=(1 if result.mm_commands_used else 0) if arm == "with_mm" else None,
                        mm_commands_used=result.mm_commands_used,
                        failure_mode=grade.failure_mode,
                        final_output=result.final_output,
                        transcript=result.transcript,
                    ),
                )
                _persist_artifacts(case, sandbox.path, sid, arm)
                print(
                    f"  {case.id:32} {arm:9} correctness={grade.correctness:6.1f} "
                    f"speed={result.elapsed_s:5.0f}s mm={result.mm_commands_used or '-'}"
                )
            finally:
                if not self.keep_sandboxes:
                    sandbox.dispose()


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def ensure_dataset() -> None:
    """Download the mmbench dataset (corpus + cases) from HF into mmbench/data/.

    On first run, pull ``vlm-run/mmbench`` and store it package-relative; skip if
    already present. Requires HF auth (the repo is currently private).
    """
    if (DATASETS_ROOT / "cases.jsonl").exists() and (DATASETS_ROOT / "mmbench-agent").is_dir():
        return
    print(f"dataset missing; downloading {HF_DATASET} -> {DATASETS_ROOT} ...")
    from huggingface_hub import snapshot_download

    snapshot_download(repo_id=HF_DATASET, repo_type="dataset", local_dir=str(DATASETS_ROOT))
    print("  done")


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description="Run the mmbench agent benchmark.")
    ap.add_argument("--assistants", default="claude", help=f"comma-separated; from {SUPPORTED}")
    ap.add_argument("--profiles", default="gateway", help="comma-separated mm profile names")
    ap.add_argument("--cases", default="", help="comma-separated case ids (default: all)")
    ap.add_argument("--runs", type=int, default=1, help="repetitions per cell")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="per-agent seconds")
    ap.add_argument("--db", default="", help="SQLite path (default: package data/mmbench.db)")
    ap.add_argument("--no-judge", action="store_true", help="skip the LLM judge")
    ap.add_argument("--keep-sandboxes", action="store_true", help="retain sandboxes for review")
    ap.add_argument(
        "--resume", action="store_true", help="reuse latest session, skip completed cells"
    )
    ap.add_argument(
        "--stream", action="store_true", help="tee each agent's live output to the terminal"
    )
    ap.add_argument(
        "--skip-preflight", action="store_true", help="skip preflight checks (not advised)"
    )
    ap.add_argument(
        "--check", action="store_true", help="ping assistants/profiles/judge and exit (no run)"
    )
    args = ap.parse_args(argv)

    ensure_dataset()  # download corpus + cases from HF on first run

    all_cases = {c.id: c for c in load_cases()}
    selected = _csv(args.cases) or list(all_cases)
    missing = [c for c in selected if c not in all_cases]
    if missing:
        ap.error(f"unknown case ids: {missing}; available: {sorted(all_cases)}")
    cases = [all_cases[c] for c in selected]

    assistants, profiles = _csv(args.assistants), _csv(args.profiles)
    use_judge = not args.no_judge

    if args.check or not args.skip_preflight:
        print("preflight:")
        report = preflight(
            assistants=assistants,
            profiles=profiles,
            cases=cases,
            datasets_root=DATASETS_ROOT,
            use_judge=use_judge,
        )
        print("\n".join(report.lines))
        if args.check:
            raise SystemExit(0 if report.ok else 1)
        if not report.ok:
            raise SystemExit("preflight failed; aborting (fix the above or pass --skip-preflight)")

    store = MmBenchStore(args.db) if args.db else MmBenchStore()
    grader = Grader(use_judge=use_judge)
    orch = Orchestrator(
        assistants=assistants,
        profiles=profiles,
        cases=cases,
        runs=args.runs,
        timeout_s=args.timeout,
        store=store,
        grader=grader,
        keep_sandboxes=args.keep_sandboxes,
        resume=args.resume,
        stream=args.stream,
    )
    print(
        f"\nmmbench: {len(assistants)}x{len(profiles)} cells {assistants}x{profiles} "
        f"cases={len(cases)} runs={args.runs} judge={'off' if args.no_judge else 'on'}"
    )
    orch.run()
    store.close()
    print("\ndone. results in SQLite.")


if __name__ == "__main__":
    main()
