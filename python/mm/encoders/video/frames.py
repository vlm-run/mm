"""Frame sampling video encoders.

Provides ``VideoFrames`` (uniform frame extraction) and
``VideoFramesWithTranscript`` (frames + Whisper audio transcript).
Refactored from the original ``VideoFrameSample`` and
``VideoFrameSampleWithTranscript`` with the new ``video-*`` naming.

Uses PyAV for in-process frame decoding — no subprocess or temp files.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from mm.encoders import Message, _resolve_provider, register
from mm.encoders.image import _image_part, _to_message
from mm.encoders.video import _uniform_timestamps
from mm.encoders.video._transcript import encode_with_transcript

logger = logging.getLogger(__name__)


class VideoFrames:
    """Extract frames at *fps* and batch them into Messages.

    Each yielded Message contains up to ``max_frames_per_message`` base64
    JPEG frames plus a text header indicating the time range.

    Kwargs:
        fps: Frames per second to sample (default 1.0).
        max_width: Frame resize width in pixels (default 1024).
        max_frames_per_message: Frames per Message (default 16).
    """

    name: str = "video-frames"
    media_types: tuple[str, ...] = ("video",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        fps: float = kwargs.get("fps", 1.0)
        max_width: int = kwargs.get("max_width", 1024)
        max_frames_per_message: int = kwargs.get("max_frames_per_message", 16)
        provider: str = _resolve_provider()

        from mm.video import VideoReader, _pyav_available

        if not _pyav_available():
            yield _to_message([{"type": "text", "text": f"[PyAV not available for {path.name}]"}])
            return

        with VideoReader(path) as reader:
            duration = reader.duration
            if duration <= 0:
                yield _to_message(
                    [{"type": "text", "text": f"[Cannot determine duration for {path.name}]"}]
                )
                return

            timestamps: list[float] = _uniform_timestamps(duration, fps)

            max_total: int = max_frames_per_message * 8
            if len(timestamps) > max_total:
                step: int = len(timestamps) // max_total
                timestamps = timestamps[::step]

            logger.debug(
                "video_frames [path=%s, duration=%.1fs, fps=%.1f, frames=%d]",
                path.name,
                duration,
                fps,
                len(timestamps),
            )

            for batch in reader.frames(timestamps, width=max_width).batched(max_frames_per_message):
                parts: list[dict[str, Any]] = []
                t_start = batch[0].timestamp
                t_end = batch[-1].timestamp
                parts.append(
                    {
                        "type": "text",
                        "text": f"Video frames from {path.name} ({t_start:.1f}s - {t_end:.1f}s):",
                    }
                )
                for frame in batch:
                    b64, mime = frame.encode_jpeg()
                    parts.append(_image_part(b64, mime, provider))
                yield _to_message(parts)


class VideoFramesWithTranscript:
    """Extract frames at *fps* **and** transcribe audio via Whisper.

    Yields a transcript Message first, then batches of frames identical
    to ``VideoFrames``.  Falls back to frame-only output when Whisper
    is unavailable.

    Kwargs:
        fps, max_width, max_frames_per_message: Same as ``VideoFrames``.
        model: Transcription model name (default chosen by backend).
        language: Language code or "auto" (default "auto").
        audio_speed: Playback speed multiplier (default 1.0).
    """

    name: str = "video-frames-w-transcript"
    media_types: tuple[str, ...] = ("video",)

    _visual = VideoFrames()

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        yield from encode_with_transcript(path, self._visual.encode, **kwargs)


register(VideoFrames())
register(VideoFramesWithTranscript())
