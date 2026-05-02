"""Tests for `mm bench --bench-file` (external benchfiles) and `--dry-run`."""

from __future__ import annotations

import json
import re
from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

import pytest
import typer
from mm.cli import app
from typer.testing import CliRunner

runner = CliRunner()


# ── helpers ───────────────────────────────────────────────────────────


def _strip_ansi(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[mK]", "", s)


def _write_benchfile(path: Path, body: str) -> Path:
    path.write_text(dedent(body))
    return path


# ── _load_benchfile loader ────────────────────────────────────────────


class TestLoadBenchfile:
    def test_loads_commands_attr(self, tmp_path: Path):
        bf = _write_benchfile(
            tmp_path / "bf.py",
            """
            from mm.commands.bench_commands import BenchCommand

            COMMANDS = [
                BenchCommand("alpha", "demo", "echo alpha"),
                BenchCommand("beta",  "demo", "echo beta"),
            ]
            """,
        )
        from mm.commands.bench import _load_benchfile

        cmds = _load_benchfile(bf)
        assert [c.name for c in cmds] == ["alpha", "beta"]
        assert all(c.group == "demo" for c in cmds)

    def test_loads_factory_when_present(self, tmp_path: Path):
        """A `commands(files)` factory takes precedence over a static COMMANDS list."""
        bf = _write_benchfile(
            tmp_path / "bf.py",
            """
            from mm.commands.bench_commands import BenchCommand

            COMMANDS = [BenchCommand("static", "demo", "echo static")]

            def commands(files):
                return [BenchCommand(f"factory ({len(files)})", "demo", "echo factory")]
            """,
        )
        from mm.commands.bench import _load_benchfile

        cmds = _load_benchfile(bf, files=[1, 2, 3])
        assert len(cmds) == 1
        assert cmds[0].name == "factory (3)"

    def test_missing_file_exits(self, tmp_path: Path):
        from mm.commands.bench import _load_benchfile

        with pytest.raises(typer.Exit) as ei:
            _load_benchfile(tmp_path / "does-not-exist.py")
        assert ei.value.exit_code == 1

    def test_non_py_suffix_exits(self, tmp_path: Path):
        bf = tmp_path / "bf.yaml"
        bf.write_text("commands: []\n")
        from mm.commands.bench import _load_benchfile

        with pytest.raises(typer.Exit) as ei:
            _load_benchfile(bf)
        assert ei.value.exit_code == 1

    def test_module_without_commands_exits(self, tmp_path: Path):
        bf = _write_benchfile(tmp_path / "bf.py", "x = 1\n")
        from mm.commands.bench import _load_benchfile

        with pytest.raises(typer.Exit) as ei:
            _load_benchfile(bf)
        assert ei.value.exit_code == 1

    def test_invalid_entry_exits(self, tmp_path: Path):
        bf = _write_benchfile(
            tmp_path / "bf.py",
            """
            from mm.commands.bench_commands import BenchCommand
            COMMANDS = [BenchCommand("ok", "demo", "echo ok"), {"bogus": True}]
            """,
        )
        from mm.commands.bench import _load_benchfile

        with pytest.raises(typer.Exit) as ei:
            _load_benchfile(bf)
        assert ei.value.exit_code == 1

    def test_factory_returning_non_list_exits(self, tmp_path: Path):
        bf = _write_benchfile(
            tmp_path / "bf.py",
            """
            def commands(files):
                return None
            """,
        )
        from mm.commands.bench import _load_benchfile

        with pytest.raises(typer.Exit) as ei:
            _load_benchfile(bf)
        assert ei.value.exit_code == 1


# ── --bench-file CLI integration ─────────────────────────────────────


class TestBenchFileCli:
    def test_replaces_builtins(self, tmp_path: Path, small_tree: Path):
        """A user-supplied benchfile fully replaces the built-in command set."""
        bf = _write_benchfile(
            tmp_path / "bf.py",
            """
            from mm.commands.bench_commands import BenchCommand
            COMMANDS = [BenchCommand("only-row", "demo", "echo hi")]
            """,
        )
        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "--bench-file",
                str(bf),
                "--dry-run",
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0, r.output
        data = json.loads(r.stdout)
        names = [row["name"] for row in data["results"]]
        # Built-ins like "mm find ." / "mm wc ." must NOT appear.
        assert names == ["only-row"]

    def test_short_flag_alias(self, tmp_path: Path, small_tree: Path):
        bf = _write_benchfile(
            tmp_path / "bf.py",
            """
            from mm.commands.bench_commands import BenchCommand
            COMMANDS = [BenchCommand("alpha", "demo", "echo hi")]
            """,
        )
        r = runner.invoke(
            app,
            ["bench", str(small_tree), "-b", str(bf), "--dry-run", "--format", "json"],
        )
        assert r.exit_code == 0, r.output
        data = json.loads(r.stdout)
        assert [row["name"] for row in data["results"]] == ["alpha"]

    def test_mode_ignored_with_bench_file(self, tmp_path: Path, small_tree: Path):
        """`--mode` emits a one-line note on stderr but does not change the loaded commands."""
        bf = _write_benchfile(
            tmp_path / "bf.py",
            """
            from mm.commands.bench_commands import BenchCommand
            COMMANDS = [BenchCommand("alpha", "demo", "echo hi")]
            """,
        )
        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "-b",
                str(bf),
                "--mode",
                "fast",
                "--dry-run",
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0, r.output
        # Note about --mode being ignored should land on stderr.
        assert "ignored" in (r.stderr or "").lower() or "ignored" in (r.output or "").lower()
        data = json.loads(r.stdout)
        assert [row["name"] for row in data["results"]] == ["alpha"]

    def test_bad_benchfile_exits_one(self, tmp_path: Path, small_tree: Path):
        bf = tmp_path / "bf.py"
        bf.write_text("this is not python !@#\n")
        r = runner.invoke(
            app,
            ["bench", str(small_tree), "-b", str(bf), "--dry-run"],
        )
        assert r.exit_code == 1, r.output


# ── --dry-run behaviour ──────────────────────────────────────────────


class TestDryRun:
    def test_no_subprocess_invocations(self, tmp_path: Path, small_tree: Path):
        """`--dry-run` must not invoke the timing subprocess loop."""
        bf = _write_benchfile(
            tmp_path / "bf.py",
            """
            from mm.commands.bench_commands import BenchCommand
            COMMANDS = [
                BenchCommand("a", "demo", "echo a"),
                BenchCommand("b", "demo", "echo b"),
                BenchCommand("c", "demo", "echo c"),
            ]
            """,
        )
        with patch("mm.commands.bench._time_cmd") as time_cmd:
            r = runner.invoke(
                app,
                [
                    "bench",
                    str(small_tree),
                    "-b",
                    str(bf),
                    "--dry-run",
                    "--format",
                    "json",
                ],
            )
        assert r.exit_code == 0, r.output
        time_cmd.assert_not_called()

    def test_json_emits_argv_and_dry_run_flag(self, tmp_path: Path, small_tree: Path):
        bf = _write_benchfile(
            tmp_path / "bf.py",
            """
            from mm.commands.bench_commands import BenchCommand
            COMMANDS = [BenchCommand("alpha", "demo", "echo alpha")]
            """,
        )
        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "-b",
                str(bf),
                "--dry-run",
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0, r.output
        data = json.loads(r.stdout)
        assert data["dry_run"] is True
        assert len(data["results"]) == 1
        row = data["results"][0]
        assert row == {
            "name": "alpha",
            "group": "demo",
            "dry_run": True,
            "argv": ["echo alpha"],
            "files_count": 0,
            "total_bytes": 0,
        }

    def test_rich_renders_placeholders_and_caption(self, tmp_path: Path, small_tree: Path):
        bf = _write_benchfile(
            tmp_path / "bf.py",
            """
            from mm.commands.bench_commands import BenchCommand
            COMMANDS = [BenchCommand("alpha", "demo", "echo alpha")]
            """,
        )
        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "-b",
                str(bf),
                "--dry-run",
                "--format",
                "rich",
            ],
        )
        assert r.exit_code == 0, r.output
        plain = _strip_ansi(r.stdout)
        # Caption announces dry-run mode.
        assert "(dry run" in plain
        # The single row should not contain any zero-valued metric like "0.00ms".
        assert "0.00ms" not in plain
        assert "alpha" in plain

    def test_default_path_dry_run_works(self, small_tree: Path):
        """`--dry-run` without `--bench-file` still works against the built-in matrix."""
        with patch("mm.commands.bench._time_cmd") as time_cmd:
            r = runner.invoke(
                app,
                [
                    "bench",
                    str(small_tree),
                    "--dry-run",
                    "--format",
                    "json",
                ],
            )
        assert r.exit_code == 0, r.output
        time_cmd.assert_not_called()
        data = json.loads(r.stdout)
        assert data["dry_run"] is True
        # Built-in suite should produce some rows even on a tiny tree.
        assert len(data["results"]) > 0
        for row in data["results"]:
            assert row.get("dry_run") or row.get("skipped"), row


# ── vlmgw benchfile smoke ────────────────────────────────────────────


class TestVlmgwBenchfileSmoke:
    """The shipped vlmgw benchfile parses cleanly and dry-runs end-to-end."""

    def test_dry_run_loads(self, small_tree: Path):
        bf = Path(__file__).resolve().parents[2] / "benchmarks" / "vlmgw_bench_commands.py"
        assert bf.exists(), f"missing benchfile: {bf}"

        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "-b",
                str(bf),
                "--dry-run",
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0, r.output
        data = json.loads(r.stdout)
        groups = {row["group"] for row in data["results"]}
        # All seven groups from the plan must be represented.
        assert {
            "A. image-prompt",
            "B. model-alias",
            "C. image-extra-body",
            "D. video-frame-sampling",
            "E. cache",
            "F. unavailable",
            "G. validation",
        }.issubset(groups)
