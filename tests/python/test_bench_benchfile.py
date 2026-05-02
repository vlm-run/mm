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

    def test_module_scope_dataclass_decorates(self, tmp_path: Path):
        """Dataclasses declared at benchfile module scope decorate cleanly.

        Regression: under Python 3.12 the dataclass decorator walks
        ``sys.modules.get(cls.__module__).__dict__`` to resolve string
        annotations. The loader must register the module in
        ``sys.modules`` BEFORE running ``exec_module``; otherwise the
        decorator raises ``AttributeError: 'NoneType' object ...``.
        """
        bf = _write_benchfile(
            tmp_path / "bf.py",
            """
            from __future__ import annotations
            from dataclasses import dataclass, field
            from typing import Any
            from mm.commands.bench_commands import BenchCommand

            @dataclass(frozen=True)
            class Spec:
                model: str
                extra: dict[str, Any] = field(default_factory=dict)

            COMMANDS = [
                BenchCommand(s.model, "demo", f"echo {s.model}")
                for s in [Spec("alpha"), Spec("beta", extra={"k": 1})]
            ]
            """,
        )
        from mm.commands.bench import _load_benchfile

        cmds = _load_benchfile(bf)
        assert [c.name for c in cmds] == ["alpha", "beta"]


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


class TestFilterFlags:
    """`--group` / `--model` / `--command` compose via AND on benchfile rows."""

    @pytest.fixture
    def benchfile(self, tmp_path: Path) -> Path:
        bf = tmp_path / "bf.py"
        bf.write_text(
            dedent(
                """
                from mm.commands.bench_commands import BenchCommand

                COMMANDS = [
                    BenchCommand("alpha-x", "alpha", "echo a", tags={"model": "qwen"}),
                    BenchCommand("alpha-y", "alpha", "echo b", tags={"model": "sam3"}),
                    BenchCommand("beta-x",  "beta",  "echo c", tags={"model": "qwen"}),
                    BenchCommand("beta-y",  "beta",  "echo d", tags={"model": "moondream2"}),
                    BenchCommand("gamma-x", "gamma", "echo e", tags={"model": "sam3"}),
                ]
                """
            )
        )
        return bf

    def _run(self, small_tree: Path, bf: Path, *extra: str) -> dict:
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
                *extra,
            ],
        )
        assert r.exit_code == 0, r.output
        return json.loads(r.stdout)

    def test_group_filter(self, benchfile: Path, small_tree: Path):
        data = self._run(small_tree, benchfile, "--group", "alpha")
        assert {r["name"] for r in data["results"]} == {"alpha-x", "alpha-y"}

    def test_group_filter_short_flag(self, benchfile: Path, small_tree: Path):
        data = self._run(small_tree, benchfile, "-g", "beta")
        assert {r["name"] for r in data["results"]} == {"beta-x", "beta-y"}

    def test_group_filter_case_insensitive(self, benchfile: Path, small_tree: Path):
        data = self._run(small_tree, benchfile, "--group", "ALPHA")
        assert {r["name"] for r in data["results"]} == {"alpha-x", "alpha-y"}

    def test_group_filter_exact_match_only(self, benchfile: Path, small_tree: Path):
        """`--group alpha` must NOT match `alphabet`-style longer groups."""
        bf = small_tree.parent / "bf2.py"
        bf.write_text(
            dedent(
                """
                from mm.commands.bench_commands import BenchCommand
                COMMANDS = [
                    BenchCommand("a", "alpha",    "echo 1"),
                    BenchCommand("b", "alphabet", "echo 2"),
                ]
                """
            )
        )
        data = self._run(small_tree, bf, "--group", "alpha")
        assert {r["name"] for r in data["results"]} == {"a"}

    def test_model_filter_cuts_across_groups(self, benchfile: Path, small_tree: Path):
        data = self._run(small_tree, benchfile, "--model", "qwen")
        assert {r["name"] for r in data["results"]} == {"alpha-x", "beta-x"}
        # And spans both alpha + beta groups.
        assert {r["group"] for r in data["results"]} == {"alpha", "beta"}

    def test_model_filter_case_insensitive(self, benchfile: Path, small_tree: Path):
        data = self._run(small_tree, benchfile, "--model", "QWEN")
        assert {r["name"] for r in data["results"]} == {"alpha-x", "beta-x"}

    def test_group_and_model_compose_via_and(self, benchfile: Path, small_tree: Path):
        data = self._run(small_tree, benchfile, "--group", "alpha", "--model", "sam3")
        assert {r["name"] for r in data["results"]} == {"alpha-y"}

    def test_group_model_command_three_way_compose(self, benchfile: Path, small_tree: Path):
        # alpha group ∩ qwen model ∩ name contains "x" -> alpha-x
        data = self._run(
            small_tree,
            benchfile,
            "--group",
            "alpha",
            "--model",
            "qwen",
            "--command",
            "x",
        )
        assert [r["name"] for r in data["results"]] == ["alpha-x"]

    def test_group_no_match_exits_one(self, benchfile: Path, small_tree: Path):
        r = runner.invoke(
            app,
            ["bench", str(small_tree), "-b", str(benchfile), "--dry-run", "--group", "nope"],
        )
        assert r.exit_code == 1, r.output
        assert "--group 'nope'" in (r.stderr or r.output)

    def test_model_no_match_exits_one(self, benchfile: Path, small_tree: Path):
        r = runner.invoke(
            app,
            ["bench", str(small_tree), "-b", str(benchfile), "--dry-run", "--model", "nope"],
        )
        assert r.exit_code == 1, r.output
        assert "--model 'nope'" in (r.stderr or r.output)

    def test_filters_work_against_default_suite(self, small_tree: Path):
        """`--group metadata` works against the built-in matrix too."""
        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "--dry-run",
                "--format",
                "json",
                "--group",
                "metadata",
            ],
        )
        assert r.exit_code == 0, r.output
        data = json.loads(r.stdout)
        groups = {row["group"] for row in data["results"]}
        assert groups == {"metadata"}, groups


