"""Tests and benchmarks for mm.video — PyAV-based VideoReader.

Covers:
- Unit tests for VideoReader, Frame, FrameStream, probe()
- Performance benchmarks comparing PyAV vs ffmpeg subprocess baseline
- Edge cases: empty timestamps, out-of-range seeks, keyframe iteration

Benchmarks require ~/data/mmbench-tiny/bakery.mp4 (252.7s, 29.3 MB).
Skip with ``pytest -k 'not bench'`` when the file is unavailable.
"""

from __future__ import annotations

import base64
import io
import subprocess
import tempfile
from pathlib import Path

import pytest
from mm.ffmpeg import probe_duration
from mm.video import (
    Frame,
    FrameStream,
    VideoInfo,
    VideoReader,
    probe,
    tile_to_mosaic,
)
from PIL import Image

BAKERY = Path.home() / "data" / "mmbench-tiny" / "bakery.mp4"
requires_bakery = pytest.mark.skipif(
    not BAKERY.exists(),
    reason="bakery.mp4 not found at ~/data/mmbench-tiny/",
)


# ---------------------------------------------------------------------------
# Frame dataclass
# ---------------------------------------------------------------------------


class TestFrame:
    def test_encode_jpeg_roundtrip(self):
        img = Image.new("RGB", (100, 75), (255, 0, 0))
        frame = Frame(timestamp=1.5, image=img)
        b64, mime = frame.encode_jpeg()
        assert mime == "image/jpeg"
        decoded = Image.open(io.BytesIO(base64.b64decode(b64)))
        assert decoded.size == (100, 75)
        assert decoded.mode == "RGB"

    def test_encode_jpeg_rgba_converts(self):
        img = Image.new("RGBA", (50, 50), (0, 255, 0, 128))
        frame = Frame(timestamp=0.0, image=img)
        b64, mime = frame.encode_jpeg()
        assert mime == "image/jpeg"
        decoded = Image.open(io.BytesIO(base64.b64decode(b64)))
        assert decoded.mode == "RGB"

    def test_frozen(self):
        frame = Frame(timestamp=0.0, image=Image.new("RGB", (1, 1)))
        with pytest.raises(AttributeError):
            frame.timestamp = 1.0


# ---------------------------------------------------------------------------
# FrameStream
# ---------------------------------------------------------------------------


class TestFrameStream:
    def _make_stream(self, n: int) -> FrameStream:
        frames = [Frame(float(i), Image.new("RGB", (10, 10))) for i in range(n)]

        def factory():
            yield from frames

        return FrameStream(factory, count=n)

    def test_len(self):
        stream = self._make_stream(5)
        assert len(stream) == 5

    def test_iter(self):
        stream = self._make_stream(3)
        result = list(stream)
        assert len(result) == 3
        assert [f.timestamp for f in result] == [0.0, 1.0, 2.0]

    def test_collect(self):
        stream = self._make_stream(4)
        frames = stream.collect()
        assert isinstance(frames, list)
        assert len(frames) == 4

    def test_batched(self):
        stream = self._make_stream(10)
        batches = list(stream.batched(3))
        assert len(batches) == 4
        assert [len(b) for b in batches] == [3, 3, 3, 1]

    def test_batched_exact(self):
        stream = self._make_stream(6)
        batches = list(stream.batched(3))
        assert len(batches) == 2
        assert all(len(b) == 3 for b in batches)

    def test_empty_stream(self):
        stream = self._make_stream(0)
        assert len(stream) == 0
        assert stream.collect() == []
        assert list(stream.batched(4)) == []


# ---------------------------------------------------------------------------
# tile_to_mosaic
# ---------------------------------------------------------------------------


class TestTileToMosaic:
    def test_basic(self):
        images = [Image.new("RGB", (320, 180), (i * 20, 0, 0)) for i in range(16)]
        mosaic = tile_to_mosaic(images, cols=4, rows=4, thumb_width=160)
        assert mosaic.size == (640, 360)
        assert mosaic.mode == "RGB"

    def test_fewer_than_grid(self):
        images = [Image.new("RGB", (200, 100)) for _ in range(3)]
        mosaic = tile_to_mosaic(images, cols=4, rows=4, thumb_width=160)
        assert mosaic.size == (640, 360)

    def test_single_image(self):
        mosaic = tile_to_mosaic([Image.new("RGB", (800, 600))], cols=1, rows=1, thumb_width=160)
        assert mosaic.size == (160, 90)


# ---------------------------------------------------------------------------
# Real video tests (require bakery.mp4)
# ---------------------------------------------------------------------------


