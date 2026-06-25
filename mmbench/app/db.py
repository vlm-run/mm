"""Dashboard read-side aggregations over the SQLite store.

Hero metric: lift (with_mm - without_mm correctness) + speedup, **averaged over all
of a cell's sessions** (a cell = one assistant/profile pair). Drill-down:
leaderboard -> cell detail (per-session trend + runs) -> session detail (per-case
results). Voided runs delete their own rows, so only surviving runs aggregate.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from statistics import mean, pstdev

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DEFAULT_DB_PATH = DATA_DIR / "mmbench.db"
CASES_FILE = DATA_DIR / "cases.jsonl"
ARTIFACTS_DIR = DATA_DIR / "_artifacts"
PASS_THRESHOLD = 60.0  # a case (case, arm, run) counts as a pass at >= this correctness


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _arm_stats(rows: list[sqlite3.Row]) -> dict:
    """Aggregate a list of case_results rows for a single arm."""
    corr = [r["correctness"] for r in rows if r["correctness"] is not None]
    spd = [r["speed_s"] for r in rows if r["speed_s"] is not None]
    mm = [r["mm_used"] for r in rows if r["mm_used"] is not None]
    tok = [r["token_total"] for r in rows if r["token_total"] is not None]
    return {
        "n": len(rows),
        "passes": sum(1 for c in corr if c >= PASS_THRESHOLD),
        "correctness": round(mean(corr), 1) if corr else None,
        "correctness_std": round(pstdev(corr), 1) if len(corr) > 1 else 0.0,
        "speed_s": round(mean(spd), 1) if spd else None,
        "completion": round(mean([r["task_completion"] or 0 for r in rows]), 2) if rows else None,
        "mm_adoption": round(mean(mm), 2) if mm else None,
        "token_total": round(mean(tok)) if tok else None,
        "token_sum": sum(tok) if tok else None,
    }


def _lift_speedup(without: dict, with_: dict) -> tuple[float | None, float | None]:
    lift = (
        round(with_["correctness"] - without["correctness"], 1)
        if without["correctness"] is not None and with_["correctness"] is not None
        else None
    )
    speedup = (
        round(without["speed_s"] / with_["speed_s"], 2)
        if without["speed_s"] and with_["speed_s"]
        else None
    )
    return lift, speedup


def _cell_model(conn: sqlite3.Connection, assistant: str, profile: str) -> tuple[str, str]:
    """The (model, base_url) from the cell's most recent session."""
    r = conn.execute(
        "SELECT model, base_url FROM sessions WHERE assistant = ? AND profile_name = ? "
        "ORDER BY started_at DESC LIMIT 1",
        (assistant, profile),
    ).fetchone()
    return (r["model"] if r else "", r["base_url"] if r else "") if r else ("", "")


