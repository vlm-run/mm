"""Video mosaic encoder: scene-aware frame extraction + tiled mosaic grids.

Extracts frames via scene detection (PySceneDetect) or uniform sampling,
then tiles them into mosaic grids using ``tile_to_mosaic``.
Each yielded Message contains one or more mosaic JPEG images.

Uses PyAV for in-process frame decoding — no subprocess or temp files.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any, Iterable

from mm.encoders import register, resolve_provider
from mm.encoders.base import Encoder, Message, to_message
from mm.encoders.image import _image_part
from mm.utils import get_b64

logger = logging.getLogger(__name__)


class VideoMosaic(Encoder):
    """Build mosaic grids from video frames, one Message per mosaic.

    Uses scene detection (PySceneDetect) when available, falling back
    to uniform temporal sampling. Frames are tiled into ``tile_cols x
    tile_rows`` grids at ``thumb_width`` px per thumbnail.

    Kwargs:
        tile_cols: Mosaic grid columns (default 4).
        tile_rows: Mosaic grid rows (default 4).
        thumb_width: Per-frame thumbnail width in pixels (default 160).
        num_mosaics: Maximum number of mosaics to produce (default 8).
        num_frames: Total frames to sample before tiling (default 128).
        mode: fast | accurate.
        generate_model: --generate.model CLI flag.
    """

    name = "mosaic"
    kind = "video"

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        from mm.video import VideoReader, pyav_runnable, tile_to_mosaic

        if not pyav_runnable():
            yield to_message(
                [
                    {"type": "text", "text": f"[PyAV not runnable for {path.name}]"},
                ]
            )
            return

        tile_cols: int = kwargs.get("tile_cols", 4)
        tile_rows: int = kwargs.get("tile_rows", 4)
        thumb_width: int = kwargs.get("thumb_width", 160)
        num_mosaics: int = kwargs.get("num_mosaics", 8)
        num_frames: int = kwargs.get("num_frames", 128)
        generate_model = kwargs.get("generate_model", None)
        provider: str = resolve_provider(generate_model)

        with VideoReader(path) as reader:
            duration = reader.duration
            if duration <= 0:
                yield to_message(
                    [{"type": "text", "text": f"[Cannot determine duration for {path.name}]"}]
                )
                return

            timestamps = _get_timestamps(path, duration, num_frames)
            frames_per_mosaic = tile_cols * tile_rows

            mosaic_b64s: list[str] = []
            frames_used = 0
            for batch in reader.frames(timestamps, width=thumb_width).batched(frames_per_mosaic):
                if len(mosaic_b64s) >= num_mosaics:
                    break
                mosaic_img = tile_to_mosaic(
                    [f.image for f in batch],
                    cols=tile_cols,
                    rows=tile_rows,
                    thumb_width=thumb_width,
                )
                buf = io.BytesIO()
                mosaic_img.save(buf, "JPEG", quality=85)
                mosaic_b64s.append(get_b64(buf.getvalue()))
                frames_used += len(batch)

            if not mosaic_b64s:
                yield to_message(
                    [{"type": "text", "text": f"[No frames extracted from {path.name}]"}]
                )
                return

            mins, secs = divmod(duration, 60)
            dur_str = f"{int(mins)}m{secs:.0f}s"

            logger.debug(
                "video_mosaic [path=%s, duration=%s, frames=%d, mosaics=%d, grid=%dx%d]",
                path.name,
                dur_str,
                frames_used,
                len(mosaic_b64s),
                tile_cols,
                tile_rows,
            )

            parts: list[dict[str, Any]] = [
                {
                    "type": "text",
                    "text": (
                        f"{path.name} ({dur_str}) — "
                        f"{len(mosaic_b64s)} mosaic(s), "
                        f"{tile_cols}x{tile_rows} grid, "
                        f"{frames_used} frames:"
                    ),
                }
            ]
            for b64 in mosaic_b64s:
                parts.append(_image_part(b64, "image/jpeg", provider))

            yield to_message(parts)


def _get_timestamps(
    path: Path,
    duration: float,
    num_frames: int,
) -> list[float]:
    """Get frame timestamps via scene detection or uniform sampling."""
    try:
        from mm.common.video.shot_detection import (
            detect_scenes,
            sample_scene_timestamps,
            sample_uniform_timestamps,
        )

        result = detect_scenes(path)
        if result.scenes:
            return sample_scene_timestamps(result.scenes, num_frames)
        return sample_uniform_timestamps(duration, num_frames)
    except ImportError:
        step = duration / num_frames if num_frames > 0 else duration
        return [i * step for i in range(num_frames)]


class VideoMosaicWithTranscript(Encoder):
    """Build mosaic grids from video frames with Whisper transcript.

    Yields a transcript Message first, then mosaic grids identical
    to ``VideoMosaic``. Falls back to mosaic-only output when Whisper
    is unavailable.

    Kwargs:
        tile_cols, tile_rows, thumb_width, num_mosaics, num_frames:
            Same as ``VideoMosaic``.
        model: Transcription model name (default chosen by backend).
        language: Language code or "auto" (default "auto").
        audio_speed: Playback speed multiplier (default 2.0).
        mode: fast | accurate.
    """

    name = "mosaic-w-transcript"
    kind = "video"

    _visual = VideoMosaic()

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        from mm.encoders.video._transcript import encode_with_transcript

        yield from encode_with_transcript(path, self._visual.encode, **kwargs)


register(VideoMosaic())
register(VideoMosaicWithTranscript())
