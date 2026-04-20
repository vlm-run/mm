"""Shared transcript helper for ``-w-transcript`` encoder variants.

Provides ``transcript_messages`` which extracts and transcribes audio
via Whisper and yields a timestamped transcript Message.  All
``-w-transcript`` video encoders delegate to this helper so that
Whisper integration is not duplicated across files.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from mm.encoders import Message
from mm.encoders.image import _to_message

logger = logging.getLogger(__name__)


def transcript_messages(
    path: Path,
    *,
    whisper_model: str = "medium",
    language: str = "auto",
    audio_speed: float = 1.0,
) -> Iterable[Message]:
    """Extract audio and yield a Whisper transcript Message.

    Silently yields nothing when Whisper or ffmpeg is unavailable so
    that visual-only output is still produced.
    """
    try:
        from mm.ffmpeg import extract_audio
        from mm.whisper import transcribe, whisper_available
    except ImportError:
        return

    if not whisper_available():
        return

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
        return

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

    yield _to_message([{"type": "text", "text": text}])


def encode_with_transcript(
    path: Path,
    visual_encode_fn: Any,
    **kwargs: Any,
) -> Iterable[Message]:
    """Wrap a visual encoder to prepend a Whisper transcript.

    Args:
        path: Video file path.
        visual_encode_fn: Callable ``(path, **kwargs) -> Iterable[Message]``.
        **kwargs: Passed to both the transcript helper and the visual encoder.
            Transcript-specific kwargs: ``whisper_model``, ``language``,
            ``audio_speed``.
    """
    whisper_model: str = kwargs.get("whisper_model", "medium")
    language: str = kwargs.get("language", "auto")
    audio_speed: float = kwargs.get("audio_speed", 1.0)

    yield from transcript_messages(
        path,
        whisper_model=whisper_model,
        language=language,
        audio_speed=audio_speed,
    )
    yield from visual_encode_fn(path, **kwargs)
