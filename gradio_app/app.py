"""HuggingFace Spaces entry point for the mm Gradio app.

Spaces with ``sdk: gradio`` auto-discover ``app.py`` at the Space root
and invoke ``demo.launch()`` (or call ``demo`` directly if it's a
``gr.Blocks``). This module exposes ``demo`` and runs the same
mmbench-tiny preload + Gradio theme as the FastAPI variant.

The Gradio UI uses the ``mm`` package installed from PyPI (``mm-ctx``);
no local checkout is required.

Run locally:
    python -m gradio_app.app
"""

from __future__ import annotations

import logging

from gradio_app.config import data_dir
from gradio_app.data_setup import ensure_mmbench_tiny
from gradio_app.theme import build_theme
from gradio_app.ui import DESIGN_HEAD, build_ui

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("mm.gradio_app.spaces")

log.info("Data dir: %s", data_dir())
try:
    ensure_mmbench_tiny()
except Exception:
    log.exception("Failed to fetch mmbench-tiny — UI still works for any existing data")

demo = build_ui()

if __name__ == "__main__":
    demo.launch(theme=build_theme(), head=DESIGN_HEAD)
