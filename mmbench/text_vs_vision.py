"""Scratch evaluation: text-only models + mm vs native vision models.

This is a throwaway runner (not part of the harness) that reuses the mmbench
internals (Assistant, SandboxManager, Grader, MmBenchStore, cases, ad-hoc
profiles, primer) to answer a different question than the stock orchestrator:

    Do text-only models augmented with the `mm` toolkit match native
    vision-capable models on the same multimodal corpus?

Setups are built from CLI flags:

    --vision-models  : comma-separated OpenRouter model ids (without_mm arm).
    --text-models    : comma-separated OpenRouter model ids (with_mm arm).
    --mm-backend     : OpenRouter model id backing mm's own LLM (with_mm only).

Each vision model becomes a ``vN`` setup (without_mm). Each text model becomes a
``tN`` setup (with_mm, backed by --mm-backend). All via OpenRouter.

The stock orchestrator always runs both arms for one (assistant, profile) cell
with the same model; this comparison needs a different model per arm and only
one arm per cell, so it drives the harness components directly instead.

Results go to a separate SQLite DB (mmbench/data/text_vs_vision.db) so
the main mmbench.db is never touched.

Usage:
    uv run python -m mmbench.scratch_text_vs_vision            # all setups, all cases
    uv run python -m mmbench.scratch_text_vs_vision --cases invoices-to-csv,ocr-needle-at-scale
    uv run python -m mmbench.scratch_text_vs_vision --setup v0   # only first vision model
    uv run python -m mmbench.scratch_text_vs_vision --report    # just print the table
    uv run python -m mmbench.scratch_text_vs_vision \\
        --vision-models google/gemini-3.5-flash \\
        --text-models z-ai/glm-5.2 \\
        --mm-backend google/gemini-3.1-flash-lite
"""

from __future__ import annotations

import argparse
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from mmbench.harness.assistants import DEFAULT_TIMEOUT_S, PRIMER_PATH, Assistant
from mmbench.harness.cases import EvalCase, load_cases
from mmbench.harness.grader import Grader, JudgeConfig, JudgeError, ping_adhoc, ping_judge
from mmbench.harness.profiles import ProfileSpec, materialize_adhoc
from mmbench.harness.run import DATASETS_ROOT, _persist_artifacts, ensure_dataset
from mmbench.harness.sandbox import SandboxManager
from mmbench.harness.store import CaseResult, MmBenchStore

OPENROUTER = "https://openrouter.ai/api/v1"
DEFAULT_VISION_MODELS = "google/gemini-3.5-flash"
DEFAULT_TEXT_MODELS = "z-ai/glm-5.2"
DEFAULT_MM_BACKEND = "google/gemini-3.1-flash-lite"
SCRATCH_DB = Path(__file__).resolve().parent / "data" / "text_vs_vision.db"


@dataclass(frozen=True)
class Setup:
    """One evaluation cell: a pi model + a single arm + an optional mm backend.

    Attributes:
        key: short id ("v0" / "t1" / ...).
        label: human-readable label recorded as the profile_name in results.
        agent_model: the OpenRouter model id driving pi (the agent).
        mm_model: the OpenRouter model id backing mm's own LLM (with_mm only);
            None for the without_mm arm.
        arm: "with_mm" or "without_mm".
        profile: ad-hoc mm backend spec; None for the without_mm arm.
    """

    key: str
    label: str
    agent_model: str
    mm_model: str | None
    arm: str
    profile: ProfileSpec | None


def _model_label(model_id: str) -> str:
    """Short label from an OpenRouter model id (last path segment)."""
    return model_id.rsplit("/", 1)[-1]


