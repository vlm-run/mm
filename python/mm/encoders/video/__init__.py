"""Video encoding strategies: frame sampling and chunked encoding.

Provides ``VideoFrameSample`` and ``VideoChunk`` strategies that extract
visual content from video files and encode it as OpenAI-compatible
Message dicts.  Uses PyAV for in-process decoding.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from mm.encoders import Message, _resolve_provider, register
from mm.encoders.image import _image_part, _to_message

logger = logging.getLogger(__name__)


class VideoFrameSample:
    """Extract frames at *fps* and batch them into Messages.

    Each yielded Message contains up to ``max_frames_per_message`` base64
    JPEG frames plus a text header indicating the time range.

    Kwargs:
        fps: Frames per second to sample (default 1.0).
        max_width: Frame resize width in pixels (default 1024).
        max_frames_per_message: Frames per Message (default 16).
    """

    name: str = "frame-sample"
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
                "frame_sample [path=%s, duration=%.1fs, fps=%.1f, frames=%d]",
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


class VideoChunk:
    """Split video into overlapping time-based chunks.

    Each yielded Message contains extracted frames for one chunk plus
    a text header with the time range.

    Kwargs:
        chunk_duration: Seconds per chunk (default 60).
        overlap: Overlap between chunks in seconds (default 20).
        max_width: Frame resize width in pixels (default 1024).
        frames_per_chunk: Number of frames to extract per chunk (default 16).
    """

    name: str = "video-chunks"
    media_types: tuple[str, ...] = ("video",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        chunk_duration: int = kwargs.get("chunk_duration", 60)
        overlap: int = kwargs.get("overlap", 20)
        max_width: int = kwargs.get("max_width", 1024)
        frames_per_chunk: int = kwargs.get("frames_per_chunk", 16)
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

            step: int = max(chunk_duration - overlap, 1)
            start: float = 0.0
            chunk_idx: int = 0

            logger.debug(
                "video_chunk [path=%s, duration=%.1fs, chunk=%ds, overlap=%ds]",
                path.name,
                duration,
                chunk_duration,
                overlap,
            )

            while start < duration:
                end: float = min(start + chunk_duration, duration)
                chunk_timestamps: list[float] = _uniform_timestamps_range(
                    start,
                    end,
                    frames_per_chunk,
                )
                frames = reader.frames(chunk_timestamps, width=max_width).collect()

                if frames:
                    parts: list[dict[str, Any]] = [
                        {
                            "type": "text",
                            "text": f"Video chunk {chunk_idx} ({start:.0f}s - {end:.0f}s) of {path.name}:",
                        }
                    ]
                    for frame in frames:
                        b64, mime = frame.encode_jpeg()
                        parts.append(_image_part(b64, mime, provider))
                    yield _to_message(parts)

                start += step
                chunk_idx += 1


def _uniform_timestamps(duration: float, fps: float) -> list[float]:
    """Generate uniformly spaced timestamps at *fps* from 0 to *duration*."""
    interval: float = 1.0 / fps
    timestamps: list[float] = []
    t: float = 0.0
    while t < duration:
        timestamps.append(t)
        t += interval
    return timestamps


def _uniform_timestamps_range(start: float, end: float, count: int) -> list[float]:
    """Generate *count* uniformly spaced timestamps between *start* and *end*."""
    if count <= 1:
        return [start]
    step: float = (end - start) / count
    return [start + i * step for i in range(count)]


register(VideoFrameSample())
register(VideoChunk())

from mm.encoders.video import (  # noqa: E402, F401
    captions,
    frames,
    keyframes,
    mosaic,
    native,
    shots,
    summary,
    transcript,
)

_ALIASES: dict[str, str] = {
    "frame-sample": "video-frames",
    "video-frames-transcript": "video-frames-w-transcript",
    "video-chunk": "video-chunks",
    "mosaic": "video-mosaic",
    "shot-frames": "video-shots",
    "shot-mosaic": "video-shot-mosaic",
}


def _register_aliases() -> None:
    """Register old encoder names as aliases pointing to their replacements.

    Always overwrites the old name so new implementations take precedence
    even when the old encoder was already registered under that name.
    """
    from mm.encoders import _REGISTRY

    for old_name, new_name in _ALIASES.items():
        if new_name in _REGISTRY:
            _REGISTRY[old_name] = _REGISTRY[new_name]


_register_aliases()
