"""Aggregations over trial rows for the leaderboard, uplift, and trends.

Pure-Python (no DataFrame dependency) so it runs anywhere the store does.
Consumes the decoded rows returned by :meth:`mmbench_agents.store.Store.trials`
and produces the summaries the dashboard and static report render. ``success``
means a fully-correct, grounded answer (all sub-checks passed).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable


def _mean(values: list[float]) -> float:
    """Arithmetic mean, or 0.0 for an empty list."""
    return round(sum(values) / len(values), 4) if values else 0.0


def _success(row: dict) -> float:
    """1.0 when the trial produced a fully-correct, grounded answer."""
    return 1.0 if row.get("grounding") == 1.0 else 0.0


def _summarise(rows: list[dict]) -> dict:
    """Summary metrics for a group of trial rows."""
    return {
        "trials": len(rows),
        "success_rate": _mean([_success(r) for r in rows]),
        "mean_overall": _mean([r["overall"] for r in rows]),
        "mean_correctness": _mean([r["correctness"] for r in rows]),
        "mean_wall_s": _mean([r["wall_s"] for r in rows]),
        "mean_mm_calls": _mean([float(r["mm_calls"]) for r in rows]),
        "mean_cost_usd": _mean([r["cost_usd"] for r in rows]),
    }


def _group(rows: Iterable[dict], *keys: str) -> dict[tuple, list[dict]]:
    """Group rows by the given column names."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in keys)].append(row)
    return groups


def leaderboard(rows: list[dict]) -> list[dict]:
    """Per-assistant summary, ranked by mean overall score (desc)."""
    out = [
        {"assistant": key[0], **_summarise(group)}
        for key, group in _group(rows, "assistant").items()
    ]
    out.sort(key=lambda r: r["mean_overall"], reverse=True)
    return out


def condition_split(rows: list[dict]) -> list[dict]:
    """Per-(assistant, condition) summary."""
    return [
        {"assistant": key[0], "mm_condition": key[1], **_summarise(group)}
        for key, group in sorted(_group(rows, "assistant", "mm_condition").items())
    ]


def uplift(rows: list[dict]) -> list[dict]:
    """Per-assistant baseline-vs-``mm`` deltas (the headline signal)."""
    by_cond = _group(rows, "assistant", "mm_condition")
    out = []
    for assistant in sorted({r["assistant"] for r in rows}):
        base = by_cond.get((assistant, "baseline"))
        mm = by_cond.get((assistant, "mm"))
        if not base or not mm:
            continue
        bs, ms = _summarise(base), _summarise(mm)
        speedup = round(bs["mean_wall_s"] / ms["mean_wall_s"], 3) if ms["mean_wall_s"] else 0.0
        out.append(
            {
                "assistant": assistant,
                "baseline_overall": bs["mean_overall"],
                "mm_overall": ms["mean_overall"],
                "delta_overall": round(ms["mean_overall"] - bs["mean_overall"], 2),
                "baseline_success": bs["success_rate"],
                "mm_success": ms["success_rate"],
                "delta_success": round(ms["success_rate"] - bs["success_rate"], 4),
                "speedup": speedup,
            }
        )
    return out


def by_task(rows: list[dict]) -> list[dict]:
    """Per-(task, condition) mean overall score."""
    return [
        {"task_id": key[0], "mm_condition": key[1], **_summarise(group)}
        for key, group in sorted(_group(rows, "task_id", "mm_condition").items())
    ]


def headline_leaderboard(rows: list[dict]) -> list[dict]:
    """Next.js-evals-style leaderboard: one row per (assistant, model).

    Each row pairs the ``mm`` arm of an (assistant, profile) combination with
    that assistant's ``baseline`` arm, exposing success rate without vs. with
    ``mm`` (the analogue of "Success Rate with AGENTS.md") alongside the mean
    wall-clock duration. Ranked by with-``mm`` success rate, then by speed.

    Args:
        rows: Decoded trial rows from :meth:`mmbench_agents.store.Store.trials`.

    Returns:
        Ranked rows with ``assistant``, ``model`` (the profile), ``avg_duration_s``,
        ``success_baseline`` (``None`` when the assistant has no baseline arm),
        ``success_mm``, and the trial counts feeding each figure.
    """
    baseline = {
        key[0]: _summarise(group)
        for key, group in _group(
            [r for r in rows if r["mm_condition"] == "baseline"], "assistant"
        ).items()
    }
    out = []
    for key, group in _group(
        [r for r in rows if r["mm_condition"] == "mm"], "assistant", "profile"
    ).items():
        mm = _summarise(group)
        base = baseline.get(key[0])
        out.append(
            {
                "assistant": key[0],
                "model": key[1],
                "avg_duration_s": mm["mean_wall_s"],
                "success_baseline": base["success_rate"] if base else None,
                "success_mm": mm["success_rate"],
                "mm_trials": mm["trials"],
                "baseline_trials": base["trials"] if base else 0,
            }
        )
    out.sort(key=lambda r: (-r["success_mm"], r["avg_duration_s"]))
    return out