def leaderboard(db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    """Ranked rows, one per (assistant, profile), averaged over ALL their sessions."""
    conn = _connect(db_path)
    try:
        cells = conn.execute(
            "SELECT assistant, profile_name, COUNT(DISTINCT session_id) AS n_sessions "
            "FROM case_results GROUP BY assistant, profile_name"
        ).fetchall()
        out = []
        for c in cells:
            a, p = c["assistant"], c["profile_name"]
            rows = conn.execute(
                "SELECT arm, correctness, speed_s, task_completion, mm_used, token_total "
                "FROM case_results WHERE assistant = ? AND profile_name = ?",
                (a, p),
            ).fetchall()
            without = _arm_stats([r for r in rows if r["arm"] == "without_mm"])
            with_ = _arm_stats([r for r in rows if r["arm"] == "with_mm"])
            lift, speedup = _lift_speedup(without, with_)
            model, base_url = _cell_model(conn, a, p)
            n_runs = conn.execute(
                "SELECT COUNT(DISTINCT run_id) FROM case_results WHERE assistant = ? AND profile_name = ?",
                (a, p),
            ).fetchone()[0]
            out.append(
                {
                    "assistant": a,
                    "profile": p,
                    "model": model,
                    "base_url": base_url,
                    "n_sessions": c["n_sessions"],
                    "n_runs": n_runs,
                    "without_mm": without,
                    "with_mm": with_,
                    "lift": lift,
                    "speedup": speedup,
                }
            )
        out.sort(key=lambda r: r["with_mm"]["correctness"] or -1, reverse=True)
        for i, r in enumerate(out, 1):
            r["rank"] = i
        return out
    finally:
        conn.close()


def sessions(db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    """Per (cell, session) with_mm correctness over time, for the trend chart."""
    conn = _connect(db_path)
    try:
        out = []
        srows = conn.execute(
            "SELECT s.session_id, s.assistant, s.profile_name, s.started_at FROM sessions s "
            "WHERE EXISTS (SELECT 1 FROM case_results c WHERE c.session_id = s.session_id) "
            "ORDER BY s.started_at"
        ).fetchall()
        for s in srows:
            with_rows = conn.execute(
                "SELECT correctness, speed_s, task_completion, mm_used, token_total "
                "FROM case_results WHERE session_id = ? AND arm = 'with_mm'",
                (s["session_id"],),
            ).fetchall()
            out.append(
                {
                    "assistant": s["assistant"],
                    "profile": s["profile_name"],
                    "started_at": s["started_at"],
                    "with_mm_correctness": _arm_stats(with_rows)["correctness"],
                }
            )
        return out
    finally:
        conn.close()


def case_breakdown(db_path: Path = DEFAULT_DB_PATH) -> dict:
    """Per (cell, case) mean correctness, for the cross-case comparison figure.

    Returns ``{"cases": [{case_id, title, archetype}], "rows": [{assistant,
    profile, case_id, without_mm, with_mm, n}]}`` averaged over all sessions/runs.
    """
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT assistant, profile_name, case_id, title, archetype, arm, "
            "AVG(correctness) AS corr, COUNT(*) AS n "
            "FROM case_results GROUP BY assistant, profile_name, case_id, arm"
        ).fetchall()
        cells: dict[tuple[str, str, str], dict] = {}
        cases: dict[str, dict] = {}
        for r in rows:
            cases.setdefault(
                r["case_id"],
                {"case_id": r["case_id"], "title": r["title"], "archetype": r["archetype"]},
            )
            e = cells.setdefault(
                (r["assistant"], r["profile_name"], r["case_id"]),
                {
                    "assistant": r["assistant"],
                    "profile": r["profile_name"],
                    "case_id": r["case_id"],
                    "without_mm": None,
                    "with_mm": None,
                    "n": 0,
                },
            )
            e[r["arm"]] = round(r["corr"], 1) if r["corr"] is not None else None
            e["n"] += r["n"]
        return {
            "cases": sorted(cases.values(), key=lambda c: c["case_id"]),
            "rows": list(cells.values()),
        }
    finally:
        conn.close()


def case_spec(case_id: str, cases_file: Path = CASES_FILE) -> dict:
    """The raw case definition (prompt, ground truth, checks, ...) from cases.jsonl."""
    if not cases_file.exists():
        return {}
    for line in cases_file.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        spec = json.loads(line)
        if spec.get("id") == case_id:
            return spec
    return {}


def artifacts(
    session_id: str, case_id: str, arm: str, artifacts_dir: Path = ARTIFACTS_DIR
) -> list[str]:
    """Relative paths of the files the agent wrote for one (session, case, arm)."""
    root = artifacts_dir / session_id / case_id / arm
    if not root.is_dir():
        return []
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def artifact_path(
    session_id: str, case_id: str, arm: str, rel: str, artifacts_dir: Path = ARTIFACTS_DIR
) -> Path | None:
    """Resolve a stored artifact file, guarding against path traversal. None if absent."""
    root = (artifacts_dir / session_id / case_id / arm).resolve()
    target = (root / rel).resolve()
    if root in target.parents and target.is_file():
        return target
    return None


def case_transcript(session_id: str, case_id: str, db_path: Path = DEFAULT_DB_PATH) -> dict:
    """Stored stdout, stderr, and mm log (latest run per arm) for one case in a session.

    Returns ``{session_id, case_id, without_mm, with_mm}`` where each arm is
    ``{final_output, stderr, mm_log, token_total, token_usage, mm_tokens}`` or
    ``None`` if that arm has no recorded run. ``mm_tokens`` is mm's own LLM token
    usage across the run's ``mm cat`` calls (0 in the without_mm arm).
    """
    conn = _connect(db_path)
    try:
        out: dict = {
            "session_id": session_id,
            "case_id": case_id,
            "without_mm": None,
            "with_mm": None,
        }
        for arm in ("without_mm", "with_mm"):
            r = conn.execute(
                "SELECT cr.final_output AS final_output, cr.stderr AS stderr, "
                "cr.mm_log AS mm_log, cr.token_total AS token_total, "
                "cr.token_usage_json AS token_usage_json, "
                "cr.mm_token_total AS mm_token_total "
                "FROM case_results cr JOIN runs r ON r.run_id = cr.run_id "
                "WHERE cr.session_id = ? AND cr.case_id = ? AND cr.arm = ? "
                "ORDER BY r.run_index DESC LIMIT 1",
                (session_id, case_id, arm),
            ).fetchone()
            if r:
                out[arm] = {
                    "final_output": r["final_output"] or "",
                    "stderr": r["stderr"] or "",
                    "mm_log": r["mm_log"] or "",
                    "token_total": r["token_total"],
                    "token_usage": json.loads(r["token_usage_json"] or "null"),
                    "mm_tokens": r["mm_token_total"] or 0,
                }
        return out
    finally:
        conn.close()


def _cell_cases(conn: sqlite3.Connection, assistant: str, profile: str) -> list[dict]:
    """Per-case mean correctness (both arms) for one cell, across all its sessions/runs."""
    rows = conn.execute(
        "SELECT case_id, title, archetype, arm, AVG(correctness) AS corr, COUNT(*) AS n "
        "FROM case_results WHERE assistant = ? AND profile_name = ? GROUP BY case_id, arm",
        (assistant, profile),
    ).fetchall()
    by_case: dict[str, dict] = {}
    for r in rows:
        e = by_case.setdefault(
            r["case_id"],
            {
                "case_id": r["case_id"],
                "title": r["title"],
                "archetype": r["archetype"],
                "without_mm": None,
                "with_mm": None,
                "n": 0,
            },
        )
        e[r["arm"]] = round(r["corr"], 1) if r["corr"] is not None else None
        e["n"] += r["n"]
    out = sorted(by_case.values(), key=lambda c: c["case_id"])
    for c in out:
        c["lift"] = (
            round(c["with_mm"] - c["without_mm"], 1)
            if c["without_mm"] is not None and c["with_mm"] is not None
            else None
        )
    return out


def cell_detail(assistant: str, profile: str, db_path: Path = DEFAULT_DB_PATH) -> dict:
    """One cell's overall scores + a per-session breakdown (drill target)."""
    conn = _connect(db_path)
    try:
        srows = conn.execute(
            "SELECT s.session_id, s.started_at, s.model, s.base_url FROM sessions s "
            "WHERE s.assistant = ? AND s.profile_name = ? "
            "AND EXISTS (SELECT 1 FROM case_results c WHERE c.session_id = s.session_id) "
            "ORDER BY s.started_at DESC",
            (assistant, profile),
        ).fetchall()
        per_session = []
        for s in srows:
            rows = conn.execute(
                "SELECT arm, correctness, speed_s, task_completion, mm_used, token_total, run_id "
                "FROM case_results WHERE session_id = ?",
                (s["session_id"],),
            ).fetchall()
            without = _arm_stats([r for r in rows if r["arm"] == "without_mm"])
            with_ = _arm_stats([r for r in rows if r["arm"] == "with_mm"])
            lift, speedup = _lift_speedup(without, with_)
            per_session.append(
                {
                    "session_id": s["session_id"],
                    "started_at": s["started_at"],
                    "n_runs": len({r["run_id"] for r in rows}),
                    "without_mm": without,
                    "with_mm": with_,
                    "lift": lift,
                    "speedup": speedup,
                }
            )
        allrows = conn.execute(
            "SELECT arm, correctness, speed_s, task_completion, mm_used, token_total "
            "FROM case_results WHERE assistant = ? AND profile_name = ?",
            (assistant, profile),
        ).fetchall()
        without = _arm_stats([r for r in allrows if r["arm"] == "without_mm"])
        with_ = _arm_stats([r for r in allrows if r["arm"] == "with_mm"])
        lift, speedup = _lift_speedup(without, with_)
        model, base_url = _cell_model(conn, assistant, profile)
        return {
            "assistant": assistant,
            "profile": profile,
            "model": model,
            "base_url": base_url,
            "overall": {"without_mm": without, "with_mm": with_, "lift": lift, "speedup": speedup},
            "cases": _cell_cases(conn, assistant, profile),
            "sessions": per_session,
        }
    finally:
        conn.close()


def session_detail(session_id: str, db_path: Path = DEFAULT_DB_PATH) -> dict:
    """One session: its runs + per-case results (with_mm vs without_mm)."""
    conn = _connect(db_path)
    try:
        s = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if s is None:
            return {}
        runs = [
            dict(r)
            for r in conn.execute(
                "SELECT run_id, run_index, elapsed_s FROM runs WHERE session_id = ? ORDER BY run_index",
                (session_id,),
            ).fetchall()
        ]
        cells = conn.execute(
            "SELECT case_id, title, archetype, difficulty, arm, correctness, judge_score, "
            "speed_s, task_completion, mm_used, mm_commands_used_json, failure_mode, "
            "token_total, token_usage_json "
            "FROM case_results WHERE session_id = ? ORDER BY case_id, arm",
            (session_id,),
        ).fetchall()
        by_case: dict[str, dict] = {}
        for c in cells:
            e = by_case.setdefault(
                c["case_id"],
                {
                    "case_id": c["case_id"],
                    "title": c["title"],
                    "archetype": c["archetype"],
                    "difficulty": c["difficulty"],
                },
            )
            e[c["arm"]] = {
                "correctness": c["correctness"],
                "judge_score": c["judge_score"],
                "speed_s": c["speed_s"],
                "mm_used": c["mm_used"],
                "mm_commands": json.loads(c["mm_commands_used_json"] or "[]"),
                "failure_mode": c["failure_mode"],
                "token_total": c["token_total"],
                "token_usage": json.loads(c["token_usage_json"] or "null"),
            }
        return {
            "session": {
                "session_id": session_id,
                "assistant": s["assistant"],
                "profile": s["profile_name"],
                "model": s["model"],
                "base_url": s["base_url"],
                "started_at": s["started_at"],
            },
            "runs": runs,
            "cases": list(by_case.values()),
        }
    finally:
        conn.close()
