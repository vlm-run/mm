"""Whisper transcription via faster-whisper (CTranslate2).

~4x faster than openai-whisper on CPU, GPU auto-detection.
Models cached lazily — first call loads, subsequent calls reuse.

Install: pip install vlmctx[extract]
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TranscriptionResult:
    """Result of a Whisper transcription."""

    text: str
    segments: list[dict[str, Any]] = field(default_factory=list)
    language: str = ""
    language_probability: float = 0.0
    elapsed_ms: float = 0.0
    model_size: str = ""
    device: str = ""


_MODEL_CACHE: dict[str, Any] = {}


def whisper_available() -> bool:
    """Check if faster-whisper is installed."""
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _get_device() -> tuple[str, str]:
    """Detect best device and compute type.

    Returns (device, compute_type):
      - CUDA GPU: ("cuda", "float16")
      - CPU: ("cpu", "int8")
    """
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda", "float16"
    except ImportError:
        pass
    # Also check via ctranslate2 directly
    try:
        import ctranslate2
        if "cuda" in ctranslate2.get_supported_compute_types("cuda"):
            return "cuda", "float16"
    except (ImportError, RuntimeError):
        pass
    return "cpu", "int8"


def _get_model(model_size: str) -> Any:
    """Load or retrieve cached WhisperModel."""
    if model_size in _MODEL_CACHE:
        return _MODEL_CACHE[model_size]

    from faster_whisper import WhisperModel

    device, compute_type = _get_device()
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    _MODEL_CACHE[model_size] = model
    return model


def transcribe(
    audio_path: str | Path,
    *,
    model_size: str = "tiny",
    language: str | None = None,
    beam_size: int = 5,
) -> TranscriptionResult:
    """Transcribe audio file using faster-whisper.

    Args:
        audio_path: Path to audio file (WAV, MP3, etc.)
        model_size: Whisper model size ("tiny", "base", "small", "medium", "large-v3")
        language: ISO language code (auto-detected if None)
        beam_size: Beam size for decoding (higher = more accurate, slower)

    Returns:
        TranscriptionResult with text, segments, language, and timing.
    """
    if not whisper_available():
        return TranscriptionResult(
            text="[whisper not installed — pip install vlmctx[extract]]",
            model_size=model_size,
        )

    t0 = time.monotonic()
    device, _ = _get_device()

    model = _get_model(model_size)
    segments_iter, info = model.transcribe(
        str(audio_path),
        beam_size=beam_size,
        language=language,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )

    segments: list[dict[str, Any]] = []
    text_parts: list[str] = []
    for seg in segments_iter:
        segments.append({
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
        })
        text_parts.append(seg.text.strip())

    elapsed = (time.monotonic() - t0) * 1000

    return TranscriptionResult(
        text=" ".join(text_parts),
        segments=segments,
        language=info.language,
        language_probability=round(info.language_probability, 3),
        elapsed_ms=round(elapsed, 1),
        model_size=model_size,
        device=device,
    )
