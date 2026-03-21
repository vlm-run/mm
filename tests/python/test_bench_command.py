"""Tests for the vlmctx bench subcommand."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from vlmctx.cli import app

runner = CliRunner()


class TestBenchCommand:
    """Tests for vlmctx bench."""

    def test_exit_zero(self, small_tree: Path):
        """Bench runs successfully on a small directory."""
        r = runner.invoke(app, ["bench", str(small_tree), "--rounds", "2", "--warmup", "0"])
        assert r.exit_code == 0, f"bench failed: {r.output}"

    def test_json_output_structure(self, small_tree: Path):
        """JSON output has expected top-level keys and result structure."""
        r = runner.invoke(app, [
            "bench", str(small_tree),
            "--rounds", "2", "--warmup", "0",
            "--format", "json",
        ])
        assert r.exit_code == 0, f"bench failed: {r.output}"
        data = json.loads(r.output)

        # Top-level keys
        assert "directory" in data
        assert "files" in data
        assert "total_bytes" in data
        assert "rounds" in data
        assert "results" in data
        assert isinstance(data["results"], list)
        assert len(data["results"]) > 0

        # Each result has required fields
        for result in data["results"]:
            assert "name" in result
            assert "group" in result
            if not result.get("skipped"):
                assert "mean_ms" in result
                assert "std_ms" in result
                assert "min_ms" in result
                assert "max_ms" in result
                assert "timings_ms" in result
                assert isinstance(result["timings_ms"], list)

    def test_json_rounds_match(self, small_tree: Path):
        """Number of timings matches requested rounds."""
        rounds = 3
        r = runner.invoke(app, [
            "bench", str(small_tree),
            "--rounds", str(rounds), "--warmup", "0",
            "--format", "json",
        ])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["rounds"] == rounds
        for result in data["results"]:
            if not result.get("skipped"):
                assert len(result["timings_ms"]) == rounds

    def test_verbose_output(self, small_tree: Path):
        """Verbose mode runs without error."""
        r = runner.invoke(app, [
            "bench", str(small_tree),
            "--rounds", "2", "--warmup", "0",
            "--verbose",
        ])
        assert r.exit_code == 0, f"bench --verbose failed: {r.output}"

    def test_skips_missing_file_types(self, tmp_path: Path):
        """L1 benchmarks for missing types are skipped gracefully."""
        # Directory with only code files — no images, videos, or PDFs
        (tmp_path / "main.py").write_text("print('hello')\n")
        (tmp_path / "lib.py").write_text("def add(a, b): return a + b\n")

        r = runner.invoke(app, [
            "bench", str(tmp_path),
            "--rounds", "2", "--warmup", "0",
            "--format", "json",
        ])
        assert r.exit_code == 0
        data = json.loads(r.output)

        skipped_names = {
            result["name"]
            for result in data["results"]
            if result.get("skipped")
        }
        assert "cat image" in skipped_names
        assert "cat video" in skipped_names
        assert "cat pdf" in skipped_names

    def test_empty_directory(self, tmp_path: Path):
        """Bench handles empty directory gracefully."""
        r = runner.invoke(app, [
            "bench", str(tmp_path),
            "--rounds", "2", "--warmup", "0",
            "--format", "json",
        ])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["files"] == 0

    def test_l0_benchmarks_always_present(self, small_tree: Path):
        """L0 benchmarks run regardless of file types present."""
        r = runner.invoke(app, [
            "bench", str(small_tree),
            "--rounds", "2", "--warmup", "0",
            "--format", "json",
        ])
        assert r.exit_code == 0
        data = json.loads(r.output)

        l0_names = {
            result["name"]
            for result in data["results"]
            if result["group"] == "L0" and not result.get("skipped")
        }
        assert "find ." in l0_names
        assert "ls ." in l0_names
        assert "wc ." in l0_names
        assert "sql GROUP BY" in l0_names
        assert "find --kind image" in l0_names

    def test_timings_are_positive(self, small_tree: Path):
        """All timings should be positive numbers."""
        r = runner.invoke(app, [
            "bench", str(small_tree),
            "--rounds", "2", "--warmup", "0",
            "--format", "json",
        ])
        assert r.exit_code == 0
        data = json.loads(r.output)
        for result in data["results"]:
            if not result.get("skipped"):
                assert result["mean_ms"] > 0
                assert result["min_ms"] > 0
                assert all(t > 0 for t in result["timings_ms"])

    def test_tsv_output(self, small_tree: Path):
        """TSV output produces tab-separated rows."""
        r = runner.invoke(app, [
            "bench", str(small_tree),
            "--rounds", "2", "--warmup", "0",
            "--format", "tsv",
        ])
        assert r.exit_code == 0
        lines = r.output.strip().splitlines()
        assert len(lines) >= 2  # header + at least 1 data row
        header = lines[0].split("\t")
        assert "group" in header
        assert "name" in header
        assert "mean_ms" in header


class TestBenchResult:
    """Tests for BenchResult dataclass."""

    def test_properties(self):
        from vlmctx.commands.bench import BenchResult

        r = BenchResult(
            name="test",
            group="L0",
            timings_ms=[10.0, 12.0, 11.0, 13.0, 9.0],
            files_count=100,
            total_bytes=1024 * 1024,
        )
        assert r.mean_ms == 11.0
        assert r.min_ms == 9.0
        assert r.max_ms == 13.0
        assert r.median_ms == 11.0
        assert r.std_ms > 0
        assert r.files_per_sec > 0
        assert r.mb_per_sec > 0

    def test_skipped_result(self):
        from vlmctx.commands.bench import BenchResult

        r = BenchResult(name="test", group="L1", skipped=True, skip_reason="no files")
        d = r.to_dict()
        assert d["skipped"] is True
        assert d["skip_reason"] == "no files"
        assert "mean_ms" not in d

    def test_to_dict(self):
        from vlmctx.commands.bench import BenchResult

        r = BenchResult(
            name="find .",
            group="L0",
            timings_ms=[5.0, 6.0, 5.5],
            files_count=50,
            total_bytes=1000,
        )
        d = r.to_dict()
        assert d["name"] == "find ."
        assert d["group"] == "L0"
        assert d["mean_ms"] > 0
        assert len(d["timings_ms"]) == 3


class TestSparkline:
    """Tests for sparkline rendering."""

    def test_basic(self):
        from vlmctx.commands.bench import _sparkline

        result = _sparkline([1.0, 2.0, 3.0, 4.0, 5.0])
        assert len(result) == 5
        assert result[0] == "▁"
        assert result[-1] == "█"

    def test_empty(self):
        from vlmctx.commands.bench import _sparkline

        assert _sparkline([]) == ""

    def test_constant(self):
        from vlmctx.commands.bench import _sparkline

        result = _sparkline([5.0, 5.0, 5.0])
        assert len(result) == 3