def build_setups(
    vision_models: list[str], text_models: list[str], mm_backend: str
) -> dict[str, Setup]:
    """Build the setup matrix from model lists.

    Each vision model becomes a ``vN`` without_mm setup. Each text model becomes
    a ``tN`` with_mm setup backed by ``mm_backend``.
    """
    setups: dict[str, Setup] = {}
    for i, model in enumerate(vision_models):
        key = f"v{i}"
        setups[key] = Setup(
            key=key,
            label=_model_label(model),
            agent_model=model,
            mm_model=None,
            arm="without_mm",
            profile=None,
        )
    for i, model in enumerate(text_models):
        key = f"t{i}"
        setups[key] = Setup(
            key=key,
            label=f"{_model_label(model)}+mm",
            agent_model=model,
            mm_model=mm_backend,
            arm="with_mm",
            profile=None,
        )
    return setups


def _pi_cmd(model: str) -> list[str]:
    """Build pi arguments for an OpenRouter model."""
    return [
        "pi",
        "--provider",
        "openrouter",
        "--model",
        model,
        "--no-session",
        "--mode",
        "json",
        "-p",
    ]


def _materialize_setups(
    api_key: str, setups: dict[str, Setup], keys: list[str]
) -> dict[str, Setup]:
    """Bind selected with_mm setups to temporary mm backend profiles."""
    setup_dict: dict[str, Setup] = {}
    for key in keys:
        setup = setups[key]
        if setup.mm_model is None:
            setup_dict[key] = setup
            continue
        profile = materialize_adhoc(model=setup.mm_model, base_url=OPENROUTER, api_key=api_key)
        setup_dict[key] = Setup(
            key=setup.key,
            label=setup.label,
            agent_model=setup.agent_model,
            mm_model=setup.mm_model,
            arm=setup.arm,
            profile=profile,
        )
    return setup_dict


def _remove_profiles(setups: dict[str, Setup]) -> None:
    """Remove temporary profiles created for selected setups."""
    for setup in setups.values():
        if setup.profile and setup.profile.config_dir:
            shutil.rmtree(setup.profile.config_dir, ignore_errors=True)


def preflight(
    setups: dict[str, Setup],
    api_key: str,
    judge: JudgeConfig,
    *,
    harness: str = "pi",
) -> bool:
    """Ping every model (agent, mm backend, judge) and the harness CLI.

    Returns True only if all checks pass. Prints a line per check.
    """
    ok = True
    adapter = Assistant(harness)
    if not adapter.is_installed():
        print(f"  [FAIL] harness: {harness} not on PATH")
        ok = False
    else:
        print(f"  [ok]   harness: {harness}")

    pinged = set()
    for setup in setups.values():
        model = setup.agent_model
        if model in pinged:
            continue
        pinged.add(model)
        role = "vision-native model" if setup.arm == "without_mm" else "text-only model"
        passed, detail = ping_adhoc(OPENROUTER, model, api_key)
        tag = "ok" if passed else "FAIL"
        print(f"  [{tag}] {role}: {model}" + (f" - {detail}" if not passed else ""))
        ok = ok and passed

        if setup.mm_model and setup.mm_model not in pinged:
            pinged.add(setup.mm_model)
            passed, detail = ping_adhoc(OPENROUTER, setup.mm_model, api_key)
            tag = "ok" if passed else "FAIL"
            print(
                f"  [{tag}] mm backend: {setup.mm_model}" + (f" - {detail}" if not passed else "")
            )
            ok = ok and passed

    passed, detail = ping_judge(judge)
    tag = "ok" if passed else "FAIL"
    print(f"  [{tag}] judge: {judge.model}" + (f" - {detail}" if not passed else ""))
    ok = ok and passed

    return ok


