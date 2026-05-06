"""Runtime budgets for ``mm cat`` on images and videos (fast mode).

Run with ``pytest -m 'perf and slow'`` or full suite. Heavier than ``find`` perf.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from mm.cli import app
from PIL import Image
from typer.testing import CliRunner

from .test_utils import write_minimal_mp4

pytestmark = [pytest.mark.perf, pytest.mark.slow]

runner = CliRunner()


def _write_valid_png(path: Path) -> None:
    img = Image.new("RGB", (1, 1), color=(40, 80, 120))
    img.save(path, "PNG")


def _cat_image_max_s() -> float:
    return float(os.environ.get("MM_TEST_CAT_IMAGE_MAX_S", "8.0"))


def _cat_image_multi_max_s() -> float:
    return float(os.environ.get("MM_TEST_CAT_IMAGE_MULTI_MAX_S", "6.0"))


def _cat_video_max_s() -> float:
    return float(os.environ.get("MM_TEST_CAT_VIDEO_MAX_S", "20.0"))


def _cat_video_multi_max_s() -> float:
    return float(os.environ.get("MM_TEST_CAT_VIDEO_MULTI_MAX_S", "30.0"))


def test_cat_single_image_fast_cli_under_budget(tmp_path: Path) -> None:
    img = tmp_path / "a.png"
    _write_valid_png(img)
    t0 = time.perf_counter()
    r = runner.invoke(
        app,
        ["cat", str(img), "-m", "fast", "--format", "json"],
    )
    elapsed = time.perf_counter() - t0
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert isinstance(data, list) and len(data) == 1
    assert elapsed < _cat_image_max_s(), f"cat 1 image took {elapsed:.3f}s"


def test_cat_three_images_fast_cli_under_budget(tmp_path: Path) -> None:
    paths: list[str] = []
    for i in range(3):
        p = tmp_path / f"i{i}.png"
        _write_valid_png(p)
        paths.append(str(p))
    t0 = time.perf_counter()
    r = runner.invoke(
        app,
        ["cat", *paths, "-m", "fast", "--format", "json", "-y"],
    )
    elapsed = time.perf_counter() - t0
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert len(data) == 3
    assert elapsed < _cat_image_multi_max_s(), f"cat 3 images took {elapsed:.3f}s"


def test_cat_single_video_fast_cli_under_budget(tmp_path: Path) -> None:
    """Fast video path: ``video-mosaic`` encoder + short LLM caption."""
    vid = tmp_path / "clip.mp4"
    write_minimal_mp4(vid)
    t0 = time.perf_counter()
    r = runner.invoke(
        app,
        ["cat", str(vid), "-m", "fast", "--format", "json"],
    )
    elapsed = time.perf_counter() - t0
    assert r.exit_code == 0, r.output
    data = json.loads(r.stdout)
    assert isinstance(data, list) and len(data) == 1
    assert "clip.mp4" in data[0].get("path", "")
    assert elapsed < _cat_video_max_s(), f"cat 1 video took {elapsed:.3f}s"


def test_cat_two_videos_fast_cli_under_budget(tmp_path: Path) -> None:
    paths: list[str] = []
    for name in ("a.mp4", "b.mp4"):
        p = tmp_path / name
        write_minimal_mp4(p)
        paths.append(str(p))
    t0 = time.perf_counter()
    r = runner.invoke(
        app,
        ["cat", *paths, "-m", "fast", "--format", "json", "-y"],
    )
    elapsed = time.perf_counter() - t0
    assert r.exit_code == 0, r.output
    data = json.loads(r.stdout)
    assert len(data) == 2
    assert elapsed < _cat_video_multi_max_s(), f"cat 2 videos took {elapsed:.3f}s"


def test_cat_single_video_real_file_under_budget() -> None:
    """Optional: timing on a real MP4 under ``~/data/mmbench-mini`` if present."""
    vid = Path.home() / "data" / "mmbench-mini" / "video" / "gemini_intro.mp4"
    if not vid.is_file():
        pytest.skip("~/data/mmbench-mini/video/gemini_intro.mp4 not found")
    max_s = float(os.environ.get("MM_TEST_CAT_VIDEO_REAL_MAX_S", "120.0"))
    t0 = time.perf_counter()
    r = runner.invoke(
        app,
        ["cat", str(vid), "-m", "fast", "--format", "json"],
    )
    elapsed = time.perf_counter() - t0
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert len(data) == 1
    assert elapsed < max_s, f"cat real video took {elapsed:.3f}s"