@requires_bakery
class TestProbe:
    def test_probe_returns_video_info(self):
        info = probe(BAKERY)
        assert isinstance(info, VideoInfo)
        assert info.duration > 250
        assert info.fps > 23
        assert info.width == 1280
        assert info.height == 720
        assert info.codec == "h264"
        assert info.has_audio is True

    def test_probe_nonexistent_raises(self):
        with pytest.raises(Exception):
            probe("/nonexistent/video.mp4")


@requires_bakery
class TestVideoReader:
    def test_context_manager(self):
        with VideoReader(BAKERY) as reader:
            assert reader.duration > 250
            assert reader.fps > 23
            assert reader.width == 1280

    def test_repr(self):
        with VideoReader(BAKERY) as reader:
            r = repr(reader)
            assert "bakery.mp4" in r
            assert "252." in r

    def test_frames_collect(self):
        with VideoReader(BAKERY) as reader:
            frames = reader.frames([10.0, 60.0, 120.0], width=512).collect()
            assert len(frames) == 3
            for f in frames:
                assert isinstance(f, Frame)
                assert f.image.width <= 512
                assert f.image.mode == "RGB"

    def test_frames_batched(self):
        with VideoReader(BAKERY) as reader:
            ts = [float(i * 10) for i in range(20)]
            batches = list(reader.frames(ts, width=256).batched(8))
            assert len(batches) == 3
            assert len(batches[0]) == 8
            assert len(batches[1]) == 8
            assert len(batches[2]) == 4

    def test_frames_empty_timestamps(self):
        with VideoReader(BAKERY) as reader:
            frames = reader.frames([], width=256).collect()
            assert frames == []

    def test_frames_preserves_order(self):
        with VideoReader(BAKERY) as reader:
            ts = [120.0, 10.0, 60.0]
            frames = reader.frames(ts, width=256).collect()
            assert [f.timestamp for f in frames] == pytest.approx(ts, abs=1.0)

    def test_keyframes(self):
        with VideoReader(BAKERY) as reader:
            kf = reader.keyframes(width=256, max_frames=10).collect()
            assert len(kf) == 10
            for f in kf:
                assert f.image.width <= 256

    def test_keyframes_all(self):
        with VideoReader(BAKERY) as reader:
            kf = reader.keyframes(width=256).collect()
            assert len(kf) > 50

    def test_encode_jpeg_from_reader(self):
        with VideoReader(BAKERY) as reader:
            frames = reader.frames([30.0], width=512).collect()
            b64, mime = frames[0].encode_jpeg()
            assert mime == "image/jpeg"
            assert len(b64) > 1000

    def test_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            VideoReader("/no/such/file.mp4")


# ---------------------------------------------------------------------------
# Benchmarks: PyAV vs ffmpeg subprocess
# ---------------------------------------------------------------------------


