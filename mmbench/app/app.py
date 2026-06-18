"""Dashboard: FastAPI + a self-contained HTML page (static/index.html) over the
JSON API. ``MMBENCH_DB`` overrides the results DB.

    uv run python -m mmbench.app.app   # http://localhost:9095
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from . import db

STATIC = Path(__file__).resolve().parent / "static"
DB_PATH = Path(os.environ["MMBENCH_DB"]) if os.environ.get("MMBENCH_DB") else db.DEFAULT_DB_PATH

app = FastAPI(title="mmbench")


@app.get("/api/leaderboard")
def api_leaderboard() -> list[dict]:
    return db.leaderboard(DB_PATH)


@app.get("/api/cases")
def api_cases() -> list[dict]:
    return db.case_breakdown(DB_PATH)


@app.get("/api/sessions")
def api_sessions() -> list[dict]:
    return db.sessions(DB_PATH)


@app.get("/api/session/{session_id}")
def api_session(session_id: str) -> dict:
    return db.session_detail(session_id, DB_PATH)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=9095)


if __name__ == "__main__":
    main()
