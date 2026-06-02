"""End-to-end tests for the harness, store, sweep, and analysis layers.

Drives the deterministic mock adapter (no external creds), so these exercise
sandboxing, scoring, persistence, idempotent resume, and the leaderboard/uplift
aggregations exactly as a real run would.
"""

from __future__ import annotations

import pytest

from mmbench_agents import analysis, dataset
from mmbench_agents.adapters import register
from mmbench_agents.adapters.cli import CliAdapter
from mmbench_agents.harness import Harness
from mmbench_agents.store import Store
from mmbench_agents.sweep import Sweep, SweepConfig
from mmbench_agents.tasks import TASKS_BY_ID
from mmbench_agents.types import (
    AssistantSpec,
    FailureMode,
    MmCondition,
    Profile,
    SweepMode,
    TrialKey,
)


def _sweep(tmp_path, **kwargs):
    config = SweepConfig(
        sweep_mode=SweepMode.ASSISTANT,
        assistants=[AssistantSpec("mock-strong", "mock-strong")],
        tasks=[TASKS_BY_ID["manifest"], TASKS_BY_ID["needle"]],
        **kwargs,
    )
    store = Store(tmp_path / "runs.db")
    sweep = Sweep(Harness(sandbox_root=tmp_path), store)
    run_id = sweep.run(config, dataset_hash=dataset.pinned_hash())
    return store, run_id


def test_sweep_runs_baseline_and_mm_arms(tmp_path):
    store, run_id = _sweep(tmp_path)
    rows = store.trials(run_id)
    assert len(rows) == 4  # 2 tasks x (baseline + mm)
    conditions = {r["mm_condition"] for r in rows}
    assert conditions == {"baseline", "mm"}
    for row in rows:
        if row["mm_condition"] == "baseline":
            assert row["mm_calls"] == 0
            assert row["profile"] == "none"
        else:
            assert row["mm_commands"]


def test_sweep_is_idempotent_and_resumable(tmp_path):
    store, run_id = _sweep(tmp_path)
    key = TrialKey("mock-strong", "none", MmCondition.BASELINE, "manifest", 0)
    assert store.has_trial(run_id, key)
    before = len(store.trials(run_id))
    Sweep(Harness(sandbox_root=tmp_path), store)._run_or_skip(
        run_id,
        SweepConfig(sweep_mode=SweepMode.ASSISTANT, assistants=[]),
        _plan_for(key),
    )
    assert len(store.trials(run_id)) == before


def _plan_for(key: TrialKey):
    from mmbench_agents.sweep import TrialPlan

    return TrialPlan(
        assistant=AssistantSpec(key.assistant, key.assistant),
        profile=Profile(name=key.profile),
        condition=key.mm_condition,
        task=TASKS_BY_ID[key.task_id],
        repeat=key.repeat,
    )


def test_analysis_reports_uplift_and_leaderboard(tmp_path):
    store, run_id = _sweep(tmp_path, repeats=2)
    rows = store.trials(run_id)
    board = analysis.leaderboard(rows)
    assert board and board[0]["assistant"] == "mock-strong"
    assert 0.0 <= board[0]["mean_overall"] <= 100.0
    for entry in analysis.uplift(rows):
        assert entry["speedup"] > 1.0  # mock models mm as faster


def test_unavailable_cli_assistant_is_skipped(tmp_path):
    register(CliAdapter("ghost", "definitely-not-a-real-binary-xyz"))
    result = Harness(sandbox_root=tmp_path).run_trial(
        assistant=AssistantSpec("ghost", "ghost", "definitely-not-a-real-binary-xyz"),
        task=TASKS_BY_ID["manifest"],
        condition=MmCondition.MM,
        profile=Profile.none(),
    )
    assert result.failure_mode is FailureMode.SKIPPED


def test_report_renders_html(tmp_path):
    pytest.importorskip("plotly")
    from mmbench_agents.report import build_report

    store, run_id = _sweep(tmp_path)
    out = build_report(store, run_id, tmp_path / "report.html")
    html = out.read_text()
    assert "Leaderboard" in html and "mm speedup" in html