def _old_ffmpeg_extract_frame(path: str, ts: float, out_path: str, width: int = 1024):
    """Baseline: ffmpeg subprocess per-frame extraction."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{ts:.3f}",
            "-i",
            path,
            "-vf",
            f"thumbnail=10,scale={width}:-1",
            "-frames:v",
            "1",
            "-q:v",
            "3",
            "-update",
            "1",
            out_path,
        ],
        capture_output=True,
        timeout=30,
    )


@requires_bakery
class TestBenchProbe:
    def test_bench_pyav_probe(self, benchmark):
        """PyAV probe: ~7ms."""
        benchmark(probe, BAKERY)

    def test_bench_ffprobe_subprocess(self, benchmark):
        """ffprobe subprocess: ~58ms."""
        benchmark(probe_duration, str(BAKERY))


@requires_bakery
class TestBenchFrames:
    def test_bench_pyav_16_frames(self, benchmark):
        """PyAV parallel seek+decode 16 frames: ~250ms."""
        ts = [i * 15.0 for i in range(16)]

        def run():
            with VideoReader(BAKERY) as reader:
                return reader.frames(ts, width=1024).collect()

        result = benchmark(run)
        assert len(result) == 16

    def test_bench_ffmpeg_16_frames(self, benchmark):
        """ffmpeg subprocess 16 frames: ~320ms."""
        ts = [i * 15.0 for i in range(16)]

        def run():
            import shutil
            from concurrent.futures import ThreadPoolExecutor

            out_dir = Path(tempfile.mkdtemp(prefix="mm_bench_"))
            try:

                def extract(args):
                    idx, t = args
                    fp = out_dir / f"f_{idx:04d}.jpg"
                    _old_ffmpeg_extract_frame(str(BAKERY), t, str(fp))
                    return fp

                with ThreadPoolExecutor(max_workers=8) as pool:
                    paths = list(pool.map(extract, enumerate(ts)))
                return [p for p in paths if p.exists()]
            finally:
                shutil.rmtree(out_dir, ignore_errors=True)

        result = benchmark(run)
        assert len(result) == 16

    def test_bench_pyav_252_frames(self, benchmark):
        """PyAV parallel 252 frames (1fps): ~3.4s."""
        ts = [float(i) for i in range(253)]

        def run():
            with VideoReader(BAKERY) as reader:
                return reader.frames(ts, width=1024).collect()

        benchmark.extra_info["frames"] = 253
        result = benchmark(run)
        assert len(result) == 253

    def test_bench_ffmpeg_252_frames(self, benchmark):
        """ffmpeg subprocess 252 frames (1fps): ~4.4s."""
        ts = [float(i) for i in range(253)]

        def run():
            import shutil
            from concurrent.futures import ThreadPoolExecutor

            out_dir = Path(tempfile.mkdtemp(prefix="mm_bench_"))
            try:

                def extract(args):
                    idx, t = args
                    fp = out_dir / f"f_{idx:04d}.jpg"
                    _old_ffmpeg_extract_frame(str(BAKERY), t, str(fp))
                    return fp

                with ThreadPoolExecutor(max_workers=8) as pool:
                    paths = list(pool.map(extract, enumerate(ts)))
                return [p for p in paths if p.exists()]
            finally:
                shutil.rmtree(out_dir, ignore_errors=True)

        benchmark.extra_info["frames"] = 253
        result = benchmark(run)
        assert len(result) >= 250


@requires_bakery
class TestBenchKeyframes:
    def test_bench_pyav_keyframes(self, benchmark):
        """PyAV keyframe decode (all I-frames): ~600ms."""

        def run():
            with VideoReader(BAKERY) as reader:
                return reader.keyframes(width=512).collect()

        result = benchmark(run)
        assert len(result) > 50


@requires_bakery
class TestBenchMosaic:
    def test_bench_pyav_mosaic_pipeline(self, benchmark):
        """Full mosaic: 128 frames via PyAV + Pillow tiling."""

        def run():
            with VideoReader(BAKERY) as reader:
                ts_count = 128
                interval = reader.duration / ts_count
                ts = [(i + 0.5) * interval for i in range(ts_count)]
                frames = reader.frames(ts, width=160).collect()
                mosaics = []
                for i in range(0, len(frames), 16):
                    batch = [f.image for f in frames[i : i + 16]]
                    mosaics.append(tile_to_mosaic(batch, cols=4, rows=4, thumb_width=160))
                return mosaics

        result = benchmark(run)
        assert len(result) == 8

    def test_bench_ffmpeg_mosaic_pipeline(self, benchmark):
        """Full mosaic: 128 frames via ffmpeg subprocess + ffmpeg tiling."""
        from mm.ffmpeg import extract_uniform_mosaics

        def run():
            return extract_uniform_mosaics(
                BAKERY,
                tile_cols=4,
                tile_rows=4,
                thumb_width=160,
                num_mosaics=8,
            )

        result = benchmark(run)
        assert len(result.mosaic_paths) > 0


@requires_bakery
class TestBenchEndToEnd:
    def test_bench_pyav_full_pipeline(self, benchmark):
        """End-to-end: 16 frames -> resize -> JPEG -> base64 via PyAV."""
        ts = [i * 15.0 for i in range(16)]

        def run():
            with VideoReader(BAKERY) as reader:
                results = []
                for frame in reader.frames(ts, width=1024):
                    b64, mime = frame.encode_jpeg()
                    results.append(b64)
                return results

        result = benchmark(run)
        assert len(result) == 16
        assert all(len(b) > 1000 for b in result)

    def test_bench_ffmpeg_full_pipeline(self, benchmark):
        """End-to-end: 16 frames -> extract to disk -> read -> base64 via ffmpeg."""
        ts = [i * 15.0 for i in range(16)]

        def run():
            import shutil
            from concurrent.futures import ThreadPoolExecutor

            out_dir = Path(tempfile.mkdtemp(prefix="mm_bench_"))
            try:

                def extract(args):
                    idx, t = args
                    fp = out_dir / f"f_{idx:04d}.jpg"
                    _old_ffmpeg_extract_frame(str(BAKERY), t, str(fp))
                    return fp

                with ThreadPoolExecutor(max_workers=8) as pool:
                    paths = list(pool.map(extract, enumerate(ts)))

                results = []
                for p in paths:
                    if p.exists():
                        results.append(base64.b64encode(p.read_bytes()).decode())
                return results
            finally:
                shutil.rmtree(out_dir, ignore_errors=True)

        result = benchmark(run)
        assert len(result) == 16
