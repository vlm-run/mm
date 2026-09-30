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
# Metadata benchmarks
# ---------------------------------------------------------------------------


def test_bench_context_creation(benchmark, large_tree: Path):
    """Benchmark Context creation (metadata scan + Arrow build)."""
    from mm.context import Context

    result = benchmark(Context, large_tree)
    assert result.num_files > 0


def test_bench_context_1k_mixed(benchmark, mixed_1k_tree: Path):
    """Benchmark metadata scan on 1000 mixed files (code + images)."""
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
# Fast benchmarks
# ---------------------------------------------------------------------------


def test_bench_fast_code_batch(benchmark, mixed_1k_tree: Path):
    """Benchmark fast extraction on code files."""
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
            scanner.extract_metadata(f)

    benchmark(extract_batch)


def test_bench_fast_video_native(benchmark, youtube_dir):
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

    result = benchmark(scanner.extract_metadata, target)
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

    from mm.ffmpeg import audio_transformer, ffmpeg_available

    if not ffmpeg_available():
        pytest.skip("ffmpeg not available")

    target = min(youtube_dir.glob("*.mp4"), key=lambda p: p.stat().st_size)

    result = benchmark(audio_transformer, target, speed=2.0)
    assert result.path.exists()


# ---------------------------------------------------------------------------
# End-to-end pipeline on real data
# ---------------------------------------------------------------------------


def test_bench_e2e_demo_dir(benchmark, demo_dir):
    """Benchmark full metadata pipeline on ~/data/1-demo (249 real files)."""
    if demo_dir is None:
        pytest.skip("~/data/1-demo not available")

    from mm.context import Context

    result = benchmark(Context, demo_dir)
    assert result.num_files > 200


# ---------------------------------------------------------------------------
# Single-file extract benchmarks (extract_metadata_one vs Scanner.scan + extract_metadata)
# ---------------------------------------------------------------------------

_SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "sample_files"


def test_bench_extract_metadata_one_image(benchmark):
    """Benchmark single-file image metadata extraction via extract_metadata_one.

    This is the hot path in ``mm cat`` and ``mm peek`` — previously required
    scanning the entire parent directory via ``Scanner(parent).scan()``.
    """
    img = _SAMPLE_DIR / "image.png"
    if not img.exists():
        pytest.skip("sample_files/image.png not available")

    from mm._mm import extract_metadata_one

    result = benchmark(extract_metadata_one, img)
    assert result.dimensions is not None


class TestBenchmarkMetadataRetrieval:
    """
    Creates a directory with 200 siblings to show the cost of scanning
    the parent dir just to extract one file. Both patterns are benchmarked
    so the comparison is direct.
    """

    def test_bench_extract_metadata_scanner(self, benchmark, tmp_path):
        """Benchmark the old Scanner(parent).scan() pattern."""
        from mm._mm import Scanner

        for i in range(200):
            (tmp_path / f"img_{i}.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        target = tmp_path / "img_100.png"

        def old_pattern():
            scanner = Scanner(str(target.parent))
            scanner.scan()
            return scanner.extract_metadata(target.name)

        result = benchmark(old_pattern)
        assert result is not None

    def test_bench_extract_metadata_one(self, benchmark, tmp_path):
        """Benchmark extract_metadata_one alone with 200 siblings (no dir scan)."""
        from mm._mm import extract_metadata_one

        for i in range(200):
            (tmp_path / f"img_{i}.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        target = tmp_path / "img_100.png"

        result = benchmark(extract_metadata_one, target)
        assert result is not None


# ---------------------------------------------------------------------------
# Token cost computation benchmarks
# ---------------------------------------------------------------------------


def test_bench_price_catalog_lookup(benchmark):
    """Benchmark model price catalog lookup (normalized key match)."""
    from mm.model_price_catalog import get_price_catalog

    catalog = get_price_catalog()
    models = ["google/gemini-2.5-flash", "gpt-4o", "anthropic/claude-3.5-sonnet"]

    def lookup_batch():
        return [catalog.lookup(m) for m in models]

    results = benchmark(lookup_batch)
    assert all(r is not None for r in results)


def test_bench_compute_cost(benchmark):
    """Benchmark cost computation from token usage dict."""
    from mm.model_price_catalog import get_price_catalog

    catalog = get_price_catalog()
    usage = {
        "prompt_tokens": 15000,
        "completion_tokens": 3000,
        "cached_tokens": 5000,
        "reasoning_tokens": 800,
        "total_tokens": 18000,
    }

    result = benchmark(catalog.compute_cost, usage, "google/gemini-2.5-flash")
    assert result is not None
    assert result.total_cost > 0


def test_bench_display_elapsed_with_cost(benchmark):
    """Benchmark the timing footer rendering with token cost."""
    from time import perf_counter

    from mm.display import display_elapsed

    start = perf_counter() - 1.5

    def render():
        display_elapsed(start, total_bytes=10 * 1024 * 1024, cached=True, token_cost=0.0142)

    benchmark(render)
