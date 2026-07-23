"""SQLite results store: sessions -> runs -> case_results.

Three tables model the result hierarchy:

    sessions   one (assistant, profile) pair benchmarked at a point in time
      -> runs        one full pass over all cases x both arms within a session
        -> case_results   one (case, arm) outcome: correctness, speed, grounding

per (assistant, profile) and skips completed cells; ``void_run`` drops a run's rows
when the judge fails mid-run.

Example:
    >>> store = MmBenchStore(":memory:")
    >>> sid = store.start_session(mode="B", assistant="claude",
    ...     profile_name="gateway", base_url="https://...", model="qwen/...")
    >>> rid = store.start_run(sid, run_index=0)
    >>> store.record_case_result(rid, sid, CaseResult(...))
    >>> store.finish_run(rid, elapsed_s=42.0)
    >>> store.finish_session(sid)
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "mmbench.db"

ARMS = ("without_mm", "with_mm")

FAILURE_MODES = (
    "api_error",
    "timeout",
    "tool_error",
    "content_incorrect",
    "format_violation",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    assistant    TEXT NOT NULL,
    profile_name TEXT NOT NULL,
    base_url     TEXT,
    model        TEXT,
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    status       TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS runs (
    run_id     TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    run_index  INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    ended_at   TEXT,
    elapsed_s  REAL
);

CREATE TABLE IF NOT EXISTS case_results (
    run_id                TEXT NOT NULL REFERENCES runs(run_id),
    session_id            TEXT NOT NULL REFERENCES sessions(session_id),
    assistant             TEXT NOT NULL,
    profile_name          TEXT NOT NULL,
    case_id               TEXT NOT NULL,
    title                 TEXT,
    difficulty            TEXT,
    archetype             TEXT,
    modality_json         TEXT,
    mm_commands_json      TEXT,
    arm                   TEXT NOT NULL,
    correctness           REAL,
    checkpoint_score      REAL,
    judge_score           INTEGER,
    speed_s               REAL,
    task_completion       INTEGER,
    mm_used               INTEGER,
    mm_commands_used_json TEXT,
    failure_mode          TEXT,
    final_output          TEXT,
    stderr                TEXT,
    mm_log                TEXT,
    token_total           INTEGER,
    token_usage_json      TEXT,
    mm_token_total        INTEGER,
    mm_token_usage_json   TEXT,
    created_at            TEXT NOT NULL,
    PRIMARY KEY (run_id, case_id, arm)
);

CREATE INDEX IF NOT EXISTS idx_cr_session ON case_results(session_id);
CREATE INDEX IF NOT EXISTS idx_cr_case    ON case_results(case_id);
CREATE INDEX IF NOT EXISTS idx_cr_arm     ON case_results(arm);
CREATE INDEX IF NOT EXISTS idx_cr_model   ON case_results(assistant, profile_name);
CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);
"""


