"""Tests for mm.scenes — PySceneDetect wrapper."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mm.scenes import (
    sample_scene_timestamps,
    sample_uniform_timestamps,
)


class TestSampleSceneTimestamps:
    """Test uniform sampling of scene midpoints."""

    def test_empty_scenes(self):
        assert sample_scene_timestamps([], 10) == []

    def test_fewer_scenes_than_n(self):
        scenes = [(0.0, 10.0), (10.0, 20.0), (20.0, 30.0)]
        result = sample_scene_timestamps(scenes, 10)
        assert len(result) == 3
        assert result == [5.0, 15.0, 25.0]

    def test_exact_match(self):
        scenes = [(0.0, 10.0), (10.0, 20.0)]
        result = sample_scene_timestamps(scenes, 2)
        assert len(result) == 2
        assert result == [5.0, 15.0]

    def test_more_scenes_than_n(self):
        scenes = [(i * 10.0, (i + 1) * 10.0) for i in range(100)]
        result = sample_scene_timestamps(scenes, 16)
        assert len(result) == 16
        # Should be sorted
        assert result == sorted(result)
        # Should span the full range
        assert result[0] < 50
        assert result[-1] > 500

    def test_single_scene(self):
        scenes = [(0.0, 60.0)]
        result = sample_scene_timestamps(scenes, 1)
        assert result == [30.0]


class TestSampleUniformTimestamps:
    """Test uniform timestamp generation (fallback)."""

    def test_basic(self):
        result = sample_uniform_timestamps(60.0, 4)
        assert len(result) == 4
        assert result[0] == pytest.approx(7.5)
        assert result[-1] == pytest.approx(52.5)

    def test_single(self):
        result = sample_uniform_timestamps(10.0, 1)
        assert result == [5.0]

    def test_zero_duration(self):
        assert sample_uniform_timestamps(0.0, 10) == []

    def test_zero_n(self):
        assert sample_uniform_timestamps(60.0, 0) == []

    def test_sixteen_frames(self):
        result = sample_uniform_timestamps(300.0, 16)
        assert len(result) == 16
        # Evenly spaced
        intervals = [result[i + 1] - result[i] for i in range(15)]
        for iv in intervals:
            assert iv == pytest.approx(intervals[0], rel=1e-6)


class TestSceneDetectAvailability:
    """Test graceful degradation when scenedetect is not installed."""

    def test_detect_scenes_without_scenedetect(self):
        from mm.scenes import detect_scenes

        with patch("mm.scenes.scenedetect_available", return_value=False):
            result = detect_scenes("/tmp/video.mp4")
            assert result.scenes == []
            assert result.num_scenes == 0
