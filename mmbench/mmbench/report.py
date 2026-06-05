"""Static HTML report for a single run (Plotly, no server required).

Renders the leaderboard, the baseline-vs-``mm`` uplift, the per-assistant
speedup, and per-task scores into one self-contained HTML file. Mirrors the
interactive dashboard so a run can be shared as an artifact. Plotly is imported
lazily, so importing this module is cheap and the core package stays dependency-free.
"""

from __future__ import annotations

from pathlib import Path

from mmbench import analysis
from mmbench.store import Store

_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>mmbench-agents — run {run_id}</title>
<style>body{{font-family:system-ui,sans-serif;margin:24px;color:#111}}
h1{{margin-bottom:0}} .sub{{color:#666;margin-top:4px}} .grid>div{{margin:18px 0}}
.section-title{{margin:22px 0 6px}}
#lead{{border-collapse:collapse;width:100%;font-size:14px}}
#lead td,#lead th{{border:1px solid #ddd;padding:9px 12px;text-align:left}}
#lead thead th{{background:#fafafa;border-bottom:2px solid #ccc}}
#lead tbody tr:nth-child(even){{background:#fafafa}}
#lead .num{{text-align:right;font-variant-numeric:tabular-nums}}
#lead .up{{color:#0a7;font-weight:600}} #lead .down{{color:#c33;font-weight:600}}</style>
</head><body>
<h1>mmbench-agents</h1>
<div class="sub">run {run_id} · {label} · dataset {dataset_hash}</div>
<h3 class="section-title">Leaderboard</h3>
{headline}
<div class="grid">{body}</div>
</body></html>
"""


def _pct(value: float | None) -> str:
    """Format a 0–1 success rate as a percentage, or an em dash when absent."""
    return "—" if value is None else f"{value * 100:.0f}%"


def _headline_table(rows: list[dict]) -> str:
    """Render the Next.js-style leaderboard table as standalone HTML."""
    head = (
        "<tr><th>#</th><th>model</th><th>assistant</th><th class='num'>avg duration</th>"
        "<th class='num'>success</th><th class='num'>success w/ mm</th><th class='num'>Δ</th></tr>"
    )
    body = []
    for i, r in enumerate(rows, start=1):
        base = r["success_baseline"]
        delta = None if base is None else r["success_mm"] - base
        cls = "" if delta is None else "up" if delta > 0 else "down" if delta < 0 else ""
        dtxt = "—" if delta is None else f"{'+' if delta > 0 else ''}{delta * 100:.0f}%"
        body.append(
            f"<tr><td class='num'>{i}</td><td>{r['model']}</td><td>{r['assistant']}</td>"
            f"<td class='num'>{r['avg_duration_s']:.2f}s</td>"
            f"<td class='num'>{_pct(base)}</td><td class='num'>{_pct(r['success_mm'])}</td>"
            f"<td class='num {cls}'>{dtxt}</td></tr>"
        )
    return f"<table id='lead'><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"


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
        headline=_headline_table(analysis.headline_leaderboard(rows)),
        body="".join(f"<div>{p}</div>" for p in parts),
    )
    out = Path(out_path)
    out.write_text(html)
    return out