def _now() -> str:
    """UTC timestamp in ISO-8601, second precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class CaseResult:
    """One (case, arm) outcome, ready to persist.

    The scoring fields (``correctness``, ``checkpoint_score``, ``judge_score``)
    are filled by the grader; ``speed_s`` and ``final_output`` by the assistant
    adapter. List/dict fields are JSON-encoded at write time.
    """

    case_id: str
    arm: str
    title: str = ""
    difficulty: str = ""
    archetype: str = ""
    modality: list[str] = field(default_factory=list)
    mm_commands: list[str] = field(default_factory=list)
    correctness: float | None = None
    checkpoint_score: float | None = None
    judge_score: int | None = None
    speed_s: float | None = None
    task_completion: int | None = None
    mm_used: int | None = None
    mm_commands_used: list[str] = field(default_factory=list)
    failure_mode: str | None = None
    final_output: str = ""
    stderr: str = ""
    mm_log: str = ""
    token_total: int | None = None
    token_usage_json: str = ""
    mm_token_total: int | None = None
    mm_token_usage_json: str = ""

    def __post_init__(self) -> None:
        if self.arm not in ARMS:
            raise ValueError(f"arm must be one of {ARMS}, got {self.arm!r}")
        if self.failure_mode is not None and self.failure_mode not in FAILURE_MODES:
            raise ValueError(
                f"failure_mode must be one of {FAILURE_MODES}, got {self.failure_mode!r}"
            )


class MmBenchStore:
    """Thin, typed wrapper over the SQLite results store.

    Args:
        db_path: SQLite file path, or ``":memory:"``. Parent dirs are created.
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def start_session(
        self,
        *,
        assistant: str,
        profile_name: str,
        base_url: str | None,
        model: str | None,
    ) -> str:
        """Open a session for one (assistant, profile) pair. Returns its id."""
        session_id = uuid.uuid4().hex
        self.conn.execute(
            "INSERT INTO sessions (session_id, assistant, profile_name, "
            "base_url, model, started_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, assistant, profile_name, base_url, model, _now()),
        )
        self.conn.commit()
        return session_id

    def finish_session(self, session_id: str, status: str = "completed") -> None:
        """Mark a session ended."""
        self.conn.execute(
            "UPDATE sessions SET ended_at = ?, status = ? WHERE session_id = ?",
            (_now(), status, session_id),
        )
        self.conn.commit()

    def start_run(self, session_id: str, run_index: int) -> str:
        """Open a run within a session. Returns its id."""
        run_id = uuid.uuid4().hex
        self.conn.execute(
            "INSERT INTO runs (run_id, session_id, run_index, started_at) VALUES (?, ?, ?, ?)",
            (run_id, session_id, run_index, _now()),
        )
        self.conn.commit()
        return run_id

    def finish_run(self, run_id: str, elapsed_s: float) -> None:
        """Mark a run ended with its wall-clock elapsed time."""
        self.conn.execute(
            "UPDATE runs SET ended_at = ?, elapsed_s = ? WHERE run_id = ?",
            (_now(), elapsed_s, run_id),
        )
        self.conn.commit()

    def void_run(self, run_id: str) -> None:
        """Discard a run: delete its case results and the run row.

        Used when the judge becomes unreachable mid-run; the run's data is dropped
        (so no run mixes judged and checks-only cells) while the session's other
        completed runs are kept.
        """
        self.conn.execute("DELETE FROM case_results WHERE run_id = ?", (run_id,))
        self.conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
        self.conn.commit()

    def record_case_result(self, run_id: str, session_id: str, result: CaseResult) -> None:
        """Upsert one (case, arm) result. Re-recording replaces the cell."""
        row = asdict(result)
        self.conn.execute(
            "INSERT OR REPLACE INTO case_results ("
            "run_id, session_id, assistant, profile_name, case_id, title, "
            "difficulty, archetype, modality_json, mm_commands_json, arm, "
            "correctness, checkpoint_score, judge_score, speed_s, "
            "task_completion, mm_used, mm_commands_used_json, failure_mode, "
            "final_output, stderr, mm_log, token_total, token_usage_json, "
            "mm_token_total, mm_token_usage_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                session_id,
                self._session_field(session_id, "assistant"),
                self._session_field(session_id, "profile_name"),
                row["case_id"],
                row["title"],
                row["difficulty"],
                row["archetype"],
                json.dumps(row["modality"]),
                json.dumps(row["mm_commands"]),
                row["arm"],
                row["correctness"],
                row["checkpoint_score"],
                row["judge_score"],
                row["speed_s"],
                row["task_completion"],
                row["mm_used"],
                json.dumps(row["mm_commands_used"]),
                row["failure_mode"],
                row["final_output"],
                row["stderr"],
                row["mm_log"],
                row["token_total"],
                row["token_usage_json"],
                row["mm_token_total"],
                row["mm_token_usage_json"],
                _now(),
            ),
        )
        self.conn.commit()

    def _session_field(self, session_id: str, column: str) -> str:
        """Read a single column off a session row (assistant / profile_name)."""
        cur = self.conn.execute(
            f"SELECT {column} FROM sessions WHERE session_id = ?", (session_id,)
        )
        hit = cur.fetchone()
        if hit is None:
            raise KeyError(f"unknown session_id {session_id!r}")
        return hit[column]

    def latest_session_id(self, assistant: str, profile_name: str) -> str | None:
        """Most recent session id for an (assistant, profile) pair, or None."""
        cur = self.conn.execute(
            "SELECT session_id FROM sessions WHERE assistant = ? AND profile_name = ? "
            "ORDER BY started_at DESC LIMIT 1",
            (assistant, profile_name),
        )
        hit = cur.fetchone()
        return hit["session_id"] if hit else None

    def completed_cells(self, session_id: str) -> set[tuple[str, str]]:
        """(case_id, arm) cells in a session that completed (task_completion=1).

        Used for resume: a cell already completed is skipped rather than re-run.
        """
        cur = self.conn.execute(
            "SELECT case_id, arm FROM case_results WHERE session_id = ? AND task_completion = 1",
            (session_id,),
        )
        return {(r["case_id"], r["arm"]) for r in cur.fetchall()}

    def close(self) -> None:
        """Close the underlying connection."""
        self.conn.close()
