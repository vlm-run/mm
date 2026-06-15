"""HuggingFace Spaces entrypoint for the mm xterm.js terminal.

Uploaded by ``gradio_app/Makefile``'s ``deploy-app`` target as the
Space's root ``app.py``. HF Spaces runs ``python app.py``, so we mount
the FastAPI app from ``gradio_app.main`` (which exposes ``/ws/terminal``
plus the Gradio UI on ``/``) on port 7860.

Why this isn't just ``demo.launch()``: the terminal UI talks to a
``/ws/terminal`` WebSocket that bridges xterm.js to a PTY. That route
lives on the FastAPI app — Gradio's standalone server doesn't see it.

GPU note: ZeroGPU's ``@spaces.GPU`` decorator runs the wrapped
function in a forked Worker subprocess and rejects coroutine functions
outright (``NotImplementedError``) — incompatible with our async WS
handler. To get full-speed audio/video accurate-mode, the Space must
run on a regular GPU (e.g. ``a10g-small`` / ``t4-small``); on
ZeroGPU, those commands fall back to CPU faster-whisper.
"""

from __future__ import annotations

import uvicorn

from gradio_app.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
