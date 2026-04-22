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

# vlm.run brand tokens (inferred from vlm.run landing and chat.vlm.run/showdown).
# Keep these in one place so the chart and HTML shell stay in sync.
BRAND = {
    "bg": "#F5FAFF",  # page background — very pale blue
    "surface": "#FFFFFF",  # cards / panels
    "surface_tint": "#E6EDFC",  # subtle fill (chips, zebra)
    "border": "#D5E2F7",
    "border_strong": "#AAC2EC",
    "text_primary": "#010917",  # near-black navy
    "text_secondary": "#596983",
    "text_muted": "#A29F9F",
    "accent": "#1E5ACA",  # primary brand blue
    "accent_deep": "#102955",
    "accent_hover": "#2756A8",
    "accent_bright": "#4E8CFF",
    "accent_soft": "#749ADF",
}

FONT_SANS = "Geist, Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
FONT_MONO = "'Fragment Mono', 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace"

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


def task_results(task: dict) -> list:
    """Return task results list, treating missing/null as empty."""
    return task.get("results") or []


def _num(v) -> float:
    """Coerce YAML scalar (possibly None) to float; None -> 0.0."""
    try:
        return float(v) if v is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


def _fmt_sec(v) -> str:
    """Format seconds; return 'n/a' when value is missing."""
    return f"{v:.1f}s" if isinstance(v, (int, float)) else "n/a"


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
        for r in task_results(task):
            with_mm = r.get("with_mm") or {}
            without_mm = r.get("without_mm") or {}
            rows.append(
                {
                    "task": task["name"],
                    "label": None,  # filled after y_labels are built
                    "category": category(task["name"]),
                    "assistant": r["assistant"],
                    "with_mm": _num(with_mm.get("mean_s")),
                    "without_mm": _num(without_mm.get("mean_s")),
                    "with_mm_std": _num(with_mm.get("stddev_s")),
                    "without_mm_std": _num(without_mm.get("stddev_s")),
                    "speedup": parse_speedup(r.get("speedup")),
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
        font=dict(family=FONT_SANS, size=13, color=BRAND["text_primary"]),
        title=dict(
            text=(
                f"<b>Wall-clock Time per Task</b>"
                f"<br>"
                f"<span style='font-size:13px; color:{BRAND['text_secondary']}'>"
                f"Solid = with mm &nbsp; | &nbsp; Striped = without mm"
                f" &nbsp; | &nbsp; "
                f"Avg speedup: <b style='color:{BRAND['accent']}'>{mean_speedup:.1f}x</b>"
                f"</span>"
            ),
            font=dict(size=17, color=BRAND["text_primary"]),
            x=0,
            xanchor="left",
            y=0.97,
            yanchor="top",
            pad=dict(b=20),
        ),
        xaxis=dict(
            title=dict(
                text="Wall-clock time (seconds)",
                font=dict(size=13, color=BRAND["text_secondary"]),
                standoff=18,
            ),
            gridcolor=BRAND["border"],
            zeroline=True,
            zerolinecolor=BRAND["border_strong"],
            tickfont=dict(color=BRAND["text_secondary"]),
        ),
        yaxis=dict(
            autorange="reversed",
            tickfont=dict(size=12, color=BRAND["text_primary"]),
            categoryorder="array",
            categoryarray=y_labels,
        ),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.24,
            xanchor="center",
            x=0.5,
            font=dict(size=12, color=BRAND["text_primary"]),
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor=BRAND["border"],
            borderwidth=1,
        ),
        margin=dict(l=200, r=80, t=120, b=190),
        plot_bgcolor=BRAND["surface"],
        paper_bgcolor=BRAND["surface"],
    )

    return fig


