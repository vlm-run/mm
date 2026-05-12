"""Audio transcription with pluggable backends.

All *available* backends are registered at import time.  The OpenAI-
compatible backend is always present; local backends are added when
their extras are installed:

* ``openai`` (priority 10, always available) — VLM Run gateway
  (``https://gateway.vlm.run/v1/openai``, model ``nvidia/parakeet-tdt-0.6b-v3``).
* ``mlx`` (priority 20) — Apple Metal GPU.  ``pip install mm-ctx[mlx]``
* ``ctranslate2`` (priority 30) — CPU int8 / CUDA float16.  ``pip install mm-ctx[gpu]``

Auto-detection picks the lowest-priority (= most preferred) available
backend.  Callers can always override with ``backend="openai"`` to
force the gateway even when a local backend is installed.

Public API::

    from mm.common.audio import transcribe, transcribe_available, list_backends

    # Auto-detect best backend
    result = transcribe("audio.wav")

    # Force gateway regardless of installed extras
    result = transcribe("audio.wav", backend="openai")
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from mm.common.audio._base import (
    TranscriptionBackend,
    TranscriptionResult,
    TranscriptionSegment,
    detect_backend,
    list_backends,
    register_backend,
    transcribe_available,
)

if TYPE_CHECKING:
    from mm.common.audio._base import BackendLabel


def _register_backends() -> str:
    """Register all available backends and return the best one's name.

    The OpenAI backend is always registered.  Local backends (mlx,
    ctranslate2) are added when their respective extras are installed.
    Returns the name of the highest-priority (lowest number) backend.
    """
    from mm.common.audio._openai import OpenAIBackend

    register_backend(OpenAIBackend())
    best = "openai"

    try:
        import lightning_whisper_mlx  # noqa: F401
        import mlx.core as mx

        if mx.metal.is_available():
            from mm.common.audio._mlx import MLXBackend

            register_backend(MLXBackend())
            best = "mlx"
    except (ImportError, AttributeError):
        pass

    try:
        import faster_whisper  # noqa: F401

        from mm.common.audio._ctranslate2 import CTranslate2Backend

        register_backend(CTranslate2Backend())
        if best == "openai":
            best = "ctranslate2"
    except ImportError:
        pass

    return best


ACTIVE_VARIANT = _register_backends()

GATEWAY_MODEL = "nvidia/parakeet-tdt-0.6b-v3"


def transcribe(
    audio_path: str | Path,
    *,
    model: str | None = None,
    language: str | None = None,
    beam_size: int = 1,
    audio_speed: float = 1.0,
    backend: BackendLabel | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> TranscriptionResult:
    """Transcribe audio using the registered backend.

    By default, calls the VLM Run gateway's OpenAI-compatible
    transcription endpoint with ``nvidia/parakeet-tdt-0.6b-v3``.
    Override ``base_url`` to point at localhost or
    ``https://api.openai.com/v1`` (set ``OPENAI_API_KEY``).

    Args:
        audio_path: Path to audio file (WAV, MP3, etc.).
        model: Model name.  ``None`` picks a sensible default for
            the active backend (``nvidia/parakeet-tdt-0.6b-v3`` for
            the gateway, ``tiny`` for local backends).
        language: ISO language code; ``None`` for auto-detection.
        beam_size: Beam size for local backends (1 = greedy).
        audio_speed: Speed multiplier the audio was extracted at.
            Timestamps are scaled back to original time.
        backend: Explicit backend name (``"openai"``, ``"mlx"``,
            ``"ctranslate2"``). When ``None`` the ``[transcription]``
            section of ``mm.toml`` is consulted; if still unset, the
            registered backend is used.
        base_url: Custom base URL for the ``openai`` backend.
        api_key: API key for the ``openai`` backend.

    Returns:
        TranscriptionResult with text, segments, language, timing, and
        backend metadata.
    """
    if backend is None or base_url is None or api_key is None:
        from mm.config import get_transcription_config

        cfg = get_transcription_config()
        backend = backend or cfg.backend
        base_url = base_url or cfg.base_url
        api_key = api_key or cfg.api_key

    be = detect_backend(name=backend, base_url=base_url, api_key=api_key)
    if be is None:
        return TranscriptionResult(
            text=(
                "[no transcription backend available — "
                "the openai package is required for the default gateway backend; "
                "for local MLX: pip install mm-ctx[mlx]; "
                "for local GPU/CPU: pip install mm-ctx[gpu]]"
            ),
            model_size=model or "",
        )

    if model is None:
        model = GATEWAY_MODEL if be.name == "openai" else "tiny"

    return be.transcribe(
        Path(audio_path) if not isinstance(audio_path, Path) else audio_path,
        model=model,
        language=language,
        beam_size=beam_size,
        audio_speed=audio_speed,
    )


__all__ = [
    "ACTIVE_VARIANT",
    "GATEWAY_MODEL",
    "TranscriptionBackend",
    "TranscriptionResult",
    "TranscriptionSegment",
    "detect_backend",
    "list_backends",
    "register_backend",
    "transcribe",
    "transcribe_available",
]