def run_setup(
    setup: Setup,
    *,
    cases: list[EvalCase],
    store: MmBenchStore,
    grader: Grader,
    sandboxes: SandboxManager,
    primer: str,
    runs: int,
    timeout_s: int,
    stream: bool,
) -> str:
    """Run one setup over all cases, persisting each (case, arm) result. Returns the session id."""
    adapter = Assistant("pi")
    adapter.cmd = _pi_cmd(setup.agent_model)
    if not adapter.is_installed():
        raise SystemExit(f"pi not installed; cannot run setup {setup.key}")

    profile_name = setup.label
    sid = store.start_session(
        assistant="pi",
        profile_name=profile_name,
        base_url=OPENROUTER,
        model=setup.agent_model,
    )
    print(
        f"\n== setup {setup.key}: {setup.label} "
        f"(pi / agent={setup.agent_model} / mm={setup.mm_model or 'none'} / arm={setup.arm}) =="
    )

    failed_runs = 0
    try:
        for run_index in range(runs):
            if runs > 1:
                print(f"  -- run {run_index + 1}/{runs} --")
            rid: str | None = None
            t0 = time.perf_counter()
            try:
                rid = store.start_run(sid, run_index)
                for case in cases:
                    source = case.resolve_dataset(DATASETS_ROOT)
                    sandbox = sandboxes.materialize(
                        source,
                        assistant="pi",
                        profile=profile_name,
                        case_id=case.id,
                        arm=setup.arm,
                        run_index=run_index,
                        keep=False,
                    )
                    if stream:
                        print(f"\n┌─ {setup.label} · {case.id} · {setup.arm} " + "─" * 24)
                    try:
                        result = adapter.run(
                            case,
                            arm=setup.arm,
                            input_path=sandbox.path,
                            primer=primer,
                            profile_name=(setup.profile.name if setup.profile else None),
                            config_dir=(setup.profile.config_dir if setup.profile else None),
                            timeout_s=min(case.timeout_s, timeout_s),
                            stream=stream,
                        )
                        grade = grader.grade(case, result, sandbox.path)
                        store.record_case_result(
                            rid,
                            sid,
                            CaseResult(
                                case_id=case.id,
                                arm=setup.arm,
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
                                mm_used=(
                                    (1 if result.mm_commands_used else 0)
                                    if setup.arm == "with_mm"
                                    else None
                                ),
                                mm_commands_used=result.mm_commands_used,
                                failure_mode=grade.failure_mode,
                                final_output=result.final_output,
                                stderr=result.stderr,
                                mm_log=result.mm_log,
                                token_total=(
                                    result.token_usage.total_tokens if result.token_usage else None
                                ),
                                token_usage_json=(
                                    result.token_usage.to_json() if result.token_usage else ""
                                ),
                                mm_token_total=(
                                    result.mm_token_usage.total_tokens
                                    if result.mm_token_usage
                                    else None
                                ),
                                mm_token_usage_json=(
                                    result.mm_token_usage.to_json() if result.mm_token_usage else ""
                                ),
                            ),
                        )
                        _persist_artifacts(case, sandbox.path, sid, setup.arm)
                        print(
                            f"  {case.id:34} correctness={grade.correctness:6.1f} "
                            f"checks={grade.checkpoint_score:.2f} judge={grade.judge_score} "
                            f"speed={result.elapsed_s:5.0f}s "
                            f"mm={result.mm_commands_used or '-'} "
                            f"fail={grade.failure_mode or '-'}"
                        )
                    finally:
                        sandbox.dispose()
            except JudgeError as error:
                failed_runs += 1
                if rid is not None:
                    store.void_run(rid)
                    rid = None
                print(f"  ! judge failed on run {run_index + 1}: {error}")
            finally:
                if rid is not None:
                    store.finish_run(rid, round(time.perf_counter() - t0, 2))
        status = "completed" if failed_runs < runs else "failed"
        print(
            f"  setup {setup.key}: {runs - failed_runs}/{runs} runs succeeded"
            + (f" ({failed_runs} judge failures)" if failed_runs else "")
        )
    finally:
        store.finish_session(sid, status=status or "failed")
    return sid


