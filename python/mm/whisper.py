"""Whisper transcription with automatic backend selection.

Backends (checked in order, first available wins):
  1. lightning-whisper-mlx  — MLX on Apple Metal GPU (~3-4x faster on Apple Silicon)
  2. faster-whisper         — CTranslate2 on CPU/CUDA

Models cached lazily — first call loads, subsequent calls reuse.

Install: pip install mm[extract] or pip install mm[extract,mlx] for MLX support on Apple Silicon.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TranscriptionSegment:
    """Single segment of a transcription result."""

    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    """Result of a Whisper transcription."""

    text: str
    segments: list[TranscriptionSegment] = field(default_factory=list)
    language: str = ""
    language_probability: float = 0.0
    elapsed_ms: float = 0.0
    model_size: str = ""
    device: str = ""
    backend: str = ""


_MODEL_CACHE: dict[str, Any] = {}
_BACKEND: str | None = None


def whisper_available() -> bool:
    """Check if any whisper backend is installed."""
    return _detect_backend() is not None


def _detect_backend() -> str | None:
    """Detect best available whisper backend."""
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND

    # Prefer MLX on macOS (Apple Silicon Metal GPU)
    try:
        import lightning_whisper_mlx  # noqa: F401
        import mlx.core as mx

        if mx.metal.is_available():
            _BACKEND = "mlx"
            return _BACKEND
    except (ImportError, AttributeError):
        pass

    # Fall back to faster-whisper (CTranslate2)
    try:
        import faster_whisper  # noqa: F401

        _BACKEND = "ctranslate2"
        return _BACKEND
    except ImportError:
        pass

    _BACKEND = ""
    return None


# ── CTranslate2 backend (faster-whisper) ────────────────────────────


def _get_device() -> tuple[str, str]:
    """Detect best device for CTranslate2.

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
    try:
        import ctranslate2

        if "cuda" in ctranslate2.get_supported_compute_types("cuda"):
            return "cuda", "float16"
    except (ImportError, RuntimeError, ValueError):
        pass
    return "cpu", "int8"


def _get_ct2_model(model_size: str) -> Any:
    """Load or retrieve cached CTranslate2 WhisperModel."""
    key = f"ct2:{model_size}"
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]

    from faster_whisper import WhisperModel

    device, compute_type = _get_device()
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    _MODEL_CACHE[key] = model
    return model


def _transcribe_ct2(
    audio_path: str,
    model_size: str,
    beam_size: int,
    language: str | None,
    audio_speed: float,
) -> TranscriptionResult:
    """Transcribe using faster-whisper (CTranslate2)."""
    t0 = time.monotonic()
    device, _ = _get_device()

    model = _get_ct2_model(model_size)
    segments_iter, info = model.transcribe(
        audio_path,
        beam_size=beam_size,
        language=language,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )

    ts_scale = audio_speed if audio_speed > 0 else 1.0
    segments: list[TranscriptionSegment] = []
    text_parts: list[str] = []
    for seg in segments_iter:
        segments.append(
            TranscriptionSegment(
                start=round(seg.start * ts_scale, 3),
                end=round(seg.end * ts_scale, 3),
                text=seg.text.strip(),
            )
        )
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
        backend="ctranslate2",
    )


# ── MLX backend (lightning-whisper-mlx) ─────────────────────────────


def _get_mlx_model(model_size: str, batch_size: int) -> Any:
    """Load or retrieve cached MLX WhisperModel."""
    key = f"mlx:{model_size}:{batch_size}"
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]

    from lightning_whisper_mlx import LightningWhisperMLX

    model = LightningWhisperMLX(model=model_size, batch_size=batch_size, quant=None)
    _MODEL_CACHE[key] = model
    return model


def _transcribe_mlx(
    audio_path: str,
    model_size: str,
    audio_speed: float,
    batch_size: int = 12,
) -> TranscriptionResult:
    """Transcribe using lightning-whisper-mlx (Apple Metal GPU)."""
    t0 = time.monotonic()

    model = _get_mlx_model(model_size, batch_size)
    result = model.transcribe(audio_path=audio_path)

    text = result.get("text", "")
    ts_scale = audio_speed if audio_speed > 0 else 1.0

    # lightning-whisper-mlx segments: [start_ms, end_ms, text] lists
    raw_segments = result.get("segments", [])
    segments: list[TranscriptionSegment] = []
    for seg in raw_segments:
        if isinstance(seg, (list, tuple)) and len(seg) >= 3:
            start_s = seg[0] / 1000.0
            end_s = seg[1] / 1000.0
            seg_text = str(seg[2]).strip()
        elif isinstance(seg, dict):
            start_s = seg.get("start", 0)
            end_s = seg.get("end", 0)
            seg_text = seg.get("text", "").strip()
        else:
            continue
        segments.append(
            TranscriptionSegment(
                start=round(start_s * ts_scale, 3),
                end=round(end_s * ts_scale, 3),
                text=seg_text,
            )
        )

    elapsed = (time.monotonic() - t0) * 1000
    return TranscriptionResult(
        text=text.strip(),
        segments=segments,
        language=result.get("language", ""),
        language_probability=0.0,
        elapsed_ms=round(elapsed, 1),
        model_size=model_size,
        device="metal",
        backend="mlx",
    )


# ── Public API ──────────────────────────────────────────────────────


def transcribe(
    audio_path: str | Path,
    *,
    model_size: str = "tiny",
    language: str | None = None,
    beam_size: int = 1,
    audio_speed: float = 1.0,
) -> TranscriptionResult:
    """Transcribe audio file using the best available backend.

    Backend selection (automatic):
      - macOS with Apple Silicon: lightning-whisper-mlx (Metal GPU)
      - Linux/CUDA: faster-whisper (CTranslate2, GPU)
      - CPU fallback: faster-whisper (CTranslate2, int8)

    Args:
        audio_path: Path to audio file (WAV, MP3, etc.)
        model_size: Whisper model size ("tiny", "base", "small", "medium", "large-v3")
        language: ISO language code (auto-detected if None)
        beam_size: Beam size for CTranslate2 (1=greedy, 5=beam search). Ignored by MLX.
        audio_speed: Speed multiplier the audio was extracted at. Timestamps
            are scaled back to original time.

    Returns:
        TranscriptionResult with text, segments, language, timing, and backend info.
    """
    backend = _detect_backend()

    if backend is None:
        return TranscriptionResult(
            text="[whisper not installed — pip install mm[extract] or pip install mm[extract,mlx] for MLX support on Apple Silicon]",
            model_size=model_size,
        )

    audio_str = str(audio_path)

    if backend == "mlx":
        return _transcribe_mlx(audio_str, model_size, audio_speed)

    return _transcribe_ct2(audio_str, model_size, beam_size, language, audio_speed)
