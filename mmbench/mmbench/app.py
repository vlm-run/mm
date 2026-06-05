"""FastAPI dashboard for browsing benchmark runs.

Serves a single-page dashboard (Plotly via CDN) plus a small JSON API over the
store: per-run leaderboard, baseline-vs-``mm`` uplift, per-task scores, the
trial explorer (prompt, the exact ``mm`` commands the agent ran, and the
verifier sub-checks), and cross-run trends. FastAPI/uvicorn are imported lazily
so the core package has no web dependency.

Run with::

    python -m mmbench serve --db benchmark.db
"""

from __future__ import annotations

from pathlib import Path

from mmbench import analysis
from mmbench.store import Store


def create_app(db_path: str | Path):
    """Build the FastAPI app bound to the SQLite store at ``db_path``."""
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse

    app = FastAPI(title="mmbench-agents")
    db = str(db_path)

    def store() -> Store:
        return Store(db)

    @app.get("/api/runs")
    def runs() -> JSONResponse:
        with store() as s:
            return JSONResponse(s.runs())

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: int) -> JSONResponse:
        with store() as s:
            rows = s.trials(run_id)
            return JSONResponse(
                {
                    "headline": analysis.headline_leaderboard(rows),
                    "leaderboard": analysis.leaderboard(rows),
                    "condition_split": analysis.condition_split(rows),
                    "uplift": analysis.uplift(rows),
                    "by_task": analysis.by_task(rows),
                }
            )

    @app.get("/api/runs/{run_id}/trials")
    def run_trials(run_id: int) -> JSONResponse:
        with store() as s:
            return JSONResponse(s.trials(run_id))

    @app.get("/api/trends")
    def trends() -> JSONResponse:
        with store() as s:
            series = []
            for run in s.runs():
                board = analysis.leaderboard(s.trials(run["run_id"]))
                series.append(
                    {
                        "run_id": run["run_id"],
                        "created_at": run["created_at"],
                        "label": run["label"],
                        "mean_overall": round(sum(b["mean_overall"] for b in board) / len(board), 4)
                        if board
                        else 0.0,
                    }
                )
            return JSONResponse(list(reversed(series)))

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _INDEX_HTML

    return app


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: ``serve --db benchmark.db [--host H] [--port P]``."""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(prog="mmbench-agents serve")
    parser.add_argument("--db", default="benchmark.db")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8008)
    args = parser.parse_args(argv)
    uvicorn.run(create_app(args.db), host=args.host, port=args.port)
    return 0


_INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>mmbench-agents</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
body{font-family:system-ui,sans-serif;margin:20px;color:#111}
header{display:flex;gap:12px;align-items:center}
select{padding:6px} .chart{margin:18px 0}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border:1px solid #ddd;padding:6px;text-align:left}
.pass{color:#0a7} .fail{color:#c33}
#lead{font-size:14px} #lead td,#lead th{padding:9px 12px}
#lead thead th{background:#fafafa;border-bottom:2px solid #ccc}
#lead tbody tr:nth-child(even){background:#fafafa}
#lead .num{text-align:right;font-variant-numeric:tabular-nums}
#lead .up{color:#0a7;font-weight:600} #lead .down{color:#c33;font-weight:600}
.section-title{margin:24px 0 6px}
</style></head><body>
<header><h1>mmbench-agents</h1>
<label>run <select id="run"></select></label>
<span id="meta" style="color:#666"></span></header>
<h3 class="section-title">Leaderboard</h3>
<div id="lead"></div>
<div id="trend" class="chart"></div>
<div id="board" class="chart"></div>
<div id="uplift" class="chart"></div>
<div id="task" class="chart"></div>
<h3>Trials</h3><div id="trials"></div>
<script>
async function j(u){return (await fetch(u)).json()}
function grouped(rows,cat,key){
  const cats=[...new Set(rows.map(r=>r[cat]))];
  return ["baseline","mm"].map(c=>({type:"bar",name:c,x:cats,
    y:cats.map(k=>{const m=rows.find(r=>r[cat]===k&&r.mm_condition===c);return m?m[key]:0})}));
}
async function loadTrends(){
  const t=await j("/api/trends");
  Plotly.newPlot("trend",[{type:"scatter",mode:"lines+markers",
    x:t.map(r=>r.run_id),y:t.map(r=>r.mean_overall)}],
    {title:"Trend — mean overall across runs",height:320});
}
function pct(v){return v==null?"—":(v*100).toFixed(0)+"%"}
function leadTable(rows){
  const head="<tr><th>#</th><th>model</th><th>assistant</th><th class='num'>avg duration</th>"+
    "<th class='num'>success</th><th class='num'>success w/ mm</th><th class='num'>Δ</th></tr>";
  const body=rows.map((r,i)=>{
    const d=r.success_baseline==null?null:r.success_mm-r.success_baseline;
    const cls=d==null?"":d>0?"up":d<0?"down":"";
    const dtxt=d==null?"—":(d>0?"+":"")+(d*100).toFixed(0)+"%";
    return `<tr><td class='num'>${i+1}</td><td>${r.model}</td><td>${r.assistant}</td>`+
      `<td class='num'>${r.avg_duration_s.toFixed(2)}s</td>`+
      `<td class='num'>${pct(r.success_baseline)}</td>`+
      `<td class='num'>${pct(r.success_mm)}</td>`+
      `<td class='num ${cls}'>${dtxt}</td></tr>`;
  }).join("");
  return `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
}
async function loadRun(id){
  const d=await j(`/api/runs/${id}`);
  document.getElementById("lead").innerHTML=leadTable(d.headline);
  Plotly.newPlot("board",[{type:"bar",x:d.leaderboard.map(r=>r.assistant),
    y:d.leaderboard.map(r=>r.mean_overall)}],{title:"Leaderboard — mean overall",height:360});
  Plotly.newPlot("uplift",grouped(d.condition_split,"assistant","mean_overall"),
    {title:"Baseline vs mm — mean overall",barmode:"group",height:360});
  Plotly.newPlot("task",grouped(d.by_task,"task_id","mean_overall"),
    {title:"Per-task — mean overall",barmode:"group",height:360});
  const tr=await j(`/api/runs/${id}/trials`);
  const head="<tr><th>task</th><th>assistant</th><th>profile</th><th>cond</th>"+
    "<th>overall</th><th>wall_s</th><th>mm calls</th><th>commands</th><th>checks</th></tr>";
  document.getElementById("trials").innerHTML="<table>"+head+tr.map(r=>{
    const checks=r.sub_checks.map(c=>`<span class="${c.passed?'pass':'fail'}">${c.name}</span>`).join(", ");
    return `<tr><td>${r.task_id}</td><td>${r.assistant}</td><td>${r.profile}</td>`+
      `<td>${r.mm_condition}</td><td>${r.overall}</td><td>${r.wall_s}</td>`+
      `<td>${r.mm_calls}</td><td>${r.mm_commands.join(" ")||"-"}</td><td>${checks}</td></tr>`;
  }).join("")+"</table>";
}
(async()=>{
  await loadTrends();
  const runs=await j("/api/runs");
  const sel=document.getElementById("run");
  sel.innerHTML=runs.map(r=>`<option value="${r.run_id}">#${r.run_id} ${r.label||r.sweep_mode}</option>`).join("");
  sel.onchange=()=>loadRun(sel.value);
  if(runs.length) loadRun(runs[0].run_id);
})();
</script></body></html>
"""
