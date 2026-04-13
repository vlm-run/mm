"""Video mosaic encoder: scene-aware frame extraction + tiled mosaic grids.

Extracts frames via scene detection (PySceneDetect) or uniform sampling,
then tiles them into mosaic grids using ``tile_frames_to_mosaics``.
Each yielded Message contains one or more mosaic JPEG images.

This is the default video encoder for fast mode — it produces a compact
visual summary without requiring an LLM call.
"""

from __future__ import annotations

import base64
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable

from mm.encoders import Message, _resolve_provider, register
from mm.encoders.image import _image_part, _to_message

logger = logging.getLogger(__name__)


class VideoMosaic:
    """Build mosaic grids from video frames, one Message per mosaic.

    Uses scene detection (PySceneDetect) when available, falling back
    to uniform temporal sampling.  Frames are tiled into ``tile_cols x
    tile_rows`` grids at ``thumb_width`` px per thumbnail.

    Kwargs:
        tile_cols: Mosaic grid columns (default 4).
        tile_rows: Mosaic grid rows (default 4).
        thumb_width: Per-frame thumbnail width in pixels (default 160).
        num_mosaics: Maximum number of mosaics to produce (default 8).
        num_frames: Total frames to sample before tiling (default 128).
    """

    name: str = "mosaic"
    media_types: tuple[str, ...] = ("video",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        tile_cols: int = kwargs.get("tile_cols", 4)
        tile_rows: int = kwargs.get("tile_rows", 4)
        thumb_width: int = kwargs.get("thumb_width", 160)
        num_mosaics: int = kwargs.get("num_mosaics", 8)
        num_frames: int = kwargs.get("num_frames", 128)
        provider: str = _resolve_provider()

        from mm.ffmpeg import (
            extract_frames_at_timestamps,
            ffmpeg_available,
            probe_duration,
            tile_frames_to_mosaics,
        )

        if not ffmpeg_available():
            yield _to_message([{
                "type": "text",
                "text": f"[ffmpeg not available for {path.name}]",
            }])
            return

        duration = probe_duration(path)
        if duration <= 0:
            yield _to_message([{
                "type": "text",
                "text": f"[Cannot determine duration for {path.name}]",
            }])
            return

        timestamps = _get_timestamps(path, duration, num_frames)

        frame_dir = Path(tempfile.mkdtemp(prefix="mm_mosaic_fr_"))
        mosaic_dir = Path(tempfile.mkdtemp(prefix="mm_mosaic_mo_"))
        try:
            frame_paths = extract_frames_at_timestamps(
                path, timestamps,
                thumb_width=thumb_width,
                out_dir=frame_dir,
            )

            if not frame_paths:
                yield _to_message([{
                    "type": "text",
                    "text": f"[No frames extracted from {path.name}]",
                }])
                return

            mosaic_paths = tile_frames_to_mosaics(
                frame_paths,
                tile_cols=tile_cols,
                tile_rows=tile_rows,
                out_dir=mosaic_dir,
                stem=path.stem,
            )

            if not mosaic_paths:
                yield _to_message([{
                    "type": "text",
                    "text": f"[Mosaic assembly failed for {path.name}]",
                }])
                return

            if len(mosaic_paths) > num_mosaics:
                mosaic_paths = mosaic_paths[:num_mosaics]

            mins, secs = divmod(duration, 60)
            dur_str = f"{int(mins)}m{secs:.0f}s"

            logger.debug(
                "video_mosaic [path=%s, duration=%s, frames=%d, mosaics=%d, grid=%dx%d]",
                path.name, dur_str, len(frame_paths), len(mosaic_paths),
                tile_cols, tile_rows,
            )

            parts: list[dict[str, Any]] = [{
                "type": "text",
                "text": (
                    f"{path.name} ({dur_str}) — "
                    f"{len(mosaic_paths)} mosaic(s), "
                    f"{tile_cols}x{tile_rows} grid, "
                    f"{len(frame_paths)} frames:"
                ),
            }]
            for mp in mosaic_paths:
                b64 = base64.b64encode(mp.read_bytes()).decode()
                parts.append(_image_part(b64, "image/jpeg", provider))

            yield _to_message(parts)
        finally:
            shutil.rmtree(frame_dir, ignore_errors=True)
            shutil.rmtree(mosaic_dir, ignore_errors=True)


def _get_timestamps(
    path: Path, duration: float, num_frames: int,
) -> list[float]:
    """Get frame timestamps via scene detection or uniform sampling."""
    try:
        from mm.common.video.shot_detection import (
            detect_scenes,
            sample_scene_timestamps,
            sample_uniform_timestamps,
            scenedetect_available,
        )

        if scenedetect_available():
            result = detect_scenes(path)
            if result.scenes:
                return sample_scene_timestamps(result.scenes, num_frames)
            return sample_uniform_timestamps(duration, num_frames)
        return sample_uniform_timestamps(duration, num_frames)
    except ImportError:
        step = duration / num_frames if num_frames > 0 else duration
        return [i * step for i in range(num_frames)]


register(VideoMosaic())
