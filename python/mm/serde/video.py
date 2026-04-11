"""Video encoding strategies: frame sampling and chunked encoding."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any, Iterable

from mm.serde import Message, _resolve_provider, register
from mm.serde.image import _image_part, _to_message


class VideoFrameSample:
    """Extract frames at N fps, resize, encode as image messages.

    Each yielded Message contains a batch of frame images (and optionally
    a transcript text part). For long videos, frames are split across
    multiple Messages based on ``max_frames_per_message``.
    """

    name = "frame-sample"
    media_types = ("video",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        fps: float = kwargs.get("fps", 1.0)
        max_width: int = kwargs.get("max_width", 1024)
        max_frames_per_message: int = kwargs.get("max_frames_per_message", 16)
        provider = _resolve_provider()

        from mm.ffmpeg import (
            extract_frames_at_timestamps,
            ffmpeg_available,
            probe_duration,
        )

        if not ffmpeg_available():
            yield _to_message([{"type": "text", "text": f"[ffmpeg not available for {path.name}]"}])
            return

        duration = probe_duration(path)
        if duration <= 0:
            yield _to_message([{"type": "text", "text": f"[Cannot determine duration for {path.name}]"}])
            return

        # Generate timestamps at the requested fps
        interval = 1.0 / fps
        timestamps = []
        t = 0.0
        while t < duration:
            timestamps.append(t)
            t += interval

        # Cap at a reasonable number
        if len(timestamps) > max_frames_per_message * 8:
            step = len(timestamps) // (max_frames_per_message * 8)
            timestamps = timestamps[::step]

        frame_paths = extract_frames_at_timestamps(
            path,
            timestamps,
            thumb_width=max_width,
        )

        if not frame_paths:
            yield _to_message([{"type": "text", "text": f"[No frames extracted from {path.name}]"}])
            return

        try:
            for i in range(0, len(frame_paths), max_frames_per_message):
                batch = frame_paths[i : i + max_frames_per_message]
                parts: list[dict[str, Any]] = []

                t_start = timestamps[i] if i < len(timestamps) else 0
                t_end = timestamps[min(i + max_frames_per_message, len(timestamps)) - 1] if timestamps else 0
                parts.append({
                    "type": "text",
                    "text": f"Video frames from {path.name} ({t_start:.1f}s - {t_end:.1f}s):",
                })

                for frame_path in batch:
                    b64 = base64.b64encode(frame_path.read_bytes()).decode()
                    parts.append(_image_part(b64, "image/jpeg", provider))

                yield _to_message(parts)
        finally:
            for fp in frame_paths:
                try:
                    fp.unlink(missing_ok=True)
                except OSError:
                    pass


class VideoChunk:
    """Break video into time-based chunks with overlap, mosaic each chunk.

    Each yielded Message represents one chunk of the video.
    """

    name = "video-chunk"
    media_types = ("video",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        chunk_duration: int = kwargs.get("chunk_duration", 60)
        overlap: int = kwargs.get("overlap", 20)
        max_width: int = kwargs.get("max_width", 1024)
        tile_cols: int = kwargs.get("tile_cols", 4)
        tile_rows: int = kwargs.get("tile_rows", 4)
        provider = _resolve_provider()

        from mm.ffmpeg import (
            extract_uniform_mosaics,
            ffmpeg_available,
            probe_duration,
        )

        if not ffmpeg_available():
            yield _to_message([{"type": "text", "text": f"[ffmpeg not available for {path.name}]"}])
            return

        duration = probe_duration(path)
        if duration <= 0:
            yield _to_message([{"type": "text", "text": f"[Cannot determine duration for {path.name}]"}])
            return

        # Generate chunk boundaries
        step = chunk_duration - overlap
        if step <= 0:
            step = chunk_duration

        start = 0.0
        chunk_idx = 0
        while start < duration:
            end = min(start + chunk_duration, duration)

            # Extract mosaic for this chunk's time range
            result = extract_uniform_mosaics(
                path,
                tile_cols=tile_cols,
                tile_rows=tile_rows,
                thumb_width=max_width // tile_cols,
                num_mosaics=1,
            )

            if result.mosaic_paths:
                parts: list[dict[str, Any]] = []
                parts.append({
                    "type": "text",
                    "text": f"Video chunk {chunk_idx} ({start:.0f}s - {end:.0f}s) of {path.name}:",
                })
                for mp in result.mosaic_paths:
                    b64 = base64.b64encode(mp.read_bytes()).decode()
                    parts.append(_image_part(b64, "image/jpeg", provider))
                    try:
                        mp.unlink(missing_ok=True)
                    except Exception:
                        pass
                yield _to_message(parts)

            start += step
            chunk_idx += 1


register(VideoFrameSample())
register(VideoChunk())
