"""OpenAI-compatible transcription backend (default).

Calls any OpenAI-compatible ``/v1/audio/transcriptions`` endpoint.
Out of the box the backend points at the VLM Run gateway
(``https://gateway.vlm.run/v1/openai``).  Users can override
``base_url`` to point at localhost, the OpenAI API, or any other
compatible server.

Resolution order for ``base_url`` / ``api_key``:

1. Explicit constructor args (passed via ``detect_backend`` overrides).
2. ``[transcription]`` section in ``mm.toml``.
3. The active mm profile's ``base_url`` (gateway by default).

No environment variables are read — all overrides flow through CLI
flags, profiles, or ``mm.toml`` config.
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

GATEWAY_AUDIO_URL = "https://gateway.vlm.run/v1/openai"


def _resolve_transcription_config() -> tuple[str, str]:
    """Return ``(base_url, api_key)`` from ``[transcription]`` in mm.toml."""
    try:
        from mm.config import get_transcription_config

        cfg = get_transcription_config()
        return (cfg.base_url or "").rstrip("/"), cfg.api_key or ""
    except Exception:
        return "", ""


def _resolve_profile_url() -> tuple[str, str]:
    """Return ``(base_url, api_key)`` from the active mm profile."""
    try:
        from mm.profile import get_profile

        p = get_profile()
        return p.base_url.rstrip("/"), p.api_key or ""
    except Exception:
        return "", ""


class OpenAIBackend(TranscriptionBackend):
    """Transcription via any OpenAI-compatible ``/v1/audio/transcriptions`` endpoint.

    Works with the VLM Run gateway (default), OpenAI (``whisper-1``,
    ``gpt-4o-transcribe``), Ollama, vLLM, or any compatible server.

    ``base_url`` resolution:
        explicit arg → ``[transcription].base_url`` in mm.toml →
        active profile ``base_url`` → gateway default.
    """

    name = "openai"

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

    def clone_with_config(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> OpenAIBackend:
        return OpenAIBackend(
            base_url=base_url or self._base_url,
            api_key=api_key or self._api_key,
        )

    def _resolve_url_and_key(self) -> tuple[str, str]:
        """Walk the resolution chain and return ``(base_url, api_key)``."""
        if self._base_url:
            return self._base_url, self._api_key or ""

        url, key = _resolve_transcription_config()
        if url:
            return url, key

        url, key = _resolve_profile_url()
        if url:
            return url, key

        return GATEWAY_AUDIO_URL, self._api_key or ""

    @staticmethod
    def _default_model(base_url: str) -> str:
        """Pick a model based on the resolved base URL."""
        if "api.openai.com" in base_url:
            return "whisper-1"
        return "nvidia/parakeet-tdt-0.6b-v3"

    def transcribe(
        self,
        audio_path: Path,
        *,
        model: str | None = None,
        language: str | None = None,
        beam_size: int = 1,
        audio_speed: float = 1.0,
    ) -> TranscriptionResult:
        from openai import OpenAI

        base_url, api_key = self._resolve_url_and_key()

        if not api_key:
            raise ValueError(
                f"No api_key configured for transcription endpoint {base_url!r}. "
                "Set one via --encode.strategy_opts api_key=<key>, "
                "the [transcription] section in mm.toml, or the active profile "
                "(mm profile set <name> --api-key <key>)."
            )

        if model is None:
            model = self._default_model(base_url)

        client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=120.0,
        )

        t0 = time.monotonic()
        with open(audio_path, "rb") as f:
            resp = client.audio.transcriptions.create(
                model=model,
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
