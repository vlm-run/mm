"""Scene-aware video strategies using PySceneDetect.

Two strategies for processing videos shot-by-shot:

- ``shot-frames``: Detect shots, extract representative frames per shot,
  yield one Message per shot with base64-encoded frames.
- ``shot-mosaic``: Detect shots, build a mosaic grid per shot using
  the shared ``tile_frames_to_mosaics`` pipeline, yield one Message
  per shot mosaic.

Both strategies yield Messages sequentially (one shot at a time) to
avoid Out Of Memory when combined with ``-m accurate`` multi-chunk generation.

Requires: ``pip install mm[extract]`` (for scenedetect + opencv)
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


def _detect_shots(video_path: Path, threshold: float) -> list[tuple[float, float]]:
    """Run PySceneDetect and return shot boundaries as (start_s, end_s) pairs."""
    from mm.common.video.shot_detection import detect_scenes, scenedetect_available

    if not scenedetect_available():
        raise ImportError(
            "scenedetect is required for shot-based encoders. Install with: pip install mm[extract]"
        )

    result = detect_scenes(video_path, threshold=threshold)
    logger.debug(
        "scene_detect [path=%s, shots=%d, elapsed=%.0fms]",
        video_path.name,
        result.num_scenes,
        result.elapsed_ms,
    )

    if not result.scenes:
        from mm.ffmpeg import probe_duration

        duration = probe_duration(video_path)
        if duration > 0:
            return [(0.0, duration)]
        return []

    return result.scenes


def _sample_timestamps_in_range(start: float, end: float, n: int) -> list[float]:
    """Generate n uniformly spaced timestamps within [start, end)."""
    if n <= 0:
        return []
    duration = end - start
    if duration <= 0 or n == 1:
        return [start + duration / 2]
    step = duration / n
    return [start + (i + 0.5) * step for i in range(n)]


class ShotFrames:
    """Detect shots via PySceneDetect, extract frames per shot.

    Each yielded Message contains base64-encoded representative frames
    from a single shot, plus a text header with the time range.
    Shots are processed sequentially to avoid OOM.

    Kwargs:
        threshold: Scene detection threshold (default 27.0).
            Higher = fewer shots.
        max_frames_per_shot: Max frames to extract per shot (default 8).
        max_width: Frame resize width in pixels (default 1024).
    """

    name: str = "shot-frames"
    media_types: tuple[str, ...] = ("video",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        threshold: float = kwargs.get("threshold", 27.0)
        max_frames_per_shot: int = kwargs.get("max_frames_per_shot", 8)
        max_width: int = kwargs.get("max_width", 1024)
        provider: str = _resolve_provider()

        from mm.ffmpeg import extract_frames_at_timestamps, ffmpeg_available

        if not ffmpeg_available():
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": f"[ffmpeg not available for {path.name}]",
                    }
                ]
            )
            return

        shots = _detect_shots(path, threshold)
        if not shots:
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": f"[No shots detected in {path.name}]",
                    }
                ]
            )
            return

        logger.debug(
            "shot_frames [path=%s, shots=%d, max_frames=%d]",
            path.name,
            len(shots),
            max_frames_per_shot,
        )

        for shot_idx, (start, end) in enumerate(shots):
            timestamps = _sample_timestamps_in_range(
                start,
                end,
                max_frames_per_shot,
            )

            out_dir = Path(tempfile.mkdtemp(prefix=f"mm_sf_{shot_idx}_"))
            try:
                frame_paths = extract_frames_at_timestamps(
                    path,
                    timestamps,
                    thumb_width=max_width,
                    out_dir=out_dir,
                )

                if not frame_paths:
                    continue

                parts: list[dict[str, Any]] = [
                    {
                        "type": "text",
                        "text": (
                            f"Shot {shot_idx + 1}/{len(shots)} of {path.name} "
                            f"({start:.1f}s \u2013 {end:.1f}s):"
                        ),
                    }
                ]

                for fp in frame_paths:
                    b64 = base64.b64encode(fp.read_bytes()).decode()
                    parts.append(_image_part(b64, "image/jpeg", provider))

                yield _to_message(parts)
            finally:
                shutil.rmtree(out_dir, ignore_errors=True)


class ShotMosaic:
    """Detect shots via PySceneDetect, build a mosaic per shot.

    Reuses ``tile_frames_to_mosaics`` from ``mm.ffmpeg`` to tile
    extracted frames into a single mosaic image per shot.  Each
    yielded Message contains one shot's mosaic plus a text header.
    Shots are processed sequentially to avoid OOM.

    Kwargs:
        threshold: Scene detection threshold (default 27.0).
        tile_cols: Mosaic grid columns (default 4).
        tile_rows: Mosaic grid rows (default 4).
        thumb_width: Frame thumbnail width in pixels (default 160).
    """

    name: str = "shot-mosaic"
    media_types: tuple[str, ...] = ("video",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        threshold: float = kwargs.get("threshold", 27.0)
        tile_cols: int = kwargs.get("tile_cols", 4)
        tile_rows: int = kwargs.get("tile_rows", 4)
        thumb_width: int = kwargs.get("thumb_width", 160)
        provider: str = _resolve_provider()

        from mm.ffmpeg import (
            extract_frames_at_timestamps,
            ffmpeg_available,
            tile_frames_to_mosaics,
        )

        if not ffmpeg_available():
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": f"[ffmpeg not available for {path.name}]",
                    }
                ]
            )
            return

        shots = _detect_shots(path, threshold)
        if not shots:
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": f"[No shots detected in {path.name}]",
                    }
                ]
            )
            return

        frames_per_mosaic = tile_cols * tile_rows

        logger.debug(
            "shot_mosaic [path=%s, shots=%d, grid=%dx%d]",
            path.name,
            len(shots),
            tile_cols,
            tile_rows,
        )

        for shot_idx, (start, end) in enumerate(shots):
            timestamps = _sample_timestamps_in_range(
                start,
                end,
                frames_per_mosaic,
            )

            frame_dir = Path(tempfile.mkdtemp(prefix=f"mm_sm_fr_{shot_idx}_"))
            mosaic_dir = Path(tempfile.mkdtemp(prefix=f"mm_sm_mo_{shot_idx}_"))
            try:
                frame_paths = extract_frames_at_timestamps(
                    path,
                    timestamps,
                    thumb_width=thumb_width,
                    out_dir=frame_dir,
                )

                if not frame_paths:
                    continue

                mosaic_paths = tile_frames_to_mosaics(
                    frame_paths,
                    tile_cols=tile_cols,
                    tile_rows=tile_rows,
                    out_dir=mosaic_dir,
                    stem=f"{path.stem}_shot{shot_idx}",
                )

                if not mosaic_paths:
                    continue

                parts: list[dict[str, Any]] = [
                    {
                        "type": "text",
                        "text": (
                            f"Shot {shot_idx + 1}/{len(shots)} of {path.name} "
                            f"({start:.1f}s \u2013 {end:.1f}s):"
                        ),
                    }
                ]

                for mp in mosaic_paths:
                    b64 = base64.b64encode(mp.read_bytes()).decode()
                    parts.append(_image_part(b64, "image/jpeg", provider))

                yield _to_message(parts)
            finally:
                shutil.rmtree(frame_dir, ignore_errors=True)
                shutil.rmtree(mosaic_dir, ignore_errors=True)


register(ShotFrames())
register(ShotMosaic())