def report(
    store: MmBenchStore,
    session_ids: list[str] | None = None,
) -> None:
    """Print the per-case + aggregate comparison table from the scratch DB.

    Every value is cumulated over all runs in scope: per-case cells show the
    mean correctness and mean speed across that setup's runs of the case, and
    the summary rows (MEAN correctness, MEAN speed, completed) are computed
    over all case-runs. Each setup column is flagged ``@k=<runs>``.

    When ``session_ids`` is given, only aggregate results from those sessions
    (the sessions created in this invocation). When None, aggregate all
    results in the DB.
    """
    select = (
        "SELECT profile_name, case_id, run_id, correctness, speed_s, "
        "task_completion, failure_mode FROM case_results"
    )
    if session_ids is not None:
        placeholders = ",".join("?" for _ in session_ids)
        rows = store.conn.execute(
            f"{select} WHERE session_id IN ({placeholders}) ORDER BY case_id, profile_name",
            session_ids,
        ).fetchall()
    else:
        rows = store.conn.execute(f"{select} ORDER BY case_id, profile_name").fetchall()
    if not rows:
        print("no results in scratch DB yet")
        return
    by_case: dict[str, dict[str, list[dict]]] = {}
    run_ids: dict[str, set[str]] = {}
    for r in rows:
        by_case.setdefault(r["case_id"], {}).setdefault(r["profile_name"], []).append(dict(r))
        run_ids.setdefault(r["profile_name"], set()).add(r["run_id"])

    labels = sorted(run_ids)
    headers = {label: f"{label} @k={len(run_ids[label])}" for label in labels}
    width = max(18, *(len(h) for h in headers.values()))
    print(f"\n{'case':34}  " + "  ".join(f"{headers[label]:>{width}}" for label in labels))
    print("-" * (34 + (width + 2) * len(labels)))
    sums = {label: {"correctness": 0.0, "speed": 0.0, "n": 0, "completed": 0} for label in labels}
    for case_id, cells in sorted(by_case.items()):
        parts = [f"{case_id:34}"]
        for label in labels:
            cell_runs = cells.get(label)
            if not cell_runs:
                parts.append(f"{'—':>{width}}")
                continue
            k = len(cell_runs)
            correctness = sum(c["correctness"] or 0.0 for c in cell_runs) / k
            speed = sum(c["speed_s"] or 0.0 for c in cell_runs) / k
            completed = sum(1 for c in cell_runs if c["task_completion"])
            fail_counts: dict[str, int] = {}
            for c in cell_runs:
                mode = c["failure_mode"] or ("" if c["task_completion"] else "incomplete")
                if mode:
                    fail_counts[mode] = fail_counts.get(mode, 0) + 1
            marks = [f"{mode} {count}/{k}" for mode, count in sorted(fail_counts.items())]
            tag = f" [{', '.join(marks)}]" if marks else ""
            parts.append(f"{correctness:5.1f}@{speed:4.0f}s{tag}".rjust(width))
            sums[label]["correctness"] += sum(c["correctness"] or 0.0 for c in cell_runs)
            sums[label]["speed"] += sum(c["speed_s"] or 0.0 for c in cell_runs)
            sums[label]["n"] += k
            sums[label]["completed"] += completed
        print("  ".join(parts))

    print("-" * (34 + (width + 2) * len(labels)))
    parts = [f"{'MEAN correctness':34}"]
    for label in labels:
        count = sums[label]["n"] or 1
        parts.append(f"{(sums[label]['correctness'] / count):>{width}.1f}")
    print("  ".join(parts))
    parts = [f"{'MEAN speed (s)':34}"]
    for label in labels:
        count = sums[label]["n"] or 1
        parts.append(f"{(sums[label]['speed'] / count):>{width}.0f}")
    print("  ".join(parts))
    parts = [f"{'completed (case-runs)':34}"]
    for label in labels:
        parts.append(f"{sums[label]['completed']}/{sums[label]['n']}".rjust(width))
    print("  ".join(parts))


