"""Static HTML report for a single run (Plotly, no server required).

Renders the leaderboard, the baseline-vs-``mm`` uplift, the per-assistant
speedup, and per-task scores into one self-contained HTML file. Mirrors the
interactive dashboard so a run can be shared as an artifact. Plotly is imported
lazily, so importing this module is cheap and the core package stays dependency-free.
"""

from __future__ import annotations

from pathlib import Path

from mmbench_agents import analysis
from mmbench_agents.store import Store

_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>mmbench-agents — run {run_id}</title>
<style>body{{font-family:system-ui,sans-serif;margin:24px;color:#111}}
h1{{margin-bottom:0}} .sub{{color:#666;margin-top:4px}} .grid>div{{margin:18px 0}}</style>
</head><body>
<h1>mmbench-agents</h1>
<div class="sub">run {run_id} · {label} · dataset {dataset_hash}</div>
<div class="grid">{body}</div>
</body></html>
"""


def _bar(x: list, y: list, title: str, ytitle: str):
    """A single-series bar figure."""
    import plotly.graph_objects as go

    fig = go.Figure(go.Bar(x=x, y=y))
    fig.update_layout(title=title, yaxis_title=ytitle, height=380, margin=dict(t=48, b=40))
    return fig


def _grouped(rows: list[dict], cat: str, title: str, ytitle: str, key: str):
    """A grouped bar figure split by ``mm_condition``."""
    import plotly.graph_objects as go

    cats = sorted({r[cat] for r in rows})
    fig = go.Figure()
    for cond in ("baseline", "mm"):
        lookup = {r[cat]: r[key] for r in rows if r["mm_condition"] == cond}
        fig.add_bar(name=cond, x=cats, y=[lookup.get(c, 0) for c in cats])
    fig.update_layout(
        barmode="group", title=title, yaxis_title=ytitle, height=380, margin=dict(t=48, b=40)
    )
    return fig


def build_report(store: Store, run_id: int, out_path: Path | str) -> Path:
    """Render ``run_id`` to a self-contained HTML file and return its path."""
    rows = store.trials(run_id)
    run = next((r for r in store.runs() if r["run_id"] == run_id), {})
    board = analysis.leaderboard(rows)
    ups = analysis.uplift(rows)

    figs = [
        _bar(
            [r["assistant"] for r in board],
            [r["mean_overall"] for r in board],
            "Leaderboard — mean overall",
            "overall (0–100)",
        ),
        _grouped(
            analysis.condition_split(rows),
            "assistant",
            "Baseline vs mm — mean overall",
            "overall (0–100)",
            "mean_overall",
        ),
        _bar(
            [r["assistant"] for r in ups],
            [r["speedup"] for r in ups],
            "mm speedup (baseline wall ÷ mm wall)",
            "×",
        ),
        _grouped(
            analysis.by_task(rows),
            "task_id",
            "Per-task — mean overall",
            "overall (0–100)",
            "mean_overall",
        ),
    ]

    parts = []
    for i, fig in enumerate(figs):
        parts.append(fig.to_html(full_html=False, include_plotlyjs="cdn" if i == 0 else False))
    html = _PAGE.format(
        run_id=run_id,
        label=run.get("label", ""),
        dataset_hash=(run.get("dataset_hash", "") or "")[:12],
        body="".join(f"<div>{p}</div>" for p in parts),
    )
    out = Path(out_path)
    out.write_text(html)
    return out
