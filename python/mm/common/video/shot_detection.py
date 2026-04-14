"""PySceneDetect wrapper for shot boundary detection.

Detects scene changes in video files and provides uniform sampling
of scene midpoints for mosaic extraction.

Install: pip install mm[video]
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SceneResult:
    """Result of scene detection."""

    scenes: list[tuple[float, float]] = field(default_factory=list)
    elapsed_ms: float = 0.0
    num_scenes: int = 0


def scenedetect_available() -> bool:
    """Check if scenedetect is installed."""
    from mm._bootstrap import preload_media_libs

    preload_media_libs()
    try:
        import scenedetect  # noqa: F401

        return True
    except ImportError:
        return False


def detect_scenes(
    video_path: str | Path,
    *,
    threshold: float = 27.0,
    min_scene_len: int = 15,
) -> SceneResult:
    """Detect scene boundaries using PySceneDetect ContentDetector.

    Args:
        video_path: Path to video file.
        threshold: Content change threshold (higher = fewer scenes). Default 27.0.
        min_scene_len: Minimum scene length in frames. Default 15.

    Returns:
        SceneResult with list of (start_s, end_s) tuples.
    """
    if not scenedetect_available():
        return SceneResult()

    t0 = time.monotonic()

    from scenedetect import ContentDetector, SceneManager, open_video

    video = open_video(str(video_path))
    scene_manager = SceneManager()
    scene_manager.add_detector(
        ContentDetector(
            threshold=threshold,
            min_scene_len=min_scene_len,
        )
    )
    scene_manager.detect_scenes(video)
    scene_list = scene_manager.get_scene_list()

    scenes = [(scene[0].get_seconds(), scene[1].get_seconds()) for scene in scene_list]

    elapsed = (time.monotonic() - t0) * 1000

    return SceneResult(
        scenes=scenes,
        elapsed_ms=round(elapsed, 1),
        num_scenes=len(scenes),
    )


def sample_scene_timestamps(
    scenes: list[tuple[float, float]],
    n: int,
) -> list[float]:
    """Uniformly sample N scene midpoints from detected scenes.

    If fewer scenes than N, returns all midpoints.
    Samples are evenly spaced across the scene list index.

    Args:
        scenes: List of (start_s, end_s) scene boundaries.
        n: Number of timestamps to sample.

    Returns:
        Sorted list of timestamps (seconds) at scene midpoints.
    """
    if not scenes:
        return []

    if len(scenes) <= n:
        return sorted((s + e) / 2 for s, e in scenes)

    step = len(scenes) / n
    indices = [int(i * step) for i in range(n)]
    timestamps = [(scenes[i][0] + scenes[i][1]) / 2 for i in indices]
    return sorted(timestamps)


def sample_uniform_timestamps(
    duration_s: float,
    n: int,
) -> list[float]:
    """Generate N uniformly spaced timestamps across video duration.

    Fallback when scene detection is unavailable or returns no scenes.

    Args:
        duration_s: Video duration in seconds.
        n: Number of timestamps.

    Returns:
        List of timestamps evenly distributed across the duration.
    """
    if duration_s <= 0 or n <= 0:
        return []
    interval = duration_s / n
    return [(i + 0.5) * interval for i in range(n)]