def main(argv: list[str] | None = None) -> None:
    """Run selected comparison setups or print existing results."""
    ap = argparse.ArgumentParser(description="Scratch: text-only+mm vs vision model.")
    ap.add_argument(
        "--vision-models",
        default=DEFAULT_VISION_MODELS,
        help=f"comma-separated OpenRouter model ids (without_mm); default: {DEFAULT_VISION_MODELS}",
    )
    ap.add_argument(
        "--text-models",
        default=DEFAULT_TEXT_MODELS,
        help=f"comma-separated OpenRouter model ids (with_mm); default: {DEFAULT_TEXT_MODELS}",
    )
    ap.add_argument(
        "--mm-backend",
        default=DEFAULT_MM_BACKEND,
        help=f"OpenRouter model id for mm backend; default: {DEFAULT_MM_BACKEND}",
    )
    ap.add_argument(
        "--setup", default="all", help="comma-separated setup keys (v0,t1,...) or 'all'"
    )
    ap.add_argument("--cases", default="", help="comma-separated case ids (default: all)")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    ap.add_argument("--runs", type=int, default=1, help="repetitions per setup")
    ap.add_argument("--stream", action="store_true", help="tee agent output live")
    ap.add_argument("--report", action="store_true", help="only print the comparison table")
    ap.add_argument("--db", default=str(SCRATCH_DB))
    args = ap.parse_args(argv)

    if args.report:
        store = MmBenchStore(args.db)
        try:
            report(store)
        finally:
            store.close()
        return

    if args.timeout <= 0:
        ap.error("--timeout must be positive")
    if args.runs < 1:
        ap.error("--runs must be at least 1")
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        ap.error("OPENROUTER_API_KEY not set")

    vision_models = [m.strip() for m in args.vision_models.split(",") if m.strip()]
    text_models = [m.strip() for m in args.text_models.split(",") if m.strip()]
    if not vision_models and not text_models:
        ap.error("at least one --vision-models or --text-models is required")
    setups = build_setups(vision_models, text_models, args.mm_backend)

    setup_keys = [key.strip() for key in args.setup.split(",") if key.strip()]
    if setup_keys == ["all"]:
        order = list(setups)
    else:
        invalid = [key for key in setup_keys if key not in setups]
        if not setup_keys or invalid:
            ap.error(f"unknown setup keys: {invalid}; valid: {sorted(setups)}")
        order = list(dict.fromkeys(setup_keys))

    ensure_dataset()
    all_cases = {case.id: case for case in load_cases()}
    selected = list(
        dict.fromkeys(case_id.strip() for case_id in args.cases.split(",") if case_id.strip())
    )
    missing = [case_id for case_id in selected if case_id not in all_cases]
    if missing:
        ap.error(f"unknown case ids: {missing}; available: {sorted(all_cases)}")
    cases = [all_cases[case_id] for case_id in selected] if selected else list(all_cases.values())

    selected_setups = {k: setups[k] for k in order}
    judge = JudgeConfig.resolve()
    print("preflight:")
    if not preflight(selected_setups, api_key, judge):
        ap.error("preflight failed; fix the issues above before running")
    print("preflight: all checks passed\n")

    setup_dict: dict[str, Setup] = {}
    try:
        setup_dict = _materialize_setups(api_key, setups, order)
        store = MmBenchStore(args.db)
        try:
            grader = Grader(use_judge=True, judge=judge)
            sandboxes = SandboxManager()
            primer = PRIMER_PATH.read_text()
            print(
                f"scratch_text_vs_vision: setups={order} cases={len(cases)} "
                f"timeout={args.timeout} judge=on db={args.db}"
            )
            session_ids: list[str] = []
            for key in order:
                sid = run_setup(
                    setup_dict[key],
                    cases=cases,
                    store=store,
                    grader=grader,
                    sandboxes=sandboxes,
                    primer=primer,
                    runs=args.runs,
                    timeout_s=args.timeout,
                    stream=args.stream,
                )
                session_ids.append(sid)
            report(store, session_ids=session_ids)
        finally:
            store.close()
    finally:
        if setup_dict:
            _remove_profiles(setup_dict)
    print(f"\nresults: {args.db}")


if __name__ == "__main__":
    main()
