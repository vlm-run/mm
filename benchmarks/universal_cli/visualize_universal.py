#!/usr/bin/env python3
"""Visualize universal CLI assistant benchmark results.

Reads YAML results from benchmarks/universal_cli/run_results/run_*.yaml and
generates an interactive HTML report with charts and tables.

Usage:
    uvx --from plotly --with pyyaml python benchmarks/universal_cli/visualize_universal.py
    uvx --from plotly --with pyyaml python benchmarks/universal_cli/visualize_universal.py run_20260416_135037.yaml
    uvx --from plotly --with pyyaml python benchmarks/universal_cli/visualize_universal.py --compare
"""

from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
import yaml

RESULTS_DIR = Path(__file__).parent / "run_results"

TASK_LABELS = {
    "directory_survey": "Directory Survey",
    "pdf_extraction": "PDF Extraction",
    "image_metadata": "Image Metadata",
    "video_metadata": "Video Metadata",
    "audio_metadata": "Audio Metadata",
    "token_cost_estimate": "Token Cost Estimate",
    "recent_files": "Recent Files",
    "batch_metadata": "Batch Metadata",
    "evidence_package": "Evidence Package",
    "document_search": "Document Search",
    "document_token_cost": "Document Token Cost",
    "document_volume_by_dir": "Document Volume by Dir",
    "document_format_audit": "Document Format Audit",
    "hires_images": "Hi-Res Image Filter",
    "image_format_audit": "Image Format Audit",
    "image_token_cost": "Image Token Cost",
    "video_resolution_check": "Video Resolution Check",
    "video_codec_audit": "Video Codec Audit",
    "tree_overview": "Tree Overview",
    "project_token_budget": "Project Token Budget",
}

TASK_CATEGORIES = {
    "directory_survey": "Cross-modal",
    "token_cost_estimate": "Cross-modal",
    "recent_files": "Cross-modal",
    "batch_metadata": "Cross-modal",
    "evidence_package": "Cross-modal",
    "pdf_extraction": "Document",
    "document_search": "Document",
    "document_token_cost": "Document",
    "document_volume_by_dir": "Document",
    "document_format_audit": "Document",
    "image_metadata": "Image",
    "hires_images": "Image",
    "image_format_audit": "Image",
    "image_token_cost": "Image",
    "video_metadata": "Video",
    "video_resolution_check": "Video",
    "video_codec_audit": "Video",
    "audio_metadata": "Audio",
    "tree_overview": "Dev",
    "project_token_budget": "Dev",
}

CATEGORY_COLORS = {
    "Cross-modal": "#8B5CF6",
    "Document": "#EF4444",
    "Image": "#F59E0B",
    "Video": "#3B82F6",
    "Audio": "#10B981",
    "Dev": "#6B7280",
}

ASSISTANT_COLORS = {
    "claude": "#D97706",
    "codex": "#059669",
    "gemini": "#2563EB",
}

ASSISTANT_LABELS = {
    "claude": "Claude Code",
    "codex": "Codex CLI",
    "gemini": "Gemini CLI",
}


