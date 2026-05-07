"""MLX transcription backend (lightning-whisper-mlx on Apple Metal)."""

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


def _get_model(model_size: str, batch_size: int) -> Any:
    key = f"mlx:{model_size}:{batch_size}"
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]

    from mm.deps import try_import_or_raise

    lwm = try_import_or_raise("lightning_whisper_mlx", extra="mlx", package="lightning-whisper-mlx")
    model = lwm.LightningWhisperMLX(model=model_size, batch_size=batch_size, quant=None)
    _MODEL_CACHE[key] = model
    return model


class MLXBackend(TranscriptionBackend):
    """Transcription via lightning-whisper-mlx on Apple Metal GPU.

    ~3-4x faster than CTranslate2 on Apple Silicon.  Requires the
    ``mm[mlx]`` extra: ``pip install mm[mlx]``.
    """

    name = "mlx"
    priority = 10

    def available(self) -> bool:
        try:
            import lightning_whisper_mlx  # noqa: F401
            import mlx.core as mx

            return mx.metal.is_available()
        except (ImportError, AttributeError):
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
        batch_size = 12

        mdl = _get_model(model, batch_size)
        result = mdl.transcribe(audio_path=str(audio_path))

        text = result.get("text", "")
        ts_scale = audio_speed if audio_speed > 0 else 1.0

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
            model_size=model,
            device="metal",
            backend="mlx",
        )
