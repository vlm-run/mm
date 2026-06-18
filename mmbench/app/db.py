"""Dashboard read-side aggregations over the SQLite store.

Hero metric: lift (treatment - baseline correctness) + speedup. Leaderboard uses
the latest session per (assistant, profile) that has data; ``sessions`` is the
full history for trends. Voided runs delete their own rows, so only surviving runs
aggregate.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from statistics import mean, pstdev

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "benchmarks" / "data" / "mmbench.db"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _latest_sessions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """The most recent session per (assistant, profile) that has results.

    Voided runs delete their own rows, so a session shows only the data from its
    surviving (completed) runs; a session left with no data is skipped.
    """
    rows = conn.execute(
        "SELECT s.* FROM sessions s WHERE EXISTS "
        "(SELECT 1 FROM case_results c WHERE c.session_id = s.session_id) "
        "ORDER BY s.started_at"
    ).fetchall()
    latest: dict[tuple[str, str], sqlite3.Row] = {}
    for r in rows:
        latest[(r["assistant"], r["profile_name"])] = r
    return list(latest.values())


def _arm_stats(conn: sqlite3.Connection, session_id: str, arm: str) -> dict:
    """Mean correctness/speed and counts for one arm of a session."""
    rows = conn.execute(
        "SELECT correctness, speed_s, task_completion, mm_used FROM case_results "
        "WHERE session_id = ? AND arm = ?",
        (session_id, arm),
    ).fetchall()
    corr = [r["correctness"] for r in rows if r["correctness"] is not None]
    spd = [r["speed_s"] for r in rows if r["speed_s"] is not None]
    mm_used = [r["mm_used"] for r in rows if r["mm_used"] is not None]
    return {
        "n": len(rows),
        "correctness": round(mean(corr), 1) if corr else None,
        "correctness_std": round(pstdev(corr), 1) if len(corr) > 1 else 0.0,
        "speed_s": round(mean(spd), 1) if spd else None,
        "speed_std": round(pstdev(spd), 1) if len(spd) > 1 else 0.0,
        "completion": round(mean([r["task_completion"] or 0 for r in rows]), 2) if rows else None,
        "mm_adoption": round(mean(mm_used), 2) if mm_used else None,
    }


def leaderboard(db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    """One row per (assistant, profile): baseline vs treatment, lift, speedup."""
    conn = _connect(db_path)
    try:
        out = []
        for s in _latest_sessions(conn):
            base = _arm_stats(conn, s["session_id"], "baseline")
            treat = _arm_stats(conn, s["session_id"], "treatment")
            lift = (
                round(treat["correctness"] - base["correctness"], 1)
                if base["correctness"] is not None and treat["correctness"] is not None
                else None
            )
            speedup = (
                round(base["speed_s"] / treat["speed_s"], 2)
                if base["speed_s"] and treat["speed_s"]
                else None
            )
            out.append(
                {
                    "assistant": s["assistant"],
                    "profile": s["profile_name"],
                    "model": s["model"],
                    "session_id": s["session_id"],
                    "started_at": s["started_at"],
                    "baseline": base,
                    "treatment": treat,
                    "lift": lift,
                    "speedup": speedup,
                }
            )
        out.sort(key=lambda r: r["treatment"]["correctness"] or -1, reverse=True)
        return out
    finally:
        conn.close()


def case_breakdown(db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    """Per case x assistant: baseline vs treatment correctness (latest sessions)."""
    conn = _connect(db_path)
    try:
        sessions = _latest_sessions(conn)
        rows: list[dict] = []
        for s in sessions:
            for cr in conn.execute(
                "SELECT case_id, title, archetype, arm, correctness, speed_s, mm_used "
                "FROM case_results WHERE session_id = ?",
                (s["session_id"],),
            ).fetchall():
                rows.append(
                    {
                        "assistant": s["assistant"],
                        "profile": s["profile_name"],
                        "case_id": cr["case_id"],
                        "title": cr["title"],
                        "archetype": cr["archetype"],
                        "arm": cr["arm"],
                        "correctness": cr["correctness"],
                        "speed_s": cr["speed_s"],
                        "mm_used": cr["mm_used"],
                    }
                )
        return rows
    finally:
        conn.close()


def sessions(db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    """Every session with its treatment correctness, oldest first (for trends)."""
    conn = _connect(db_path)
    try:
        out = []
        q = (
            "SELECT s.* FROM sessions s WHERE EXISTS "
            "(SELECT 1 FROM case_results c WHERE c.session_id = s.session_id) "
            "ORDER BY s.started_at"
        )
        for s in conn.execute(q).fetchall():
            treat = _arm_stats(conn, s["session_id"], "treatment")
            base = _arm_stats(conn, s["session_id"], "baseline")
            out.append(
                {
                    "session_id": s["session_id"],
                    "assistant": s["assistant"],
                    "profile": s["profile_name"],
                    "started_at": s["started_at"],
                    "status": s["status"],
                    "treatment_correctness": treat["correctness"],
                    "baseline_correctness": base["correctness"],
                }
            )
        return out
    finally:
        conn.close()


def session_detail(session_id: str, db_path: Path = DEFAULT_DB_PATH) -> dict:
    """All case results for one session, paired baseline vs treatment per case."""
    conn = _connect(db_path)
    try:
        s = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if s is None:
            return {}
        cells = conn.execute(
            "SELECT case_id, title, archetype, difficulty, arm, correctness, "
            "checkpoint_score, judge_score, speed_s, task_completion, mm_used, "
            "mm_commands_used_json, failure_mode, final_output "
            "FROM case_results WHERE session_id = ? ORDER BY case_id, arm",
            (session_id,),
        ).fetchall()
        by_case: dict[str, dict] = {}
        for c in cells:
            entry = by_case.setdefault(
                c["case_id"],
                {"case_id": c["case_id"], "title": c["title"], "archetype": c["archetype"]},
            )
            entry[c["arm"]] = dict(c)
        return {
            "session": dict(s),
            "cases": list(by_case.values()),
        }
    finally:
        conn.close()
