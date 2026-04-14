"""Benchmarks for Python import time and CLI cold-start overhead."""

from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.slow

# ---------------------------------------------------------------------------
# (a) Import overhead
# ---------------------------------------------------------------------------


def test_bench_import_mm(benchmark):
    """Benchmark `import mm` in a fresh subprocess."""

    def import_mm():
        result = subprocess.run(
            [sys.executable, "-c", "import mm"],
            capture_output=True,
        )
        assert result.returncode == 0

    benchmark(import_mm)


def test_bench_import_mm_context(benchmark):
    """Benchmark `from mm import Context` in a fresh subprocess."""

    def import_context():
        result = subprocess.run(
            [sys.executable, "-c", "from mm import Context"],
            capture_output=True,
        )
        assert result.returncode == 0

    benchmark(import_context)


def test_bench_import_rust_bindings(benchmark):
    """Benchmark `from mm._mm import Scanner` (Rust extension load time)."""

    def import_scanner():
        result = subprocess.run(
            [sys.executable, "-c", "from mm._mm import Scanner"],
            capture_output=True,
        )
        assert result.returncode == 0

    benchmark(import_scanner)


# ---------------------------------------------------------------------------
# (b) CLI cold-start overhead
# ---------------------------------------------------------------------------


def test_bench_cli_help(benchmark):
    """Benchmark `mm --help` (CLI framework + import overhead)."""

    def cli_help():
        result = subprocess.run(["mm", "--help"], capture_output=True)
        assert result.returncode == 0

    benchmark(cli_help)


def test_bench_cli_find_minimal(benchmark, tmp_path):
    """Benchmark `mm find` on a minimal directory (CLI overhead + scan)."""
    d = tmp_path / "minimal"
    d.mkdir()
    (d / "a.txt").write_text("hello")

    def cli_find():
        result = subprocess.run(
            ["mm", "find", str(d), "--format", "json"],
            capture_output=True,
        )
        assert result.returncode == 0

    benchmark(cli_find)


def test_bench_cli_wc_minimal(benchmark, tmp_path):
    """Benchmark `mm wc` on a minimal directory (CLI overhead + scan)."""
    d = tmp_path / "minimal"
    d.mkdir(exist_ok=True)
    (d / "a.txt").write_text("hello")

    def cli_wc():
        result = subprocess.run(
            ["mm", "wc", str(d), "--format", "json"],
            capture_output=True,
        )
        assert result.returncode == 0

    benchmark(cli_wc)
