"""Video encoding strategies: frame sampling and chunked encoding.

Provides ``VideoFrameSample`` and ``VideoChunk`` strategies that extract
visual content from video files and encode it as OpenAI-compatible
Message dicts.  Both require ``ffmpeg`` on the system PATH.
"""

from __future__ import annotations

import base64
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

        from mm.ffmpeg import (
            extract_frames_at_timestamps,
            ffmpeg_available,
            probe_duration,
        )

        if not ffmpeg_available():
            yield _to_message([{"type": "text", "text": f"[ffmpeg not available for {path.name}]"}])
            return

        duration: float = probe_duration(path)
        if duration <= 0:
            yield _to_message([{"type": "text", "text": f"[Cannot determine duration for {path.name}]"}])
            return

        timestamps: list[float] = _uniform_timestamps(duration, fps)

        max_total: int = max_frames_per_message * 8
        if len(timestamps) > max_total:
            step: int = len(timestamps) // max_total
            timestamps = timestamps[::step]

        logger.debug(
            "frame_sample [path=%s, duration=%.1fs, fps=%.1f, frames=%d]",
            path.name, duration, fps, len(timestamps),
        )

        frame_paths: list[Path] = extract_frames_at_timestamps(
            path, timestamps, thumb_width=max_width,
        )

        if not frame_paths:
            yield _to_message([{"type": "text", "text": f"[No frames extracted from {path.name}]"}])
            return

        try:
            for i in range(0, len(frame_paths), max_frames_per_message):
                batch: list[Path] = frame_paths[i : i + max_frames_per_message]
                parts: list[dict[str, Any]] = []

                t_start: float = timestamps[i] if i < len(timestamps) else 0.0
                t_end_idx: int = min(i + max_frames_per_message, len(timestamps)) - 1
                t_end: float = timestamps[t_end_idx] if timestamps else 0.0
                parts.append({
                    "type": "text",
                    "text": f"Video frames from {path.name} ({t_start:.1f}s - {t_end:.1f}s):",
                })

                for frame_path in batch:
                    b64: str = base64.b64encode(frame_path.read_bytes()).decode()
                    parts.append(_image_part(b64, "image/jpeg", provider))

                yield _to_message(parts)
        finally:
            for fp in frame_paths:
                try:
                    fp.unlink(missing_ok=True)
                except OSError:
                    pass


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

    name: str = "video-chunk"
    media_types: tuple[str, ...] = ("video",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        chunk_duration: int = kwargs.get("chunk_duration", 60)
        overlap: int = kwargs.get("overlap", 20)
        max_width: int = kwargs.get("max_width", 1024)
        frames_per_chunk: int = kwargs.get("frames_per_chunk", 16)
        provider: str = _resolve_provider()

        from mm.ffmpeg import (
            extract_frames_at_timestamps,
            ffmpeg_available,
            probe_duration,
        )

        if not ffmpeg_available():
            yield _to_message([{"type": "text", "text": f"[ffmpeg not available for {path.name}]"}])
            return

        duration: float = probe_duration(path)
        if duration <= 0:
            yield _to_message([{"type": "text", "text": f"[Cannot determine duration for {path.name}]"}])
            return

        step: int = max(chunk_duration - overlap, 1)
        start: float = 0.0
        chunk_idx: int = 0

        logger.debug(
            "video_chunk [path=%s, duration=%.1fs, chunk=%ds, overlap=%ds]",
            path.name, duration, chunk_duration, overlap,
        )

        while start < duration:
            end: float = min(start + chunk_duration, duration)

            chunk_timestamps: list[float] = _uniform_timestamps_range(
                start, end, frames_per_chunk,
            )

            frame_paths: list[Path] = extract_frames_at_timestamps(
                path, chunk_timestamps, thumb_width=max_width,
            )

            if frame_paths:
                parts: list[dict[str, Any]] = [{
                    "type": "text",
                    "text": f"Video chunk {chunk_idx} ({start:.0f}s - {end:.0f}s) of {path.name}:",
                }]
                for fp in frame_paths:
                    b64: str = base64.b64encode(fp.read_bytes()).decode()
                    parts.append(_image_part(b64, "image/jpeg", provider))
                    try:
                        fp.unlink(missing_ok=True)
                    except OSError:
                        pass
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


def _uniform_timestamps_range(
    start: float, end: float, count: int
) -> list[float]:
    """Generate *count* uniformly spaced timestamps between *start* and *end*."""
    if count <= 1:
        return [start]
    step: float = (end - start) / count
    return [start + i * step for i in range(count)]


register(VideoFrameSample())
register(VideoChunk())
