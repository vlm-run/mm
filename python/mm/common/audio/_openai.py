"""OpenAI-compatible transcription backend.

Calls ``/v1/audio/transcriptions`` on any OpenAI-compatible server
(OpenAI, Ollama, vLLM, etc.).  The ``base_url`` and ``api_key`` can
be passed explicitly; when omitted, ``base_url`` defaults to the
``mm.profile.TRANSCRIPTION_BASE_URL`` and ``api_key`` defaults to an empty string.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from mm.common.audio._base import (
    TranscriptionBackend,
    TranscriptionResult,
    TranscriptionSegment,
)

logger = logging.getLogger(__name__)


class OpenAIBackend(TranscriptionBackend):
    """Transcription via any OpenAI-compatible ``/v1/audio/transcriptions`` endpoint.

    Works with OpenAI (``whisper-1``, ``gpt-4o-transcribe``), Ollama,
    vLLM, or any server that implements the endpoint.

    The ``base_url`` and ``api_key`` can be set explicitly in the
    constructor or via ``encoder_kwargs``; when omitted ``base_url``
    falls back to ``mm.profile.TRANSCRIPTION_BASE_URL``.
    """

    name = "openai"
    priority = 30

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key

    def available(self) -> bool:
        return True

    def transcribe(
        self,
        audio_path: Path,
        *,
        model: str = "whisper-1",
        language: str | None = None,
        beam_size: int = 1,
        audio_speed: float = 1.0,
    ) -> TranscriptionResult:
        from openai import OpenAI

        from mm.profile import TRANSCRIPTION_BASE_URL, gateway_api_key

        base_url = self._base_url or TRANSCRIPTION_BASE_URL
        api_key = self._api_key or gateway_api_key()
        client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=120.0,
        )

        t0 = time.monotonic()
        with open(audio_path, "rb") as f:
            resp = client.audio.transcriptions.create(
                model="nvidia/parakeet-tdt-0.6b-v3",
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
        elapsed = (time.monotonic() - t0) * 1000

        text = getattr(resp, "text", "") or ""
        lang = getattr(resp, "language", "") or ""
        raw_segments = getattr(resp, "segments", None) or []

        ts_scale = audio_speed if audio_speed > 0 else 1.0
        segments: list[TranscriptionSegment] = []
        for seg in raw_segments:
            start = getattr(seg, "start", 0) or 0
            end = getattr(seg, "end", 0) or 0
            seg_text = (getattr(seg, "text", "") or "").strip()
            segments.append(
                TranscriptionSegment(
                    start=round(float(start) * ts_scale, 3),
                    end=round(float(end) * ts_scale, 3),
                    text=seg_text,
                )
            )

        logger.debug(
            "openai_transcribe [path=%s, model=%s, base_url=%s, %.0fms]",
            audio_path.name,
            model,
            base_url,
            elapsed,
        )

        return TranscriptionResult(
            text=text.strip(),
            segments=segments,
            language=lang,
            language_probability=0.0,
            elapsed_ms=round(elapsed, 1),
            model_size=model,
            device="remote",
            backend="openai",
        )
