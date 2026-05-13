"""One-time bootstrap for media libraries with silenced ObjC warnings.

On macOS, when two installed Python packages each ship their own copy
of an ``ffmpeg`` dylib (``cv2`` and ``av`` both do — ``cv2/.dylibs/
libavdevice.*`` and ``av/.dylibs/libavdevice.*``), the Objective-C
runtime registers the same AVFoundation classes twice and emits::

    objc[12345]: Class AVFFrameReceiver is implemented in both
        .../cv2/.dylibs/libavdevice.61.3.100.dylib (0x...) and
        .../av/.dylibs/libavdevice.62.1.100.dylib (0x...).
        One of the two will be used. Which one is undefined.

This warning comes from ``_objc_inform`` which writes directly to file
descriptor 2 — it is **not** a Python ``warnings`` entry and cannot be
filtered by ``logging.disable()`` / ``warnings.filterwarnings``.

We can't uninstall either dependency (``cv2`` is needed by
PySceneDetect's default backend, ``av`` is needed by video processing
and optional local transcription backends), so we preload both modules once under a temporary
fd-level redirect of stderr → /dev/null. Subsequent imports of
``scenedetect``/``faster_whisper`` find both modules cached in
``sys.modules`` and do **not** reload the dylibs, so no new ObjC
warnings are emitted.

The redirect window is tight — only the Python ``import`` statements
for ``cv2`` and ``av`` run with stderr pointed at /dev/null. Any real
errors during application code run with the real stderr restored.
"""

from __future__ import annotations

import os
import sys

_PRELOADED = False


def preload_media_libs() -> None:
    """Preload ``cv2`` and ``av`` once, silencing macOS ObjC duplicate-class warnings.

    Idempotent — safe to call from multiple entry points. Only the
    first call performs the redirect; subsequent calls are a no-op.

    On non-Darwin platforms the warnings don't occur, so the imports
    happen without any fd manipulation.
    """
    global _PRELOADED
    if _PRELOADED:
        return
    _PRELOADED = True

    # Prevent OpenMP abort when multiple copies of libiomp5 are loaded
    # (e.g. cv2 + torch/ctranslate2 each bundle their own copy).
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

    if sys.platform != "darwin":
        _do_imports()
        return

    # Flush any buffered Python stderr before redirecting the fd so we
    # don't lose log lines that were written but not yet drained.
    try:
        sys.stderr.flush()
    except Exception:
        pass

    saved_fd = os.dup(2)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull_fd, 2)
        try:
            _do_imports()
        finally:
            os.dup2(saved_fd, 2)
    finally:
        os.close(devnull_fd)
        os.close(saved_fd)


def _do_imports() -> None:
    """Import ``cv2`` and ``av`` — skip silently if the package is missing.

    Both are optional deps: code paths that need them check availability
    before calling into them. The whole point of the preload is to force
    the dylib load order to happen inside our redirect window; we don't
    actually use the imported modules here.
    """
    try:
        import cv2  # noqa: F401
    except Exception:
        pass
    try:
        import av  # noqa: F401
    except Exception:
        pass
