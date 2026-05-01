"""Tests for the mm bench subcommand."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mm.cli import app
from typer.testing import CliRunner

runner = CliRunner()


@pytest.mark.slow
class TestBenchCommand:
    """Tests for mm bench."""

    def test_exit_zero(self, small_tree: Path):
        """Bench runs successfully on a small directory."""
        r = runner.invoke(app, ["bench", str(small_tree), "--rounds", "2", "--warmup", "0"])
        assert r.exit_code == 0, f"bench failed: {r.output}"

    def test_json_output_structure(self, small_tree: Path):
        """JSON output has expected top-level keys and result structure."""
        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "--rounds",
                "2",
                "--warmup",
                "0",
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0, f"bench failed: {r.output}"
        assert "CPU" not in r.stdout, "Host-info should not be in bench stdout"
        data = json.loads(r.stdout)

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
        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "--rounds",
                str(rounds),
                "--warmup",
                "0",
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0
        data = json.loads(r.stdout)
        assert data["rounds"] == rounds
        for result in data["results"]:
            if not result.get("skipped"):
                assert len(result["timings_ms"]) == rounds

    def test_mode_filter(self, small_tree: Path):
        """Mode filter runs without error."""
        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "--rounds",
                "2",
                "--warmup",
                "0",
                "--mode",
                "fast",
            ],
        )
        assert r.exit_code == 0, f"bench --mode fast failed: {r.output}"
        # --mode fast skips the accurate group.
        r2 = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "--rounds",
                "2",
                "--warmup",
                "0",
                "--mode",
                "fast",
                "--format",
                "json",
            ],
        )
        assert r2.exit_code == 0
        data = json.loads(r2.stdout)
        assert not any(res["group"] == "accurate" for res in data["results"])

    def test_skips_missing_file_types(self, tmp_path: Path):
        """Fast-group benchmarks for missing types are skipped gracefully."""
        # Directory with only code files — no images, videos, or PDFs
        (tmp_path / "main.py").write_text("print('hello')\n")
        (tmp_path / "lib.py").write_text("def add(a, b): return a + b\n")

        r = runner.invoke(
            app,
            [
                "bench",
                str(tmp_path),
                "--rounds",
                "2",
                "--warmup",
                "0",
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0
        data = json.loads(r.stdout)

        skipped = {
            (result["name"], result["group"]) for result in data["results"] if result.get("skipped")
        }
        assert ("mm cat <image>", "fast") in skipped
        assert ("mm cat <video>", "fast") in skipped
        assert ("mm cat <pdf>", "fast") in skipped

    def test_empty_directory(self, tmp_path: Path):
        """Bench handles empty directory gracefully."""
        r = runner.invoke(
            app,
            [
                "bench",
                str(tmp_path),
                "--rounds",
                "2",
                "--warmup",
                "0",
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0
        data = json.loads(r.stdout)
        assert data["files"] == 0

    def test_metadata_benchmarks_always_present(self, small_tree: Path):
        """Metadata benchmarks run regardless of file types present."""
        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "--rounds",
                "2",
                "--warmup",
                "0",
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0
        data = json.loads(r.stdout)

        metadata_names = {
            result["name"]
            for result in data["results"]
            if result["group"] == "metadata" and not result.get("skipped")
        }
        assert "mm find ." in metadata_names
        assert "mm find . (table)" in metadata_names
        assert "mm wc ." in metadata_names
        assert "mm sql 'GROUP BY kind'" in metadata_names
        assert "mm find --kind image" in metadata_names

    def test_timings_are_positive(self, small_tree: Path):
        """All timings should be positive numbers."""
        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "--rounds",
                "2",
                "--warmup",
                "0",
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0
        data = json.loads(r.stdout)
        for result in data["results"]:
            if not result.get("skipped"):
                assert result["mean_ms"] > 0
                assert result["min_ms"] > 0
                assert all(t > 0 for t in result["timings_ms"])

    def test_tsv_output(self, small_tree: Path):
        """TSV output produces tab-separated rows."""
        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "--rounds",
                "2",
                "--warmup",
                "0",
                "--format",
                "tsv",
            ],
        )
        assert r.exit_code == 0
        lines = r.stdout.strip().splitlines()
        assert len(lines) >= 2  # header + at least 1 data row
        header = lines[0].split("\t")
        assert "group" in header
        assert "name" in header
        assert "mean_ms" in header


class TestBenchResult:
    """Tests for BenchResult dataclass."""

    def test_properties(self):
        from mm.commands.bench import BenchResult

        r = BenchResult(
            name="test",
            group="metadata",
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
        from mm.commands.bench import BenchResult

        r = BenchResult(name="test", group="fast", skipped=True, skip_reason="no files")
        d = r.to_dict()
        assert d["skipped"] is True
        assert d["skip_reason"] == "no files"
        assert "mean_ms" not in d

    def test_to_dict(self):
        from mm.commands.bench import BenchResult

        r = BenchResult(
            name="find .",
            group="metadata",
            timings_ms=[5.0, 6.0, 5.5],
            files_count=50,
            total_bytes=1000,
        )
        d = r.to_dict()
        assert d["name"] == "find ."
        assert d["group"] == "metadata"
        assert d["mean_ms"] > 0
        assert len(d["timings_ms"]) == 3

    def test_uncompressed_bits_uses_pixel_bits_when_set(self):
        """media_pixel_bits overrides the fallback to total_bytes*8."""
        from mm.commands.bench import BenchResult

        r = BenchResult(
            name="test",
            group="fast",
            timings_ms=[100.0],
            files_count=1,
            total_bytes=1024,
            media_pixel_bits=7_372_800.0,  # e.g. 640*480*24
        )
        assert r.uncompressed_bits == 7_372_800.0

    def test_uncompressed_bits_falls_back_to_bytes(self):
        """Without pixel_bits, throughput uses total_bytes * 8."""
        from mm.commands.bench import BenchResult

        r = BenchResult(
            name="test",
            group="fast",
            timings_ms=[100.0],
            files_count=1,
            total_bytes=1024,
        )
        assert r.uncompressed_bits == 8192.0


class TestBenchCommands:
    """Tests for bench_commands registry."""

    def test_all_commands_non_empty(self):
        from mm.commands.bench_commands import (
            ACCURATE_COMMANDS,
            ALL_COMMANDS,
            FAST_COMMANDS,
            METADATA_COMMANDS,
            OVERHEAD_COMMANDS,
        )

        assert len(ALL_COMMANDS) > 0
        assert len(OVERHEAD_COMMANDS) > 0
        assert len(METADATA_COMMANDS) > 0
        assert len(FAST_COMMANDS) > 0
        assert len(ACCURATE_COMMANDS) > 0
        assert len(ALL_COMMANDS) == (
            len(OVERHEAD_COMMANDS)
            + len(METADATA_COMMANDS)
            + len(FAST_COMMANDS)
            + len(ACCURATE_COMMANDS)
        )

    def test_command_has_required_fields(self):
        from mm.commands.bench_commands import ALL_COMMANDS

        for cmd in ALL_COMMANDS:
            assert cmd.name
            assert cmd.group in ("overhead", "meta", "fast", "accurate")
            assert cmd.cmd_template

    def test_metata_group_includes_cat_meta_benchmarks(self):
        """The metadata group must include `cat --mode metadata` benchmarks alongside find/wc/sql/grep."""
        from mm.commands.bench_commands import METADATA_COMMANDS

        cat_meta_cmds = [c for c in METADATA_COMMANDS if "mm cat" in c.cmd_template]
        assert len(cat_meta_cmds) > 0
        for c in cat_meta_cmds:
            assert "--mode metadata" in c.cmd_template, (
                f"cat command in META_COMMANDS missing --mode metadata: {c.cmd_template}"
            )
            assert c.group == "metadata"

    def test_accurate_group_is_accurate_mode_only(self):
        """Accurate group contains only --mode accurate commands."""
        from mm.commands.bench_commands import ACCURATE_COMMANDS

        assert len(ACCURATE_COMMANDS) > 0
        for cmd in ACCURATE_COMMANDS:
            assert "--mode accurate" in cmd.cmd_template, (
                f"accurate group should only contain --mode accurate: {cmd.cmd_template}"
            )


class TestFmtMs:
    """Tests for _fmt_ms formatting."""

    def test_seconds(self):
        from mm.commands.bench import _fmt_ms

        assert _fmt_ms(1500.0) == "1.50s"

    def test_milliseconds(self):
        from mm.commands.bench import _fmt_ms

        assert _fmt_ms(15.3) == "15.3ms"

    def test_sub_10ms(self):
        from mm.commands.bench import _fmt_ms

        assert _fmt_ms(5.12) == "5.12ms"