class TestVlmgwBenchfileSmoke:
    """The shipped vlmgw benchfile parses cleanly and dry-runs end-to-end."""

    BENCHFILE = Path(__file__).resolve().parents[2] / "benchmarks" / "vlmgw_bench_commands.py"

    def _load(self):
        """Helper: load the benchfile and return its module."""
        from mm.commands.bench import _load_benchfile

        _load_benchfile(self.BENCHFILE)
        import sys as _sys

        return _sys.modules["_mm_benchfile_vlmgw_bench_commands"]

    def test_dry_run_loads_and_groups_match(self, small_tree: Path):
        assert self.BENCHFILE.exists(), f"missing benchfile: {self.BENCHFILE}"

        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "-b",
                str(self.BENCHFILE),
                "--dry-run",
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0, r.output
        data = json.loads(r.stdout)

        groups: dict[str, int] = {}
        for row in data["results"]:
            groups[row["group"]] = groups.get(row["group"], 0) + 1

        # Exact group counts -- the matrix is fully prescribed.
        assert groups == {
            "noop": 3,
            "model": 27,
            "model+llm": 1,
            "image-res": 3,
            "video-frames": 3,
            "cache": 2,
            "404": 3,
            "validation": 2,
        }, groups

    def test_noop_group_has_ping_and_two_image_resolutions(self):
        """The noop group exists for gateway round-trip cost measurements."""
        mod = self._load()
        noop_cmds = [c for c in mod.COMMANDS if c.group == "noop"]
        names = [c.name for c in noop_cmds]
        assert names == ["noop/ping", "noop/image-512", "noop/image-1024"]

        ping, img512, img1024 = noop_cmds
        # ping has no extra_body, just a --prompt ping.
        assert ping.tags["extra_body"] == ""
        assert "--prompt ping" in ping.cmd_template
        # The image rows pass image_resolution at distinct values via
        # --generate.extra-body and have NO --prompt (the noop endpoint
        # is purely a passthrough).
        assert json.loads(img512.tags["extra_body"]) == {"image_resolution": 512}
        assert json.loads(img1024.tags["extra_body"]) == {"image_resolution": 1024}
        for cmd in (img512, img1024):
            assert "--prompt" not in cmd.cmd_template
            assert cmd.tags["model"] == "noop"

    def test_all_27_canonical_model_variants_present(self):
        """Every model variant from the upstream BenchSpec list is represented.

        Locked-in canonical list -- if upstream adds a variant, this
        test fails until the benchfile is updated. The noop family
        lives in NOOP_SPECS and is checked separately above.
        """
        mod = self._load()
        names = {s.name for s in mod.SPECS}
        expected = {
            "florence2/caption",
            "florence2/ocr",
            "florence2/od",
            "moondream/caption",
            "moondream/detect",
            "moondream/video-caption",
            "qwen/text",
            "qwen/image",
            "qwen/multi-image",
            "qwen/video",
            "rfdetr/detect",
            "rfdetr-seg/segment",
            "vitpose/pose",
            "sam3/segment",
            "sam3/segment_box",
            "sam3/track",
            "dots-ocr/parse_layout",
            "dots-ocr/parse_layout_only",
            "dots-ocr/ocr",
            "dots-ocr/grounding_ocr",
            "paddleocr/ocr",
            "paddleocr/detect",
            "smolvlm/256m-caption",
            "smolvlm2/256m-image",
            "smolvlm2/256m-video",
            "smolvlm2/500m-image",
            "smolvlm2/500m-video",
            "moondream/caption+llm",
        }
        missing = expected - names
        extra = names - expected
        assert not missing, f"missing variants: {sorted(missing)}"
        assert not extra, f"unexpected variants: {sorted(extra)}"

    def test_specs_translate_with_correct_group_and_tags(self):
        """Spec rows land in `model` (or `model+llm` for cross-model pipelines)
        and carry model + extra_body tags."""
        mod = self._load()
        # COMMANDS layout: NOOP_SPECS then SPECS then auxiliary lists.
        offset = len(mod.NOOP_SPECS)
        spec_cmds = mod.COMMANDS[offset : offset + len(mod.SPECS)]
        for spec, cmd in zip(mod.SPECS, spec_cmds, strict=True):
            expected_group = "model+llm" if "llm" in spec.extra_body else "model"
            assert cmd.group == expected_group, (spec.name, cmd.group, expected_group)
            assert cmd.name == spec.name
            assert cmd.tags.get("model") == spec.model
            # extra_body tag is the JSON-rendered final payload
            # (including folded fps/max_frames/video_resolution).
            assert "extra_body" in cmd.tags
            if cmd.tags["extra_body"]:
                assert json.loads(cmd.tags["extra_body"]) == mod._eb_for(spec)

    def test_cross_model_pipeline_routed_to_model_plus_llm(self):
        """Specs declaring `extra_body.llm` go to group=`model+llm`."""
        mod = self._load()
        cross = [s for s in mod.SPECS if "llm" in s.extra_body]
        assert cross, "expected at least one cross-model spec in the matrix"
        for spec in cross:
            cmd = mod._to_command(spec)
            assert cmd.group == "model+llm"
            # And the model tag still names the *primary* (vision) model,
            # not the post-processor.
            assert cmd.tags["model"] == spec.model

    def test_video_specs_fold_extra_body(self):
        mod = self._load()
        qwen_video = next(s for s in mod.SPECS if s.name == "qwen/video")
        cmd = mod._to_command(qwen_video)
        m = re.search(r"--generate\.extra-body\s+'([^']+)'", cmd.cmd_template)
        assert m, cmd.cmd_template
        eb = json.loads(m.group(1))
        assert eb["video_fps"] == 0.4
        assert eb["video_max_frames"] == 8
        assert eb["video_resolution"] == "448x336"