def load_run(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def find_latest_run() -> Path:
    runs = sorted(RESULTS_DIR.glob("run_*.yaml"))
    if not runs:
        print("No runs found in", RESULTS_DIR)
        sys.exit(1)
    return runs[-1]


def label(task_name: str) -> str:
    return TASK_LABELS.get(task_name, task_name.replace("_", " ").title())


def category(task_name: str) -> str:
    return TASK_CATEGORIES.get(task_name, "Other")


def parse_speedup(s) -> float:
    if isinstance(s, str):
        s = s.rstrip("x")
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _desaturate(hex_color: str, factor: float = 0.45) -> str:
    """Blend a hex color toward gray by `factor` (0 = original, 1 = full gray)."""
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    gray = int(0.299 * r + 0.587 * g + 0.114 * b)

    def __h(c):
        # mix = lambda c: int(c + (gray - c) * factor)
        return int(c + (gray - c) * factor)

    return f"#{__h(r):02x}{__h(g):02x}{__h(b):02x}"


def build_single_report(data: dict, run_path: Path) -> go.Figure:
    meta = data["meta"]
    tasks = data["tasks"]
    assistants = meta["assistants"]

    # Pre-build HTML y-labels keyed by task name (populated after y_labels list)
    task_to_ylabel = {}

    rows = []
    for task in tasks:
        for r in task.get("results", []):
            rows.append(
                {
                    "task": task["name"],
                    "label": None,  # filled after y_labels are built
                    "category": category(task["name"]),
                    "assistant": r["assistant"],
                    "with_mm": r["with_mm"]["mean_s"],
                    "without_mm": r["without_mm"]["mean_s"],
                    "with_mm_std": r["with_mm"]["stddev_s"],
                    "without_mm_std": r["without_mm"]["stddev_s"],
                    "speedup": parse_speedup(r["speedup"]),
                }
            )

    n_tasks = len(tasks)
    n_assistants = len(assistants)
    mean_speedup = sum(r["speedup"] for r in rows) / len(rows) if rows else 0

    fig = go.Figure()

    # Build two-line y-axis labels: category (small, colored) above task name
    y_labels = []
    for t in tasks:
        cat = category(t["name"])
        cat_color = CATEGORY_COLORS.get(cat, "#6B7280")
        html_label = (
            f"<span style='font-size:10px; color:{cat_color}'>{cat}</span><br>{label(t['name'])}"
        )
        y_labels.append(html_label)
        task_to_ylabel[t["name"]] = html_label

    # Backfill row labels now that y_labels are built
    for r in rows:
        r["label"] = task_to_ylabel[r["task"]]

    # --- Horizontal grouped bar: with_mm vs without_mm ---
    for asst in assistants:
        asst_label = ASSISTANT_LABELS.get(asst, asst)
        asst_rows = [r for r in rows if r["assistant"] == asst]
        color = ASSISTANT_COLORS.get(asst, "#6B7280")
        color_desat = _desaturate(color, 0.55)

        # "no mm" bars — desaturated color + diagonal stripe pattern
        fig.add_trace(
            go.Bar(
                name=f"{asst_label}  \u2014  without mm",
                y=[r["label"] for r in asst_rows],
                x=[r["without_mm"] for r in asst_rows],
                error_x=dict(
                    type="data", array=[r["without_mm_std"] for r in asst_rows], thickness=1.5
                ),
                orientation="h",
                marker=dict(
                    color=color_desat,
                    opacity=0.85,
                    pattern=dict(shape="/", fgcolor="rgba(255,255,255,0.5)", size=6),
                    line=dict(color=color_desat, width=1),
                ),
                legendgroup=asst,
                legendgrouptitle_text=asst_label,
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    f"{asst_label} without mm<br>"
                    "Time: %{x:.1f}s<br>"
                    "<extra></extra>"
                ),
            )
        )

        # "+ mm" bars — solid, full saturation
        fig.add_trace(
            go.Bar(
                name=f"{asst_label}  \u2014  with mm",
                y=[r["label"] for r in asst_rows],
                x=[r["with_mm"] for r in asst_rows],
                error_x=dict(
                    type="data", array=[r["with_mm_std"] for r in asst_rows], thickness=1.5
                ),
                orientation="h",
                marker=dict(
                    color=color,
                    opacity=1.0,
                    line=dict(color=color, width=1),
                ),
                legendgroup=asst,
                hovertemplate=(
                    f"<b>%{{y}}</b><br>{asst_label} + mm<br>Time: %{{x:.1f}}s<br><extra></extra>"
                ),
            )
        )

        # Speedup annotations on bars
        for r in asst_rows:
            if r["speedup"] > 0:
                fig.add_annotation(
                    x=r["without_mm"] + r["without_mm_std"] + 2,
                    y=r["label"],
                    text=f"<b>{r['speedup']:.1f}x</b>",
                    showarrow=False,
                    font=dict(size=11, color=color),
                    xanchor="left",
                )

    bar_height = max(55, 70 - n_tasks)
    chart_height = max(550, n_tasks * bar_height * max(n_assistants, 1) + 280)

    fig.update_layout(
        barmode="group",
        bargroupgap=0.15,
        bargap=0.25,
        height=chart_height,
        template="plotly_white",
        font=dict(family="Inter, -apple-system, sans-serif", size=13),
        title=dict(
            text=(
                f"<b>Wall-clock Time per Task</b>"
                f"<br>"
                f"<span style='font-size:13px; color:#6B7280'>"
                f"Solid = with mm &nbsp; | &nbsp; Striped = without mm"
                f" &nbsp; | &nbsp; "
                f"Avg speedup: <b style='color:#059669'>{mean_speedup:.1f}x</b>"
                f"</span>"
            ),
            font=dict(size=17),
            x=0,
            xanchor="left",
            y=0.97,
            yanchor="top",
            pad=dict(b=20),
        ),
        xaxis=dict(
            title=dict(text="Wall-clock time (seconds)", font=dict(size=13)),
            gridcolor="#E5E7EB",
            zeroline=True,
            zerolinecolor="#D1D5DB",
        ),
        yaxis=dict(
            autorange="reversed",
            tickfont=dict(size=12),
            categoryorder="array",
            categoryarray=y_labels,
        ),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.14,
            xanchor="center",
            x=0.5,
            font=dict(size=12),
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#E5E7EB",
            borderwidth=1,
        ),
        margin=dict(l=200, r=80, t=120, b=140),
        plot_bgcolor="#FAFAFA",
    )

    return fig


