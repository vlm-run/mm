"""Modular audio transcription with automatic backend selection.

Backends (checked in priority order, first available wins):
  1. ``mlx``         — lightning-whisper-mlx on Apple Metal GPU (~3-4x on Apple Silicon)
  2. ``ctranslate2`` — faster-whisper on CPU (int8) or CUDA (float16)
  3. ``openai``      — any OpenAI-compatible ``/v1/audio/transcriptions`` endpoint

Public API::

    from mm.common.audio import transcribe, transcribe_available, list_backends

    result = transcribe("audio.wav", model="tiny")
    result = transcribe("audio.wav", backend="openai", base_url="http://localhost:11434/v1")
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
from mm.common.audio._ctranslate2 import CTranslate2Backend
from mm.common.audio._mlx import MLXBackend
from mm.common.audio._openai import OpenAIBackend

if TYPE_CHECKING:
    from mm.common.audio._base import BackendLabel

register_backend(MLXBackend())
register_backend(CTranslate2Backend())
register_backend(OpenAIBackend())


def transcribe(
    audio_path: str | Path,
    *,
    model: str = "tiny",
    language: str | None = None,
    beam_size: int = 1,
    audio_speed: float = 1.0,
    backend: BackendLabel | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> TranscriptionResult:
    """Transcribe audio using the best available (or explicitly chosen) backend.

    Args:
        audio_path: Path to audio file (WAV, MP3, etc.).
        model: Model name or size (e.g. ``"tiny"``, ``"whisper-1"``).
        language: ISO language code; ``None`` for auto-detection.
        beam_size: Beam size for local backends (1 = greedy).
        audio_speed: Speed multiplier the audio was extracted at.
            Timestamps are scaled back to original time.
        backend: Explicit backend name (``"mlx"``, ``"ctranslate2"``,
            ``"openai"``). When ``None`` the ``[transcription]`` section of
            ``mm.toml`` is consulted; if still unset, the best available
            local backend is auto-detected.
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
                "faster-whisper should be in the core mm install; "
                "for MLX on Apple Silicon: pip install mm[mlx]; "
                "for remote: set backend='openai' + base_url]"
            ),
            model_size=model,
        )

    return be.transcribe(
        Path(audio_path) if not isinstance(audio_path, Path) else audio_path,
        model=model,
        language=language,
        beam_size=beam_size,
        audio_speed=audio_speed,
    )


__all__ = [
    "TranscriptionBackend",
    "TranscriptionResult",
    "TranscriptionSegment",
    "detect_backend",
    "list_backends",
    "register_backend",
    "transcribe",
    "transcribe_available",
]