class TestTagColumns:
    """Tag-driven dynamic columns in the bench renderer + JSON output."""

    def _make_benchfile(self, tmp_path: Path) -> Path:
        bf = tmp_path / "bf.py"
        bf.write_text(
            dedent(
                """
                from mm.commands.bench_commands import BenchCommand

                COMMANDS = [
                    BenchCommand(
                        "alpha-row", "alpha", "echo alpha",
                        tags={"model": "model-a", "extra_body": '{"k": 1}'},
                    ),
                    BenchCommand(
                        "beta-row", "beta", "echo beta",
                        tags={"model": "model-b"},
                    ),
                    # Untagged -- should still render with empty tag cells.
                    BenchCommand("gamma-row", "gamma", "echo gamma"),
                ]
                """
            )
        )
        return bf

    def test_tags_surface_in_json(self, tmp_path: Path, small_tree: Path):
        bf = self._make_benchfile(tmp_path)
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
        rows = {row["name"]: row for row in data["results"]}

        assert rows["alpha-row"]["tags"] == {"model": "model-a", "extra_body": '{"k": 1}'}
        assert rows["beta-row"]["tags"] == {"model": "model-b"}
        # Untagged rows must NOT include a tags key (clean JSON).
        assert "tags" not in rows["gamma-row"]

    def test_tag_keys_become_columns_in_first_seen_order(
        self, tmp_path: Path, small_tree: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """`Model` then `Extra Body` columns appear between `Group` and `Command`."""
        bf = self._make_benchfile(tmp_path)
        # Rich pulls width from COLUMNS / the terminal; widen so headers
        # render without ellipsis truncation under CliRunner.
        monkeypatch.setenv("COLUMNS", "240")
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
        # Header line -- locate the column ordering.
        header_line = next(
            line for line in plain.splitlines() if "Group" in line and "Command" in line
        )
        idx = lambda label: header_line.index(label)  # noqa: E731
        assert idx("Group") < idx("Model") < idx("Extra Body") < idx("Command") < idx("Mean")

    def test_helpers_humanize_and_collect(self):
        from mm.commands.bench import BenchResult, _collect_tag_keys, _humanize_tag_key

        results = [
            BenchResult(
                "x",
                "g",
                tags={"model": "m1", "extra_body": "eb1"},
                is_dry_run=True,
            ),
            BenchResult(
                "y",
                "g",
                tags={"model": "m2", "image_resolution": "low"},
                is_dry_run=True,
            ),
            BenchResult("z", "g", tags={}, is_dry_run=True),
        ]
        # First-seen order preserved across rows.
        assert _collect_tag_keys(results) == ["model", "extra_body", "image_resolution"]
        assert _humanize_tag_key("extra_body") == "Extra Body"
        assert _humanize_tag_key("model") == "Model"
        assert _humanize_tag_key("video-fps") == "Video Fps"

    def test_default_suite_unaffected_when_no_tags(self, small_tree: Path):
        """Built-in matrix has no tags -> no extra columns rendered."""
        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "--dry-run",
                "--format",
                "rich",
            ],
        )
        assert r.exit_code == 0, r.output
        plain = _strip_ansi(r.stdout)
        header_line = next(
            line for line in plain.splitlines() if "Group" in line and "Command" in line
        )
        # `Model` and `Extra Body` are tag-driven; without tags they
        # must not appear in the table header.
        assert "Model" not in header_line
        assert "Extra Body" not in header_line
