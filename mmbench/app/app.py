"""Dashboard: FastAPI JSON API + the built Svelte SPA (static/). Source is in
mmbench/frontend (Svelte + Tailwind + Vite, built into static/). ``MMBENCH_DB``
overrides the results DB.

    uv run python -m mmbench.app.app   # http://localhost:9095
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db

STATIC = Path(__file__).resolve().parent / "static"
DB_PATH = Path(os.environ["MMBENCH_DB"]) if os.environ.get("MMBENCH_DB") else db.DEFAULT_DB_PATH
DATA_DIR = DB_PATH.parent  # cases.jsonl + _artifacts/ sit beside the DB
CASES_FILE = DATA_DIR / "cases.jsonl"
ARTIFACTS_DIR = DATA_DIR / "_artifacts"

app = FastAPI(title="mmbench")


@app.get("/api/leaderboard")
def api_leaderboard() -> list[dict]:
    return db.leaderboard(DB_PATH)


@app.get("/api/sessions")
def api_sessions() -> list[dict]:
    return db.sessions(DB_PATH)


@app.get("/api/case-breakdown")
def api_case_breakdown() -> dict:
    return db.case_breakdown(DB_PATH)


@app.get("/api/cell")
def api_cell(assistant: str, profile: str) -> dict:
    return db.cell_detail(assistant, profile, DB_PATH)


@app.get("/api/session/{session_id}")
def api_session(session_id: str) -> dict:
    return db.session_detail(session_id, DB_PATH)


@app.get("/api/transcript")
def api_transcript(session: str, case: str) -> dict:
    return db.case_transcript(session, case, DB_PATH)


@app.get("/api/case-spec")
def api_case_spec(case: str) -> dict:
    return db.case_spec(case, CASES_FILE)


@app.get("/api/artifacts")
def api_artifacts(session: str, case: str, arm: str) -> list[str]:
    return db.artifacts(session, case, arm, ARTIFACTS_DIR)


@app.get("/api/artifact-file")
def api_artifact_file(session: str, case: str, arm: str, path: str) -> FileResponse:
    p = db.artifact_path(session, case, arm, path, ARTIFACTS_DIR)
    if p is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(str(p), filename=Path(path).name)


# Built SPA (index.html + assets); html=True serves index.html for SPA routes.
# Mounted last so /api/* wins. Absent until `npm run build` in mmbench/frontend.
if STATIC.exists():
    app.mount("/", StaticFiles(directory=str(STATIC), html=True), name="static")


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=9095)


if __name__ == "__main__":
    main()