def build_table_html(data: dict) -> str:
    # meta = data["meta"]
    tasks = data["tasks"]
    # assistants = meta["assistants"]

    rows_html = []
    for task in tasks:
        for r in task.get("results", []):
            sp = parse_speedup(r["speedup"])
            sp_color = "#059669" if sp >= 1.5 else "#D97706" if sp >= 1.0 else "#EF4444"
            cat = category(task["name"])
            cat_color = CATEGORY_COLORS.get(cat, "#6B7280")
            asst_label = ASSISTANT_LABELS.get(r["assistant"], r["assistant"])

            rows_html.append(f"""
            <tr>
                <td><span style="color:{cat_color}; font-weight:600">{cat}</span></td>
                <td>{label(task["name"])}</td>
                <td>{asst_label}</td>
                <td style="text-align:right; font-variant-numeric:tabular-nums">
                    {r["with_mm"]["mean_s"]:.1f}s
                    <span style="color:#9CA3AF">± {r["with_mm"]["stddev_s"]:.1f}s</span>
                </td>
                <td style="text-align:right; font-variant-numeric:tabular-nums">
                    {r["without_mm"]["mean_s"]:.1f}s
                    <span style="color:#9CA3AF">± {r["without_mm"]["stddev_s"]:.1f}s</span>
                </td>
                <td style="text-align:right; font-weight:700; color:{sp_color}">
                    {sp:.2f}x
                </td>
            </tr>""")

    return f"""
    <table style="width:100%; border-collapse:collapse; font-size:14px; margin-top:24px">
        <thead>
            <tr style="background:#1F2937; color:white">
                <th style="padding:10px 12px; text-align:left">Category</th>
                <th style="padding:10px 12px; text-align:left">Task</th>
                <th style="padding:10px 12px; text-align:left">Assistant</th>
                <th style="padding:10px 12px; text-align:right">With mm</th>
                <th style="padding:10px 12px; text-align:right">Without mm</th>
                <th style="padding:10px 12px; text-align:right">Speedup</th>
            </tr>
        </thead>
        <tbody>
            {"".join(rows_html)}
        </tbody>
    </table>"""


