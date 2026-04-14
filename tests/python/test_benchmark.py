"""Performance benchmarks for mm Python API.

These are part of the ``slow`` tier — deselected by default so
``make test-python`` stays fast. Run with ``make test-python-full``
or ``pytest -m slow`` locally.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.slow


# ---------------------------------------------------------------------------
# L0 benchmarks
# ---------------------------------------------------------------------------


def test_bench_context_creation(benchmark, large_tree: Path):
    """Benchmark Context creation (L0 scan + Arrow build)."""
    from mm.context import Context

    result = benchmark(Context, large_tree)
    assert result.num_files > 0


def test_bench_context_1k_mixed(benchmark, mixed_1k_tree: Path):
    """Benchmark L0 scan on 1000 mixed files (code + images)."""
    from mm.context import Context

    result = benchmark(Context, mixed_1k_tree)
    assert result.num_files >= 900


def test_bench_to_polars(benchmark, large_tree: Path):
    """Benchmark to_polars() conversion."""
    from mm.context import Context

    ctx = Context(large_tree)

    df = benchmark(ctx.to_polars)
    assert len(df) == ctx.num_files


def test_bench_to_pandas(benchmark, large_tree: Path):
    """Benchmark to_pandas() conversion."""
    from mm.context import Context

    ctx = Context(large_tree)

    df = benchmark(ctx.to_pandas)
    assert len(df) == ctx.num_files


def test_bench_sql_query(benchmark, large_tree: Path):
    """Benchmark SQL query via SQLite."""
    from mm.context import Context

    ctx = Context(large_tree)

    result = benchmark(ctx.sql, "SELECT kind, COUNT(*) as n FROM files GROUP BY kind")
    assert result.num_rows > 0


def test_bench_filter(benchmark, large_tree: Path):
    """Benchmark filtering."""
    from mm.context import Context

    ctx = Context(large_tree)

    result = benchmark(ctx.filter, kind="code")
    assert result.num_files > 0


# ---------------------------------------------------------------------------
# L1 benchmarks
# ---------------------------------------------------------------------------


def test_bench_l1_code_batch(benchmark, mixed_1k_tree: Path):
    """Benchmark L1 extraction on code files."""
    from mm._mm import Scanner

    scanner = Scanner(str(mixed_1k_tree))
    scanner.scan()

    code_files = [
        f"src/file_{i}.py"
        for i in range(0, 800, 10)
        if (mixed_1k_tree / f"src/file_{i}.py").exists()
    ][:20]

    def extract_batch():
        for f in code_files:
            scanner.extract_l1(f)

    benchmark(extract_batch)


def test_bench_l1_video_native(benchmark, youtube_dir):
    """Benchmark native Rust video metadata extraction (vs ffprobe)."""
    if youtube_dir is None:
        pytest.skip("~/data/youtube not available")

    from mm._mm import Scanner

    scanner = Scanner(str(youtube_dir))
    scanner.scan()

    mp4s = [p.name for p in youtube_dir.glob("*.mp4")]
    if not mp4s:
        pytest.skip("No MP4 files found")

    # Use the smaller video for the benchmark
    target = min(mp4s, key=lambda n: (youtube_dir / n).stat().st_size)

    result = benchmark(scanner.extract_l1, target)
    assert result.dimensions is not None


# ---------------------------------------------------------------------------
# ffmpeg pipeline benchmarks
# ---------------------------------------------------------------------------


def test_bench_keyframe_mosaic(benchmark, youtube_dir):
    """Benchmark keyframe mosaic extraction."""
    if youtube_dir is None:
        pytest.skip("~/data/youtube not available")

    from mm.ffmpeg import extract_keyframe_mosaics, ffmpeg_available

    if not ffmpeg_available():
        pytest.skip("ffmpeg not available")

    target = min(youtube_dir.glob("*.mp4"), key=lambda p: p.stat().st_size)

    result = benchmark(extract_keyframe_mosaics, target, tile_cols=8, tile_rows=8, max_mosaics=2)
    assert len(result.mosaic_paths) > 0


def test_bench_audio_2x(benchmark, youtube_dir):
    """Benchmark 2x audio extraction."""
    if youtube_dir is None:
        pytest.skip("~/data/youtube not available")

    from mm.ffmpeg import extract_audio, ffmpeg_available

    if not ffmpeg_available():
        pytest.skip("ffmpeg not available")

    target = min(youtube_dir.glob("*.mp4"), key=lambda p: p.stat().st_size)

    result = benchmark(extract_audio, target, speed=2.0)
    assert result.path.exists()


# ---------------------------------------------------------------------------
# End-to-end pipeline on real data
# ---------------------------------------------------------------------------


def test_bench_e2e_demo_dir(benchmark, demo_dir):
    """Benchmark full L0 pipeline on ~/data/1-demo (249 real files)."""
    if demo_dir is None:
        pytest.skip("~/data/1-demo not available")

    from mm.context import Context

    result = benchmark(Context, demo_dir)
    assert result.num_files > 200
