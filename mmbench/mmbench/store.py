"""SQLite persistence for benchmark runs and trial results.

Two tables: ``runs`` (one row per sweep invocation) and ``trials`` (one row per
executed trial). The trial primary key is the full
``(run_id, assistant, profile, mm_condition, task_id, repeat)`` coordinate, so
re-running a sweep is idempotent and resumable — :meth:`Store.has_trial` lets
the orchestrator skip work already recorded. Rich fields (metrics, score,
answer, sub-checks) are stored as JSON; the flat score columns are duplicated
for fast leaderboard aggregation.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from mmbench.types import TrialKey, TrialResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    sweep_mode  TEXT NOT NULL,
    label       TEXT NOT NULL DEFAULT '',
    dataset_hash TEXT NOT NULL DEFAULT '',
    meta        TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS trials (
    run_id       INTEGER NOT NULL,
    assistant    TEXT NOT NULL,
    profile      TEXT NOT NULL,
    mm_condition TEXT NOT NULL,
    task_id      TEXT NOT NULL,
    repeat       INTEGER NOT NULL,
    failure_mode TEXT NOT NULL,
    completion   REAL NOT NULL,
    correctness  REAL NOT NULL,
    grounding    REAL NOT NULL,
    overall      REAL NOT NULL,
    wall_s       REAL NOT NULL,
    turns        INTEGER NOT NULL,
    mm_calls     INTEGER NOT NULL,
    cost_usd     REAL NOT NULL,
    metrics      TEXT NOT NULL,
    score        TEXT NOT NULL,
    answer       TEXT NOT NULL,
    mm_commands  TEXT NOT NULL,
    sub_checks   TEXT NOT NULL,
    raw_output   TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    PRIMARY KEY (run_id, assistant, profile, mm_condition, task_id, repeat)
);
"""


def _now() -> str:
    """UTC timestamp in ISO-8601."""
    return datetime.now(timezone.utc).isoformat()


class Store:
    """A thin SQLite wrapper for benchmark runs and trials."""

    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        """Close the underlying connection."""
        self.conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def start_run(
        self, sweep_mode: str, label: str = "", dataset_hash: str = "", meta: dict | None = None
    ) -> int:
        """Insert a new run row and return its id."""
        cur = self.conn.execute(
            "INSERT INTO runs (created_at, sweep_mode, label, dataset_hash, meta) "
            "VALUES (?, ?, ?, ?, ?)",
            (_now(), sweep_mode, label, dataset_hash, json.dumps(meta or {})),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def has_trial(self, run_id: int, key: TrialKey) -> bool:
        """Whether a trial for ``key`` is already recorded under ``run_id``."""
        row = self.conn.execute(
            "SELECT 1 FROM trials WHERE run_id=? AND assistant=? AND profile=? "
            "AND mm_condition=? AND task_id=? AND repeat=?",
            (run_id, key.assistant, key.profile, key.mm_condition.value, key.task_id, key.repeat),
        ).fetchone()
        return row is not None

    def save_trial(self, run_id: int, result: TrialResult) -> None:
        """Upsert one trial result under ``run_id``."""
        key, metrics, score = result.key, result.metrics, result.score
        self.conn.execute(
            "INSERT OR REPLACE INTO trials VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                key.assistant,
                key.profile,
                key.mm_condition.value,
                key.task_id,
                key.repeat,
                result.failure_mode.value,
                score.completion,
                score.correctness,
                score.grounding,
                score.overall,
                metrics.wall_s,
                metrics.turns,
                metrics.mm_calls,
                metrics.cost_usd,
                json.dumps(asdict(metrics)),
                json.dumps(asdict(score)),
                json.dumps(result.answer),
                json.dumps(result.mm_commands),
                json.dumps([asdict(c) for c in result.sub_checks]),
                result.raw_output,
                _now(),
            ),
        )
        self.conn.commit()

    def runs(self) -> list[dict]:
        """All runs, newest first."""
        rows = self.conn.execute("SELECT * FROM runs ORDER BY run_id DESC").fetchall()
        return [dict(r) for r in rows]

    def trials(self, run_id: int) -> list[dict]:
        """All trial rows for a run, with JSON columns decoded."""
        rows = self.conn.execute(
            "SELECT * FROM trials WHERE run_id=? ORDER BY task_id, assistant, profile, "
            "mm_condition, repeat",
            (run_id,),
        ).fetchall()
        decoded = []
        for row in rows:
            item = dict(row)
            for col in ("metrics", "score", "answer", "mm_commands", "sub_checks"):
                item[col] = json.loads(item[col])
            decoded.append(item)
        return decoded
