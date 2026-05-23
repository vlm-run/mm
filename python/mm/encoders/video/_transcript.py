"""Shared transcript helper for ``-w-transcript`` encoder variants.

Provides ``transcript_messages`` which extracts and transcribes audio
via Whisper and yields a timestamped transcript Message.  All
``-w-transcript`` video encoders delegate to this helper so that
Whisper integration is not duplicated across files.

Transcripts are cached **on disk** via :func:`mm.cache.memoize_file`,
keyed on ``(path, mtime, size, model, language, audio_speed)``.  Whisper
is the slowest step in the accurate-mode video pipeline (~76 s for a
short clip), so persisting the result across CLI invocations turns the
second ``mm cat video.mp4 -m accurate`` into a near-instant operation.
Cache lives under ``$MM_CACHE_DIR / transcripts`` (see
:func:`mm.cache.cache_dir`) and survives mtime-aware invalidation:
re-encoding the source video automatically retranscribes.

Use ``transcript_messages.cache_clear()`` to wipe the on-disk cache.
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
    model: str | None = None,
    language: str = "auto",
    audio_speed: float = 2.0,
    backend: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> list[Message]:
    """Extract audio and return transcript Messages.

    Cached on disk via :func:`mm.cache.memoize_file` — the second call
    with the same file + model + language + audio_speed is instant,
    even across CLI invocations (entries live under
    ``$MM_CACHE_DIR/transcripts/``). mtime-aware: re-encoding the
    source video invalidates automatically.

    Returns an empty list when the transcription backend or ffmpeg is
    unavailable so callers can fall back to visual-only output.
    """
    from mm.common.audio import transcribe_file

    resolved_lang = None if language == "auto" else language
    whisper_result = transcribe_file(
        path,
        model=model,
        language=resolved_lang,
        beam_size=5,
        audio_speed=audio_speed,
        backend=backend,
        base_url=base_url,
        api_key=api_key,
    )

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
            f" model={whisper_result.model_size},"
            f" {whisper_result.elapsed_ms:.0f}ms):\n\n" + "\n".join(segment_lines)
        )
    else:
        text = f"Audio transcript of {path.name}:\n\n{transcript}"

    return [_to_message([{"type": "text", "text": text}])]


def encode_with_transcript(
    path: Path,
    visual_encode_fn: Any,
    **kwargs: Any,
) -> Iterable[Message]:
    """Wrap a visual encoder to prepend a Whisper transcript.

    The Whisper run and the visual encoder execute concurrently — Whisper
    uses the default backend + profile while PyAV decode + Pillow run on the CPU.
    Total wall time is ``max(whisper, visual)`` instead of ``whisper + visual``.

    Message ordering is preserved (transcript first, then visual frames)
    because most VLM prompts expect textual context ahead of images.

    Args:
        path: Video file path.
        visual_encode_fn: Callable ``(path, **kwargs) -> Iterable[Message]``.
        **kwargs: Passed to both the transcript helper and the visual encoder.
            Transcript-specific kwargs: ``model``, ``language``, ``audio_speed``.
    """
    from concurrent.futures import ThreadPoolExecutor

    transcript_kwargs = {
        "model": kwargs.get("audio_model") or kwargs.get("model"),
        "language": kwargs.get("language", "auto"),
        "audio_speed": kwargs.get("audio_speed", 2.0),
        "backend": kwargs.get("audio_backend") or kwargs.get("backend"),
        "base_url": kwargs.get("audio_base_url") or kwargs.get("base_url"),
        "api_key": kwargs.get("audio_api_key") or kwargs.get("api_key"),
    }

    with ThreadPoolExecutor(max_workers=1) as pool:
        transcript_fut = pool.submit(transcript_messages, path, **transcript_kwargs)

        # Run the visual encoder while Whisper runs in the background.
        # Materialise the visual output so transcript can be emitted first
        # without blocking on the slower of the two.
        visual_msgs = list(visual_encode_fn(path, **kwargs))

        yield from transcript_fut.result()
        yield from visual_msgs