def build_table_html(data: dict) -> str:
    # meta = data["meta"]
    tasks = data["tasks"]
    # assistants = meta["assistants"]

    muted = BRAND["text_muted"]
    rows_html = []
    for task in tasks:
        for r in task_results(task):
            sp = parse_speedup(r.get("speedup"))
            if sp <= 0:
                sp_cell = f'<span style="color:{muted}">n/a</span>'
                sp_color = muted
            elif sp >= 1.5:
                sp_color = BRAND["accent"]
                sp_cell = f"{sp:.2f}x"
            elif sp >= 1.0:
                sp_color = BRAND["accent_soft"]
                sp_cell = f"{sp:.2f}x"
            else:
                sp_color = BRAND["text_muted"]
                sp_cell = f"{sp:.2f}x"
            cat = category(task["name"])
            cat_color = CATEGORY_COLORS.get(cat, BRAND["text_secondary"])
            asst_label = ASSISTANT_LABELS.get(r["assistant"], r["assistant"])
            with_mm = r.get("with_mm") or {}
            without_mm = r.get("without_mm") or {}

            rows_html.append(f"""
            <tr>
                <td><span style="color:{cat_color}; font-weight:600">{cat}</span></td>
                <td>{label(task["name"])}</td>
                <td>{asst_label}</td>
                <td style="text-align:right; font-variant-numeric:tabular-nums">
                    {_fmt_sec(with_mm.get("mean_s"))}
                    <span style="color:{muted}">± {_fmt_sec(with_mm.get("stddev_s"))}</span>
                </td>
                <td style="text-align:right; font-variant-numeric:tabular-nums">
                    {_fmt_sec(without_mm.get("mean_s"))}
                    <span style="color:{muted}">± {_fmt_sec(without_mm.get("stddev_s"))}</span>
                </td>
                <td style="text-align:right; font-weight:700; color:{sp_color}">
                    {sp_cell}
                </td>
            </tr>""")

    return f"""
    <table style="width:100%; border-collapse:collapse; font-size:14px; margin-top:4px">
        <thead>
            <tr>
                <th style="padding:12px 14px; text-align:left">Category</th>
                <th style="padding:12px 14px; text-align:left">Task</th>
                <th style="padding:12px 14px; text-align:left">Assistant</th>
                <th style="padding:12px 14px; text-align:right">With mm</th>
                <th style="padding:12px 14px; text-align:right">Without mm</th>
                <th style="padding:12px 14px; text-align:right">Speedup</th>
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
        for r in task_results(task):
            sp = parse_speedup(r.get("speedup"))
            if sp > 0:
                rows.append(sp)

    mean_sp = sum(rows) / len(rows) if rows else 0
    max_sp = max(rows) if rows else 0
    chart_html = fig.to_html(include_plotlyjs="cdn", full_html=False)
    table_html = build_table_html(data)
    ts = meta["timestamp"]
    mode = meta.get("mode", "n/a")
    n_tasks = meta.get("tasks_run", len(tasks))
    total_tasks = meta.get("tasks_total", "?")

    b = BRAND
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>mm Benchmark — Universal CLI Assistant · vlm.run</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Fragment+Mono&display=swap">
<style>
    :root {{
        --bg: {b["bg"]};
        --surface: {b["surface"]};
        --surface-tint: {b["surface_tint"]};
        --border: {b["border"]};
        --border-strong: {b["border_strong"]};
        --text: {b["text_primary"]};
        --text-secondary: {b["text_secondary"]};
        --text-muted: {b["text_muted"]};
        --accent: {b["accent"]};
        --accent-deep: {b["accent_deep"]};
        --accent-hover: {b["accent_hover"]};
        --accent-bright: {b["accent_bright"]};
        --accent-soft: {b["accent_soft"]};
        --font-sans: {FONT_SANS};
        --font-mono: {FONT_MONO};
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        font-family: var(--font-sans);
        background: var(--bg);
        color: var(--text);
        line-height: 1.5;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }}
    .container {{ max-width: 1200px; margin: 0 auto; padding: 40px 24px; }}
    .brand-row {{
        display: flex;
        align-items: center;
        gap: 10px;
        font-family: var(--font-mono);
        font-size: 12px;
        color: var(--accent);
        letter-spacing: 0.02em;
        margin-bottom: 16px;
    }}
    .brand-row .dot {{
        width: 6px;
        height: 6px;
        background: var(--accent);
        border-radius: 50%;
        display: inline-block;
    }}
    .header {{
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 32px;
        padding-bottom: 24px;
        border-bottom: 1px solid var(--border);
    }}
    .header h1 {{
        font-size: 28px;
        font-weight: 600;
        letter-spacing: -0.025em;
        color: var(--text);
    }}
    .header h1 span {{
        color: var(--text-secondary);
        font-weight: 400;
    }}
    .meta {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px 20px;
        font-size: 13px;
        color: var(--text-secondary);
        margin-top: 10px;
    }}
    .meta strong {{ color: var(--text); font-weight: 500; }}
    .kpi-row {{
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 16px;
        margin-bottom: 32px;
    }}
    .kpi {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 22px 24px;
        position: relative;
        overflow: hidden;
    }}
    .kpi::before {{
        content: "";
        position: absolute;
        inset: 0 auto 0 0;
        width: 3px;
        background: var(--accent);
    }}
    .kpi.accent-deep::before {{ background: var(--accent-deep); }}
    .kpi.accent-soft::before {{ background: var(--accent-soft); }}
    .kpi .value {{
        font-size: 34px;
        font-weight: 600;
        font-variant-numeric: tabular-nums;
        letter-spacing: -0.03em;
        color: var(--accent);
    }}
    .kpi.accent-deep .value {{ color: var(--accent-deep); }}
    .kpi.accent-soft .value {{ color: var(--text); }}
    .kpi .label {{
        font-size: 12px;
        color: var(--text-secondary);
        margin-top: 4px;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-weight: 500;
    }}
    .panel {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 20px;
        margin-bottom: 24px;
    }}
    .panel h3 {{
        font-size: 15px;
        font-weight: 600;
        color: var(--text);
        margin-bottom: 12px;
        letter-spacing: -0.01em;
    }}
    .panel table {{ font-family: var(--font-sans); }}
    .panel tr:nth-child(even) {{ background: var(--bg); }}
    .panel td, .panel th {{ padding: 10px 14px; }}
    .panel td {{ border-top: 1px solid var(--border); }}
    .panel thead tr {{
        background: var(--text) !important;
        color: var(--surface);
    }}
    code, .mono {{ font-family: var(--font-mono); }}
    .footer {{
        margin-top: 32px;
        padding-top: 20px;
        border-top: 1px solid var(--border);
        font-size: 12px;
        color: var(--text-muted);
        display: flex;
        justify-content: space-between;
        font-family: var(--font-mono);
    }}
    .footer a {{ color: var(--accent); text-decoration: none; }}
    .footer a:hover {{ color: var(--accent-hover); }}
</style>
</head>
<body>
<div class="container">
    <div class="brand-row">
        <span class="dot"></span>
        <span>vlm.run</span>
        <span style="color: var(--text-muted)">/</span>
        <span style="color: var(--text-secondary)">mm benchmark</span>
    </div>
    <div class="header">
        <div>
            <h1>mm <span>Universal CLI Assistant Benchmark</span></h1>
            <div class="meta">
                <span>Run <strong class="mono">{ts}</strong></span>
                <span>Mode <strong>{mode}</strong> ({n_tasks}/{total_tasks} tasks)</span>
                <span>Data <strong>{meta["file_count"]} files</strong> ({meta.get("total_size_bytes", 0) / 1e6:.0f} MB)</span>
                <span>Runs <strong>{meta["runs"]}</strong> per command</span>
                <span>Assistants <strong>{", ".join(ASSISTANT_LABELS.get(a, a) for a in meta["assistants"])}</strong></span>
            </div>
        </div>
    </div>

    <div class="kpi-row">
        <div class="kpi">
            <div class="value">{mean_sp:.1f}x</div>
            <div class="label">Average speedup with mm</div>
        </div>
        <div class="kpi accent-deep">
            <div class="value">{max_sp:.1f}x</div>
            <div class="label">Peak speedup</div>
        </div>
        <div class="kpi accent-soft">
            <div class="value">{n_tasks}</div>
            <div class="label">Tasks benchmarked</div>
        </div>
    </div>

    <div class="panel">
        {chart_html}
    </div>

    <div class="panel">
        <h3>Detailed Results</h3>
        {table_html}
    </div>

    <div class="footer">
        <span>Generated by <a href="https://vlm.run">vlm.run</a> · mm benchmark suite</span>
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
                for r in task_results(task):
                    if r["assistant"] == asst:
                        speedups.append(parse_speedup(r.get("speedup")))
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
        line_color=BRAND["border_strong"],
        annotation_text="1x (no speedup)",
        annotation_font_color=BRAND["text_muted"],
    )

    fig.update_layout(
        title=dict(
            text="<b>Speedup Trend Across Runs</b>",
            font=dict(size=18, color=BRAND["text_primary"]),
        ),
        xaxis_title="Run timestamp",
        yaxis_title="Speedup (x)",
        height=500,
        template="plotly_white",
        font=dict(family=FONT_SANS, size=13, color=BRAND["text_primary"]),
        plot_bgcolor=BRAND["surface"],
        paper_bgcolor=BRAND["surface"],
        xaxis=dict(gridcolor=BRAND["border"]),
        yaxis=dict(gridcolor=BRAND["border"]),
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
