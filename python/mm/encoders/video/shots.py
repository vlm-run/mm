"""Scene-aware video strategies using PySceneDetect + PyAV.

Four encoders for processing videos shot-by-shot:

- ``video-shots``: Detect shots, extract representative frames per shot.
- ``video-shots-w-transcript``: Same with Whisper transcript prepended.
- ``video-shot-mosaic``: Detect shots, build a mosaic grid per shot.
- ``video-shot-mosaic-w-transcript``: Same with Whisper transcript prepended.

All strategies yield Messages sequentially (one shot at a time) to
avoid OOM. Uses PyAV for in-process frame decoding — no subprocess
or temp files.
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any, Iterable

from mm.encoders import Message, _resolve_provider, register
from mm.encoders.image import _image_part, _to_message
from mm.encoders.video._transcript import encode_with_transcript

logger = logging.getLogger(__name__)


def _detect_shots(video_path: Path, threshold: float) -> list[tuple[float, float]]:
    """Run PySceneDetect and return shot boundaries as (start_s, end_s) pairs."""
    from mm.common.video.shot_detection import detect_scenes, scenedetect_available

    if not scenedetect_available():
        raise ImportError(
            "scenedetect is required for shot-based encoders but is not available — "
            "check your mm installation"
        )

    result = detect_scenes(video_path, threshold=threshold)
    logger.debug(
        "scene_detect [path=%s, shots=%d, elapsed=%.0fms]",
        video_path.name,
        result.num_scenes,
        result.elapsed_ms,
    )

    if not result.scenes:
        from mm.video import probe

        info = probe(video_path)
        if info.duration > 0:
            return [(0.0, info.duration)]
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


class VideoShots:
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

    name: str = "video-shots"
    media_types: tuple[str, ...] = ("video",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        threshold: float = kwargs.get("threshold", 27.0)
        max_frames_per_shot: int = kwargs.get("max_frames_per_shot", 8)
        max_width: int = kwargs.get("max_width", 1024)
        provider: str = _resolve_provider()

        from mm.video import VideoReader, pyav_runnable

        if not pyav_runnable():
            yield _to_message([{"type": "text", "text": f"[PyAV not runnable for {path.name}]"}])
            return

        shots = _detect_shots(path, threshold)
        if not shots:
            yield _to_message([{"type": "text", "text": f"[No shots detected in {path.name}]"}])
            return

        logger.debug(
            "video_shots [path=%s, shots=%d, max_frames=%d]",
            path.name,
            len(shots),
            max_frames_per_shot,
        )

        # Bundle timestamps across all shots into one decode pass — avoids
        # re-spawning a ThreadPoolExecutor per shot (was 76× on bakery.mp4).
        flat_ts: list[float] = []
        offsets: list[int] = [0]
        for start, end in shots:
            shot_ts = _sample_timestamps_in_range(start, end, max_frames_per_shot)
            flat_ts.extend(shot_ts)
            offsets.append(len(flat_ts))

        with VideoReader(path) as reader:
            all_frames = list(reader.frames(flat_ts, width=max_width))

        for shot_idx, (start, end) in enumerate(shots):
            shot_frames = all_frames[offsets[shot_idx] : offsets[shot_idx + 1]]
            if not shot_frames:
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
            for frame in shot_frames:
                b64, mime = frame.encode_jpeg()
                parts.append(_image_part(b64, mime, provider))

            yield _to_message(parts)


class VideoShotsWithTranscript:
    """Detect shots and extract frames, with Whisper transcript prepended.

    Kwargs: Same as ``VideoShots`` plus ``model``, ``language``,
    ``audio_speed``.
    """

    name: str = "video-shots-w-transcript"
    media_types: tuple[str, ...] = ("video",)

    _visual = VideoShots()

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        yield from encode_with_transcript(path, self._visual.encode, **kwargs)


class VideoShotMosaic:
    """Detect shots via PySceneDetect, build a mosaic per shot.

    Tiles extracted frames into a single mosaic image per shot using
    ``tile_to_mosaic`` from ``mm.video``.

    Kwargs:
        threshold: Scene detection threshold (default 27.0).
        tile_cols: Mosaic grid columns (default 4).
        tile_rows: Mosaic grid rows (default 4).
        thumb_width: Frame thumbnail width in pixels (default 160).
    """

    name: str = "video-shot-mosaic"
    media_types: tuple[str, ...] = ("video",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        threshold: float = kwargs.get("threshold", 27.0)
        tile_cols: int = kwargs.get("tile_cols", 4)
        tile_rows: int = kwargs.get("tile_rows", 4)
        thumb_width: int = kwargs.get("thumb_width", 160)
        provider: str = _resolve_provider()

        from mm.video import VideoReader, pyav_runnable, tile_to_mosaic

        if not pyav_runnable():
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": f"[PyAV not runnable for {path.name}]",
                    }
                ]
            )
            return

        shots = _detect_shots(path, threshold)
        if not shots:
            yield _to_message([{"type": "text", "text": f"[No shots detected in {path.name}]"}])
            return

        frames_per_mosaic = tile_cols * tile_rows

        logger.debug(
            "video_shot_mosaic [path=%s, shots=%d, grid=%dx%d]",
            path.name,
            len(shots),
            tile_cols,
            tile_rows,
        )

        # Bundle timestamps across all shots into one decode pass.
        flat_ts: list[float] = []
        offsets: list[int] = [0]
        for start, end in shots:
            shot_ts = _sample_timestamps_in_range(start, end, frames_per_mosaic)
            flat_ts.extend(shot_ts)
            offsets.append(len(flat_ts))

        with VideoReader(path) as reader:
            all_frames = list(reader.frames(flat_ts, width=thumb_width))

        for shot_idx, (start, end) in enumerate(shots):
            shot_frames = all_frames[offsets[shot_idx] : offsets[shot_idx + 1]]
            if not shot_frames:
                continue

            mosaic_img = tile_to_mosaic(
                [f.image for f in shot_frames],
                cols=tile_cols,
                rows=tile_rows,
                thumb_width=thumb_width,
            )

            buf = io.BytesIO()
            mosaic_img.save(buf, "JPEG", quality=85)
            b64 = base64.b64encode(buf.getvalue()).decode()

            parts: list[dict[str, Any]] = [
                {
                    "type": "text",
                    "text": (
                        f"Shot {shot_idx + 1}/{len(shots)} of {path.name} "
                        f"({start:.1f}s \u2013 {end:.1f}s):"
                    ),
                },
                _image_part(b64, "image/jpeg", provider),
            ]
            yield _to_message(parts)


class VideoShotMosaicWithTranscript:
    """Detect shots and build mosaics, with Whisper transcript prepended.

    Kwargs: Same as ``VideoShotMosaic`` plus ``model``,
    ``language``, ``audio_speed``.
    """

    name: str = "video-shot-mosaic-w-transcript"
    media_types: tuple[str, ...] = ("video",)

    _visual = VideoShotMosaic()

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        yield from encode_with_transcript(path, self._visual.encode, **kwargs)


register(VideoShots())
register(VideoShotsWithTranscript())
register(VideoShotMosaic())
register(VideoShotMosaicWithTranscript())
