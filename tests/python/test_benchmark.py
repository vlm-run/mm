"""Performance benchmarks for vlmctx Python API."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_bench_context_creation(benchmark, large_tree: Path):
    """Benchmark Context creation (L0 scan + Arrow build)."""
    from vlmctx.context import Context

    result = benchmark(Context, large_tree)
    assert result.num_files > 0


def test_bench_to_polars(benchmark, large_tree: Path):
    """Benchmark to_polars() conversion."""
    from vlmctx.context import Context

    ctx = Context(large_tree)

    df = benchmark(ctx.to_polars)
    assert len(df) == ctx.num_files


def test_bench_to_pandas(benchmark, large_tree: Path):
    """Benchmark to_pandas() conversion."""
    from vlmctx.context import Context

    ctx = Context(large_tree)

    df = benchmark(ctx.to_pandas)
    assert len(df) == ctx.num_files


def test_bench_sql_query(benchmark, large_tree: Path):
    """Benchmark SQL query via DuckDB."""
    from vlmctx.context import Context

    ctx = Context(large_tree)

    result = benchmark(ctx.sql, "SELECT kind, COUNT(*) as n FROM files GROUP BY kind")
    assert result.num_rows > 0


def test_bench_filter(benchmark, large_tree: Path):
    """Benchmark filtering."""
    from vlmctx.context import Context

    ctx = Context(large_tree)

    result = benchmark(ctx.filter, kind="code")
    assert result.num_files > 0
