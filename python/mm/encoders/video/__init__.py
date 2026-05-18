"""Video encoding strategies: chunked encoding and submodule registration.

Provides ``VideoChunk`` and imports all video encoder submodules so their
classes self-register.  Uses PyAV for in-process decoding.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from mm.encoders import Message, _resolve_provider, register
from mm.encoders.image import _image_part, _to_message

logger = logging.getLogger(__name__)


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

        from mm.video import VideoReader, pyav_runnable

        if not pyav_runnable():
            yield _to_message([{"type": "text", "text": f"[PyAV not runnable for {path.name}]"}])
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
