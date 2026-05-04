"""HuggingFace Spaces entry point for the mm Gradio app.

This module is uploaded to the Space's *root* ``app.py`` by
``gradio_app/Makefile``'s ``deploy`` target. Spaces runs ``python app.py``
on boot, so ``__name__ == "__main__"`` is ``True``.

Why this isn't in ``gradio_app/app.py``:
    The plain ``app.py`` is the local-dev entrypoint and has no
    ``spaces`` dependency. This Space-specific variant patches
    ``gradio_app.ui._do_cat`` and ``gradio_app.ui._do_grep`` so any path
    that may call into faster-whisper runs inside an ``@spaces.GPU``
    wrapper:

      - ``_do_cat`` for audio file extensions (``cat <audio> -m accurate``).
      - ``_do_grep`` whenever ``semantic=True`` (the Grep tab kicks
        ``grep_semantic`` -> pre-index -> Whisper transcription on any
        audio files in the data dir).

    Patches are applied *before* ``build_ui()`` runs so the click
    handlers capture the wrapped functions. ``duration=300`` is generous
    enough for a cold model load + a 17 min audio on the A10G; non-audio
    cats and non-semantic greps stay on CPU.
"""

from __future__ import annotations

from pathlib import Path

import spaces

from gradio_app import ui as _ui

_AUDIO_EXTS: frozenset[str] = frozenset(
    {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".oga", ".aac", ".opus", ".webm", ".wma"}
)

_original_do_cat = _ui._do_cat
_original_do_grep = _ui._do_grep


@spaces.GPU(duration=300)
def _do_cat_gpu(*args, **kwargs):  # type: ignore[no-untyped-def]
    return _original_do_cat(*args, **kwargs)


@spaces.GPU(duration=300)
def _do_grep_gpu(*args, **kwargs):  # type: ignore[no-untyped-def]
    return _original_do_grep(*args, **kwargs)


def _do_cat_routed(path: str, *args, **kwargs):  # type: ignore[no-untyped-def]
    if path and Path(path).suffix.lower() in _AUDIO_EXTS:
        return _do_cat_gpu(path, *args, **kwargs)
    return _original_do_cat(path, *args, **kwargs)


def _do_grep_routed(
    pattern: str,
    directory: str,
    kind: str,
    ext: str,
    context_lines: int,
    ignore_case: bool,
    semantic: bool,
    limit: int,
):  # type: ignore[no-untyped-def]
    if semantic:
        return _do_grep_gpu(
            pattern, directory, kind, ext, context_lines, ignore_case, semantic, limit
        )
    return _original_do_grep(
        pattern, directory, kind, ext, context_lines, ignore_case, semantic, limit
    )


_ui._do_cat = _do_cat_routed
_ui._do_grep = _do_grep_routed

from gradio_app.app import demo  # noqa: E402
from gradio_app.theme import build_theme  # noqa: E402
from gradio_app.ui import DESIGN_HEAD  # noqa: E402

if __name__ == "__main__":
    demo.launch(theme=build_theme(), head=DESIGN_HEAD, ssr_mode=False)
