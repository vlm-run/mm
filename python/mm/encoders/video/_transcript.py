"""Shared transcript helper for ``-w-transcript`` encoder variants.

Provides ``transcript_messages`` which extracts and transcribes audio
via Whisper and yields a timestamped transcript Message.  All
``-w-transcript`` video encoders delegate to this helper so that
Whisper integration is not duplicated across files.

Transcripts are cached per-process keyed on
``(path, mtime, size, model, language, audio_speed)`` so that pipelines
running multiple ``-w-transcript`` encoders against the same file pay
the Whisper cost only once.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from mm.encoders import Message
from mm.encoders.image import _to_message

logger = logging.getLogger(__name__)


_TRANSCRIPT_CACHE: dict[tuple[str, float, int, str, str, float], list[Message]] = {}
_TRANSCRIPT_CACHE_MAX = 16


def clear_transcript_cache() -> None:
    """Drop all cached transcripts (process-local)."""
    _TRANSCRIPT_CACHE.clear()


def _build_transcript_messages(
    path: Path,
    whisper_model: str,
    language: str,
    audio_speed: float,
) -> list[Message]:
    """Run Whisper on *path* and return the rendered Message list.

    Returns an empty list when Whisper is unavailable or no speech is
    detected, so callers can decide whether to fall back to a placeholder.
    """
    try:
        from mm.video import extract_audio
        from mm.whisper import transcribe, whisper_available
    except ImportError:
        return []

    if not whisper_available():
        return []

    audio_result = extract_audio(path, speed=audio_speed)

    lang_kwarg: dict[str, str] = {}
    if language != "auto":
        lang_kwarg["language"] = language

    whisper_result = transcribe(
        audio_result.path,
        model_size=whisper_model,
        beam_size=5,
        audio_speed=audio_speed,
        **lang_kwarg,
    )

    try:
        audio_result.path.unlink(missing_ok=True)
    except Exception:
        pass

    transcript = whisper_result.text
    if not transcript or transcript.startswith("["):
        return []

    if whisper_result.segments:
        segment_lines = [
            f"[{seg.start:.1f}s - {seg.end:.1f}s] {seg.text.strip()}"
            for seg in whisper_result.segments
        ]
        text = (
            f"Audio transcript of {path.name}"
            f" (lang={whisper_result.language},"
            f" model={whisper_model},"
            f" {whisper_result.elapsed_ms:.0f}ms):\n\n" + "\n".join(segment_lines)
        )
    else:
        text = f"Audio transcript of {path.name}:\n\n{transcript}"

    return [_to_message([{"type": "text", "text": text}])]


def _transcript_messages_cached(
    path: Path,
    whisper_model: str,
    language: str,
    audio_speed: float,
) -> list[Message]:
    """Cached wrapper around ``_build_transcript_messages`` keyed by file fingerprint."""
    try:
        st = path.stat()
        key = (str(path.resolve()), st.st_mtime, st.st_size, whisper_model, language, audio_speed)
    except OSError:
        return _build_transcript_messages(path, whisper_model, language, audio_speed)

    cached = _TRANSCRIPT_CACHE.get(key)
    if cached is not None:
        return cached

    messages = _build_transcript_messages(path, whisper_model, language, audio_speed)
    if len(_TRANSCRIPT_CACHE) >= _TRANSCRIPT_CACHE_MAX:
        _TRANSCRIPT_CACHE.pop(next(iter(_TRANSCRIPT_CACHE)))
    _TRANSCRIPT_CACHE[key] = messages
    return messages


def transcript_messages(
    path: Path,
    *,
    whisper_model: str = "medium",
    language: str = "auto",
    audio_speed: float = 1.0,
) -> Iterable[Message]:
    """Extract audio and yield a Whisper transcript Message.

    Cached per-process — subsequent calls with the same file + model are
    instant.  Silently yields nothing when Whisper or ffmpeg is unavailable
    so that visual-only output is still produced.
    """
    yield from _transcript_messages_cached(path, whisper_model, language, audio_speed)


def encode_with_transcript(
    path: Path,
    visual_encode_fn: Any,
    **kwargs: Any,
) -> Iterable[Message]:
    """Wrap a visual encoder to prepend a Whisper transcript.

    The Whisper run and the visual encoder execute concurrently — Whisper
    runs on the GPU (MLX/Metal) while PyAV decode + Pillow run on the CPU,
    so they share no hardware resources.  Total wall time is
    ``max(whisper, visual)`` instead of ``whisper + visual``.

    Message ordering is preserved (transcript first, then visual frames)
    because most VLM prompts expect textual context ahead of images.

    Args:
        path: Video file path.
        visual_encode_fn: Callable ``(path, **kwargs) -> Iterable[Message]``.
        **kwargs: Passed to both the transcript helper and the visual encoder.
            Transcript-specific kwargs: ``whisper_model``, ``language``,
            ``audio_speed``.
    """
    from concurrent.futures import ThreadPoolExecutor

    whisper_model: str = kwargs.get("whisper_model", "medium")
    language: str = kwargs.get("language", "auto")
    audio_speed: float = kwargs.get("audio_speed", 1.0)

    with ThreadPoolExecutor(max_workers=1) as pool:
        transcript_fut = pool.submit(
            _transcript_messages_cached,
            path,
            whisper_model,
            language,
            audio_speed,
        )

        # Run the visual encoder while Whisper runs in the background.
        # Materialise the visual output so transcript can be emitted first
        # without blocking on the slower of the two.
        visual_msgs = list(visual_encode_fn(path, **kwargs))

        yield from transcript_fut.result()
        yield from visual_msgs
