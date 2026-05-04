"""FastAPI + Gradio entry-point for the mm app.

The FastAPI surface lives at:
    GET    /api/list-directory
    POST   /api/cat
    POST   /api/grep
    GET    /api/profiles
    GET    /api/profiles/active
    POST   /api/profiles
    PATCH  /api/profiles/{name}
    POST   /api/profiles/{name}/use
    DELETE /api/profiles/{name}
    GET    /api/health
    GET    /docs (Swagger UI)

The Gradio UI is mounted at ``/`` and talks to the same in-process Python
backend as the API.

Run with::

    uv run uvicorn gradio_app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import gradio as gr
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gradio_app import __version__
from gradio_app.config import data_dir
from gradio_app.data_setup import ensure_mmbench_tiny
from gradio_app.routes import router
from gradio_app.theme import build_theme
from gradio_app.ui import DESIGN_HEAD, build_ui

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("mm.gradio_app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log.info("Data dir: %s", data_dir())
    try:
        ensure_mmbench_tiny()
    except Exception:
        log.exception("Failed to fetch mmbench-tiny — endpoints still work for any existing data")
    yield


app = FastAPI(
    title="mm app",
    description=(
        "HTTP + Gradio surface around the mm Python API: cat/grep with full "
        "mode + override support, directory tree listing, and LLM profile "
        "management."
    ),
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(router, prefix="/api")

app = gr.mount_gradio_app(
    app,
    build_ui(),
    path="/",
    head=DESIGN_HEAD,
    theme=build_theme(),
)