def build_full_html(fig: go.Figure, data: dict, run_path: Path) -> str:
    meta = data["meta"]
    tasks = data["tasks"]
    rows = []
    for task in tasks:
        for r in task.get("results", []):
            rows.append(parse_speedup(r["speedup"]))

    mean_sp = sum(rows) / len(rows) if rows else 0
    max_sp = max(rows) if rows else 0
    chart_html = fig.to_html(include_plotlyjs="cdn", full_html=False)
    table_html = build_table_html(data)
    ts = meta["timestamp"]
    mode = meta.get("mode", "n/a")
    n_tasks = meta.get("tasks_run", len(tasks))
    total_tasks = meta.get("tasks_total", "?")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>mm Benchmark — Universal CLI Assistant</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: #F9FAFB;
        color: #111827;
        line-height: 1.5;
    }}
    .container {{ max-width: 1200px; margin: 0 auto; padding: 32px 24px; }}
    .header {{
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 32px;
        padding-bottom: 24px;
        border-bottom: 1px solid #E5E7EB;
    }}
    .header h1 {{
        font-size: 24px;
        font-weight: 700;
        letter-spacing: -0.02em;
    }}
    .header h1 span {{ color: #6B7280; font-weight: 400; }}
    .meta {{
        display: flex;
        gap: 24px;
        font-size: 13px;
        color: #6B7280;
        margin-top: 8px;
    }}
    .meta strong {{ color: #111827; }}
    .kpi-row {{
        display: flex;
        gap: 16px;
        margin-bottom: 32px;
    }}
    .kpi {{
        flex: 1;
        background: white;
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 20px 24px;
    }}
    .kpi .value {{
        font-size: 32px;
        font-weight: 700;
        font-variant-numeric: tabular-nums;
        letter-spacing: -0.02em;
    }}
    .kpi .label {{
        font-size: 13px;
        color: #6B7280;
        margin-top: 2px;
    }}
    .kpi.green .value {{ color: #059669; }}
    .kpi.amber .value {{ color: #D97706; }}
    .kpi.blue .value  {{ color: #2563EB; }}
    .chart-container {{
        background: white;
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 32px;
    }}
    .table-container {{
        background: white;
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 16px;
        overflow-x: auto;
    }}
    .table-container table {{ font-family: inherit; }}
    .table-container tr:nth-child(even) {{ background: #F9FAFB; }}
    .table-container td, .table-container th {{ padding: 8px 12px; }}
    .table-container td {{ border-top: 1px solid #F3F4F6; }}
    .footer {{
        margin-top: 32px;
        padding-top: 16px;
        border-top: 1px solid #E5E7EB;
        font-size: 12px;
        color: #9CA3AF;
        display: flex;
        justify-content: space-between;
    }}
    .footer a {{ color: #6B7280; text-decoration: none; }}
    .footer a:hover {{ color: #111827; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <div>
            <h1>mm <span>Universal CLI Assistant Benchmark</span></h1>
            <div class="meta">
                <span>Run: <strong>{ts}</strong></span>
                <span>Mode: <strong>{mode}</strong> ({n_tasks}/{total_tasks} tasks)</span>
                <span>Data: <strong>{meta["file_count"]} files</strong> ({meta.get("total_size_bytes", 0) / 1e6:.0f} MB)</span>
                <span>Runs: <strong>{meta["runs"]}</strong> per command</span>
                <span>Assistants: <strong>{", ".join(ASSISTANT_LABELS.get(a, a) for a in meta["assistants"])}</strong></span>
            </div>
        </div>
    </div>

    <div class="kpi-row">
        <div class="kpi green">
            <div class="value">{mean_sp:.1f}x</div>
            <div class="label">Average speedup with mm</div>
        </div>
        <div class="kpi amber">
            <div class="value">{max_sp:.1f}x</div>
            <div class="label">Peak speedup</div>
        </div>
        <div class="kpi blue">
            <div class="value">{n_tasks}</div>
            <div class="label">Tasks benchmarked</div>
        </div>
    </div>

    <div class="chart-container">
        {chart_html}
    </div>

    <div class="table-container">
        <h3 style="font-size:16px; font-weight:600; margin-bottom:8px">Detailed Results</h3>
        {table_html}
    </div>

    <div class="footer">
        <span>Generated by <a href="https://github.com/nicepkg/mm">mm</a> benchmark suite</span>
        <span>Source: {run_path.name}</span>
    </div>
</div>
</body>
</html>"""


def build_comparison_report(run_paths: list[Path]) -> go.Figure:
    all_runs = []
    for p in sorted(run_paths):
        data = load_run(p)
        meta = data["meta"]
        tasks = data["tasks"]
        for asst in meta["assistants"]:
            speedups = []
            for task in tasks:
                for r in task.get("results", []):
                    if r["assistant"] == asst:
                        speedups.append(parse_speedup(r["speedup"]))
            speedups = [s for s in speedups if s > 0]
            if speedups:
                all_runs.append(
                    {
                        "run": p.stem,
                        "timestamp": meta["timestamp"],
                        "assistant": asst,
                        "mean_speedup": sum(speedups) / len(speedups),
                        "max_speedup": max(speedups),
                        "min_speedup": min(speedups),
                    }
                )

    fig = go.Figure()

    for asst in sorted({r["assistant"] for r in all_runs}):
        asst_data = [r for r in all_runs if r["assistant"] == asst]
        asst_label = ASSISTANT_LABELS.get(asst, asst)
        color = ASSISTANT_COLORS.get(asst, "#6B7280")

        fig.add_trace(
            go.Scatter(
                x=[r["timestamp"] for r in asst_data],
                y=[r["mean_speedup"] for r in asst_data],
                name=f"{asst_label} (mean)",
                mode="lines+markers",
                line=dict(color=color, width=2.5),
                marker=dict(size=9),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[r["timestamp"] for r in asst_data],
                y=[r["max_speedup"] for r in asst_data],
                name=f"{asst_label} (peak)",
                mode="lines",
                line=dict(color=color, width=1, dash="dot"),
                showlegend=False,
            )
        )

    fig.add_hline(
        y=1.0,
        line_dash="dash",
        line_color="#D1D5DB",
        annotation_text="1x (no speedup)",
        annotation_font_color="#9CA3AF",
    )

    fig.update_layout(
        title=dict(text="<b>Speedup Trend Across Runs</b>", font=dict(size=18)),
        xaxis_title="Run timestamp",
        yaxis_title="Speedup (x)",
        height=500,
        template="plotly_white",
        font=dict(family="Inter, -apple-system, sans-serif", size=13),
    )
    return fig


def main():
    compare_mode = "--compare" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if compare_mode:
        run_paths = sorted(RESULTS_DIR.glob("run_*.yaml"))
        if len(run_paths) < 2:
            print("Need at least 2 runs for comparison. Found:", len(run_paths))
            sys.exit(1)
        fig = build_comparison_report(run_paths)
        out = RESULTS_DIR / "comparison.html"
        fig.write_html(str(out), include_plotlyjs="cdn")
        print(f"Comparison report: {out}")
        return

    if args:
        run_path = RESULTS_DIR / args[0]
    else:
        run_path = find_latest_run()

    print(f"Loading: {run_path}")
    data = load_run(run_path)
    fig = build_single_report(data, run_path)

    out = run_path.with_suffix(".html")
    with open(out, "w") as f:
        f.write(build_full_html(fig, data, run_path))
    print(f"Report: {out}")


if __name__ == "__main__":
    main()
