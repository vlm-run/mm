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

import asyncio
import fcntl
import json
import logging
import os
import pty
import signal
import struct
import termios
import threading
from contextlib import asynccontextmanager
from typing import AsyncIterator

import gradio as gr
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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


def _reap_pid(pid: int) -> None:
    """Blocking-waitpid in a daemon thread so the event loop is never paused."""
    try:
        os.waitpid(pid, 0)
    except (ChildProcessError, OSError):
        pass


def _terminate_pty_child(pid: int) -> None:
    """SIGKILL the PTY session group, then reap off-thread.

    ``pty.fork()`` calls ``setsid()`` in the child, so ``pid`` is also the
    session/process-group leader. Killing the group catches any subshells
    bash spawned. Reaping is delegated to a daemon thread to keep the
    asyncio loop responsive even if the kernel is slow to deliver SIGKILL.
    """
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return
    threading.Thread(target=_reap_pid, args=(pid,), daemon=True).start()


@app.websocket("/ws/terminal")
async def terminal_ws(ws: WebSocket) -> None:
    """PTY-backed terminal — bridges xterm.js (browser) to a login shell.

    Frames from the client are JSON: ``{"type":"input","data":"..."}`` for
    keystrokes and ``{"type":"resize","rows":N,"cols":M}`` for window size.
    PTY output is sent back as binary frames.

    PTY reads run via ``loop.add_reader`` on a non-blocking master fd —
    not ``run_in_executor`` — because on macOS closing a fd does not
    unblock another thread's ``os.read`` on it, which would deadlock
    the executor thread permanently after each session.
    """
    await ws.accept()
    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.closerange(3, 1024)
        except OSError:
            pass
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["PS1"] = "mm $ "
        env["BASH_SILENCE_DEPRECATION_WARNING"] = "1"
        try:
            os.chdir(data_dir())
        except OSError:
            pass
        bash_init = "export PS1='mm $ '; mm; exec /bin/bash --noprofile --norc -i"
        try:
            os.execvpe(
                "/bin/bash",
                ["/bin/bash", "--noprofile", "--norc", "-c", bash_init],
                env,
            )
        except FileNotFoundError:
            os.execvpe("/bin/sh", ["/bin/sh", "-c", "mm; exec /bin/sh -i"], env)

    os.set_blocking(fd, False)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    def on_readable() -> None:
        try:
            data = os.read(fd, 4096)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        queue.put_nowait(data if data else None)

    loop.add_reader(fd, on_readable)

    async def pump_pty_to_ws() -> None:
        while True:
            chunk = await queue.get()
            if chunk is None:
                return
            try:
                await ws.send_bytes(chunk)
            except (RuntimeError, WebSocketDisconnect):
                return

    pump = asyncio.create_task(pump_pty_to_ws())
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            text = msg.get("text")
            if text is not None:
                try:
                    obj = json.loads(text)
                except json.JSONDecodeError:
                    os.write(fd, text.encode("utf-8"))
                    continue
                kind = obj.get("type")
                if kind == "resize":
                    rows = int(obj.get("rows") or 24)
                    cols = int(obj.get("cols") or 80)
                    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
                elif kind == "input":
                    os.write(fd, str(obj.get("data", "")).encode("utf-8"))
            elif msg.get("bytes"):
                os.write(fd, msg["bytes"])
    except WebSocketDisconnect:
        pass
    finally:
        try:
            loop.remove_reader(fd)
        except (OSError, ValueError):
            pass
        pump.cancel()
        try:
            os.close(fd)
        except OSError:
            pass
        _terminate_pty_child(pid)


app = gr.mount_gradio_app(
    app,
    build_ui(),
    path="/",
    head=DESIGN_HEAD,
    theme=build_theme(),
)
