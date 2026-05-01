"""mm Gradio + FastAPI app.

Exposes group-2 surface (cat with ``mode=fast|accurate``, grep with
``--semantic`` / ``--pre-index``), a list-directory endpoint that mirrors
``mm find ./data --tree``, and profile management — both as a JSON HTTP
API under ``/api`` and as a Gradio UI mounted at ``/``.
"""

__version__ = "0.1.0"
