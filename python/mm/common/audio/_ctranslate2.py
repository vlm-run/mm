"""CTranslate2 transcription backend (faster-whisper)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from mm.common.audio._base import (
    TranscriptionBackend,
    TranscriptionResult,
    TranscriptionSegment,
)

_MODEL_CACHE: dict[str, Any] = {}


def _get_device() -> tuple[str, str]:
    """Detect best device: CUDA float16 if available, else CPU int8."""
    try:
        import ctranslate2

        if "cuda" in ctranslate2.get_supported_compute_types("cuda"):
            return "cuda", "float16"
    except (ImportError, RuntimeError, ValueError):
        pass
    return "cpu", "int8"


def _get_model(model_size: str) -> Any:
    key = f"ct2:{model_size}"
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]

    from faster_whisper import WhisperModel

    device, compute_type = _get_device()
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    _MODEL_CACHE[key] = model
    return model


class CTranslate2Backend(TranscriptionBackend):
    """Transcription via faster-whisper (CTranslate2).

    Supports CUDA (float16) and CPU (int8).  VAD filtering is enabled
    by default to skip silence.
    """

    name = "ctranslate2"
    priority = 20

    def available(self) -> bool:
        from mm._bootstrap import preload_media_libs

        preload_media_libs()
        try:
            import faster_whisper  # noqa: F401

            return True
        except Exception:
            return False

    def transcribe(
        self,
        audio_path: Path,
        *,
        model: str = "tiny",
        language: str | None = None,
        beam_size: int = 1,
        audio_speed: float = 1.0,
    ) -> TranscriptionResult:
        t0 = time.monotonic()
        device, _ = _get_device()

        mdl = _get_model(model)
        segments_iter, info = mdl.transcribe(
            str(audio_path),
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
            model_size=model,
            device=device,
            backend="ctranslate2",
        )
