"""Audio transcription with pluggable backends.

The ``openai`` backend is always the default and calls the VLM Run
gateway (``https://gateway.vlm.run/v1/openai``) with
``nvidia/parakeet-tdt-0.6b-v3``.  Users can point it at any
OpenAI-compatible endpoint via ``--profile`` or ``--encode.strategy_opts``.

Local backends are **opt-in only** — they are never auto-selected:

* ``mlx`` — Apple Metal GPU.  ``pip install mm-ctx[mlx]``,
  then ``--encode.backend mlx``.
* ``ctranslate2`` — CPU int8 / CUDA float16.  ``pip install mm-ctx[gpu]``,
  then ``--encode.backend ctranslate2``.

Custom backends can be registered by subclassing
:class:`TranscriptionBackend` and calling :func:`register_backend`.
See :mod:`mm.common.audio._base` for a full Gemini example.
"""

from __future__ import annotations

from pathlib import Path

from mm.common.audio._base import (
    TranscriptionBackend,
    TranscriptionResult,
    TranscriptionSegment,
    detect_backend,
    list_backends,
    register_backend,
    transcribe_available,
    unregister_backend,
)


def _register_backends() -> None:
    """Register all available backends.

    The OpenAI backend is always registered.  Local backends (mlx,
    ctranslate2) are added when their respective extras are installed
    but are **never** auto-selected — the user must request them
    explicitly via ``--encode.backend``.
    """
    import logging

    from mm.common.audio._openai import OpenAIBackend

    logger = logging.getLogger(__name__)

    register_backend(OpenAIBackend())

    try:
        import lightning_whisper_mlx  # noqa: F401
        import mlx.core as mx

        if mx.metal.is_available():
            from mm.common.audio._mlx import MLXBackend

            register_backend(MLXBackend())
    except (ImportError, AttributeError):
        logger.debug("mlx backend not available (install mm-ctx[mlx])")

    try:
        import faster_whisper  # noqa: F401

        from mm.common.audio._ctranslate2 import CTranslate2Backend

        register_backend(CTranslate2Backend())
    except ImportError:
        logger.debug("ctranslate2 backend not available (install mm-ctx[gpu])")


_register_backends()

ACTIVE_VARIANT = "openai"

GATEWAY_MODEL = "nvidia/parakeet-tdt-0.6b-v3"


def transcribe(
    audio_path: str | Path,
    *,
    model: str | None = None,
    language: str | None = None,
    beam_size: int = 1,
    audio_speed: float = 1.0,
    backend: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> TranscriptionResult:
    """Transcribe audio using the registered backend.

    By default, calls the VLM Run gateway's OpenAI-compatible
    transcription endpoint.  The model is chosen automatically based
    on the resolved ``base_url`` (``whisper-1`` for ``api.openai.com``,
    ``nvidia/parakeet-tdt-0.6b-v3`` for the gateway).

    Args:
        audio_path: Path to audio file (WAV, MP3, etc.).
        model: Model name.  ``None`` picks a sensible default for
            the active backend (see above for openai, ``tiny`` for
            local backends).
        language: ISO language code; ``None`` for auto-detection.
        beam_size: Beam size for local backends (1 = greedy).
        audio_speed: Speed multiplier the audio was extracted at.
            Timestamps are scaled back to original time.
        backend: Explicit backend name (``"openai"``, ``"mlx"``,
            ``"ctranslate2"``). When ``None`` the ``[transcription]``
            section of ``mm.toml`` is consulted; if still unset, the
            ``openai`` backend is used.
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

    if model is None and be.name != "openai":
        model = "tiny"

    return be.transcribe(
        Path(audio_path) if not isinstance(audio_path, Path) else audio_path,
        model=model,
        language=language,
        beam_size=beam_size,
        audio_speed=audio_speed,
    )


# @memoize_file(maxsize=16, path=lambda: cache_dir() / "transcripts")
def transcribe_file(
    path: str | Path,
    *,
    model: str | None = None,
    language: str | None = None,
    audio_speed: float = 1.0,
    beam_size: int = 5,
    backend: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> TranscriptionResult:
    """Transcribe a media file (audio or video) with disk-backed caching.

    Args:
        path: Path to the original media file (audio or video).
        model: Model name; ``None`` picks the backend default.
        language: ISO language code; ``None`` for auto-detection.
        audio_speed: Speed multiplier applied during extraction.
        beam_size: Beam size for local backends.
        backend: Explicit backend name (``"openai"``, ``"mlx"``, etc.).
        base_url: Custom base URL for the openai backend.
        api_key: API key for the openai backend.

    Returns:
        :class:`TranscriptionResult`.
    """
    from mm.ffmpeg import audio_transformer

    audio_result = None
    try:
        audio_result = audio_transformer(
            Path(path) if not isinstance(path, Path) else path,
            speed=audio_speed,
        )
        return transcribe(
            audio_result.path,
            model=model,
            language=language,
            audio_speed=audio_speed,
            beam_size=beam_size,
            backend=backend,
            base_url=base_url,
            api_key=api_key,
        )
    except Exception:
        return TranscriptionResult("", segments=[])
    finally:
        if audio_result is not None:
            try:
                audio_result.path.unlink(missing_ok=True)
            except Exception:
                pass


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
    "transcribe_file",
    "unregister_backend",
]
