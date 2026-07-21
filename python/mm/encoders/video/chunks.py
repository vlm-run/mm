"""Video encoding strategies: chunked encoding and submodule registration.

Provides ``VideoChunk`` and imports all video encoder submodules so their
classes self-register.  Uses PyAV for in-process decoding.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterable

from mm.encoders import register, resolve_provider
from mm.encoders.base import Encoder, Message, to_message
from mm.encoders.image import _image_part

logger = logging.getLogger(__name__)

DEFAULT_CHUNKS_DURATION = 60
DEFAULT_OVERLAP = 5


class VideoChunk(Encoder):
    """Split video into overlapping time-based chunks.

    Each yielded Message contains extracted frames for one chunk plus
    a text header with the time range.

    Kwargs:
        chunk_duration: Seconds per chunk (default 60).
        overlap: Overlap between chunks in seconds (default 5).
        max_width: Frame resize width in pixels (default 1024).
        frames_per_chunk: Number of frames to extract per chunk (default 16).
        generate_model: --generate.model CLI flag
    """

    name = "chunked"
    kind = "video"

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        from mm.video import VideoReader, pyav_runnable

        if not pyav_runnable():
            yield to_message([{"type": "text", "text": f"[PyAV not runnable for {path.name}]"}])
            return

        chunk_duration: int = kwargs.get("chunk_duration", DEFAULT_CHUNKS_DURATION)
        overlap: int = kwargs.get("overlap", DEFAULT_OVERLAP)
        max_width: int = kwargs.get("max_width", 1024)
        model = kwargs.get("generate_model", None)

        frames_per_chunk: int = kwargs.get("frames_per_chunk", 16)
        provider: str = resolve_provider(model)

        with VideoReader(path) as reader:
            video_duration = reader.duration
            if video_duration <= 0:
                yield to_message(
                    [{"type": "text", "text": f"[Cannot determine duration for {path.name}]"}]
                )
                return

            start: float = 0.0
            step: int = max(chunk_duration - overlap, 1)
            segments: list[tuple[float, float]] = []
            while start < video_duration:
                end = min(start + chunk_duration, video_duration)
                segments.append((start, end))
                start += step

            logger.debug(
                "video_chunk [path=%s, duration=%.1fs, chunk=%ds, overlap=%ds, segments=%d]",
                path.name,
                video_duration,
                chunk_duration,
                overlap,
                segments,
            )

            from mm.encoders.video import uniform_timestamps_range

            def _submit_fn(varg: tuple[int, tuple[float, float]]):
                idx, (start, end) = varg
                chunk_timestamps = uniform_timestamps_range(start, end, frames_per_chunk)
                frames = reader.frames(chunk_timestamps, width=max_width).collect()
                if frames:
                    parts: list[dict[str, Any]] = [
                        {
                            "type": "text",
                            "text": f"Video chunk {idx} ({start:.0f}s - {end:.0f}s) of {path.name}:",
                        }
                    ]
                    for frame in frames:
                        b64, mime = frame.encode_jpeg()
                        parts.append(_image_part(b64, mime, provider))
                    return to_message(parts)

            with ThreadPoolExecutor(max_workers=min(4, len(segments))) as pool:
                yield from filter(None, pool.map(_submit_fn, enumerate(segments)))


register(VideoChunk())
