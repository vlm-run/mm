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
        # ``moondream/video-caption`` was dropped (the gateway no
        # longer supports moondream2 video) and ``qwen/multi-image``
        # was folded back into SPECS as a regular ``mm cat <f1> <f2>``
        # row, so SPECS now contributes 28 ``model`` + 1 ``model+llm``.
        assert groups == {
            "noop": 3,
            "model": 28,
            "model+llm": 1,
            "image-res": 3,
            "video-frames": 3,
            "cache": 2,
            "404": 3,
            "validation": 2,
        }, groups

    def test_noop_group_has_ping_and_two_image_resolutions(self):
        """The noop group exists for gateway round-trip cost measurements.

        ``noop/image-*`` rows must use **client-side**
        ``--encode.strategy_opts max_width=N`` (PIL/Rust resize before
        upload), NOT a server-side ``image_resolution`` extra-body
        knob. The noop gateway endpoint doesn't transform the image at
        all, so the only knob that actually changes upload bytes is the
        client-side encoder.

        All three rows are currently ``disabled=True`` because the
        ``vlm-run/noop`` model isn't deployed; the row layout still
        has to be correct so re-enabling is a one-flag flip.
        """
        mod = self._load()
        noop_cmds = [c for c in mod.COMMANDS if c.group == "noop"]
        names = [c.name for c in noop_cmds]
        assert names == ["noop/ping", "noop/image-512", "noop/image-1024"]

        ping, img512, img1024 = noop_cmds
        # ping has no extra_body and no encoder flag -- just a --prompt.
        assert "--prompt ping" in ping.cmd_template
        assert "--encode.strategy_opts" not in ping.cmd_template
        assert "--generate.extra-body" not in ping.cmd_template

        # The image rows pass max_width via `--encode.strategy_opts`
        # (client-side downsample) and NEVER via `--generate.extra-body`.
        assert "--encode.strategy_opts max_width=512" in img512.cmd_template
        assert "--encode.strategy_opts max_width=1024" in img1024.cmd_template
        for cmd in (img512, img1024):
            assert "--generate.extra-body" not in cmd.cmd_template
            assert "image_resolution" not in cmd.cmd_template
            # The noop endpoint is a pure passthrough -- no prompt.
            assert "--prompt" not in cmd.cmd_template

        # Model tag uses the canonical <org>/<model-name> form.
        for cmd in noop_cmds:
            assert cmd.tags["model"] == "vlm-run/noop"

        # Currently disabled -- vlm-run/noop isn't deployed.
        for cmd in noop_cmds:
            assert cmd.disabled is True, cmd.name

    def test_all_canonical_model_variants_present(self):
        """Every model variant from the upstream BenchSpec list is represented.

        Locked-in canonical list -- if upstream adds a variant, this
        test fails until the benchfile is updated. The noop family
        lives in NOOP_SPECS and is checked separately above.

        ``moondream/video-caption`` is intentionally absent: moondream2
        no longer accepts multi-frame video on the gateway, so the
        spec was removed entirely (rather than disabled) until that
        capability returns. ``qwen/multi-image`` lives in SPECS (not
        a separate hand-authored list) and resolves to a regular
        ``mm cat <f1> <f2>`` invocation -- two sequential one-image
        chats, not a single multi-image API call.
        """
        mod = self._load()
        names = {s.name for s in mod.SPECS}
        expected = {
            "florence2/caption",
            "florence2/ocr",
            "florence2/od",
            "moondream/caption",
            "moondream/detect",
            "qwen/text",
            "qwen/image",
            "qwen/video",
            "qwen/multi-image",
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
            "gliner/extract_entities",
            "gliner/classify_text",
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

    def test_disabled_specs_match_known_failures(self):
        """The disabled set matches the known-broken upstream surface.

        Locked in so re-enabling a row requires an explicit decision
        (deployment fix verified, capability restored, etc) rather
        than someone silently flipping the flag.
        """
        mod = self._load()
        disabled_specs = {s.name for s in mod.SPECS if s.disabled}
        assert disabled_specs == {
            # qwen/text -- "What is 2+2?" prompt isn't representative
            # of any real usage pattern.
            "qwen/text",
            # SAM3 deployment unavailable (failed to deploy) +
            # multi-image rejection on sam3/track.
            "sam3/segment",
            "sam3/segment_box",
            "sam3/track",
            # dots.ocr deployment unavailable.
            "dots-ocr/parse_layout",
            "dots-ocr/parse_layout_only",
            "dots-ocr/ocr",
            "dots-ocr/grounding_ocr",
            # paddleocr -- gateway returns Internal Server Error.
            "paddleocr/ocr",
            "paddleocr/detect",
            # gliner is text-only but mm cat always attaches an image.
            "gliner/extract_entities",
            "gliner/classify_text",
            # smolvlm2-video accepts at most 1 image_url part, which
            # is incompatible with multi-frame video sampling.
            "smolvlm2/256m-video",
            "smolvlm2/500m-video",
            # moondream/caption+llm -- Internal Server Error.
            "moondream/caption+llm",
        }, sorted(disabled_specs)

    def test_qwen_multi_image_uses_regular_mm_cat(self):
        """``qwen/multi-image`` resolves to ``mm cat <f1> <f2>`` (not a helper script).

        Earlier iterations routed multi-image through a Python helper
        that built a single chat-completion with multiple image_url
        parts; that's been reverted to the standard ``mm cat`` shape
        (which iterates client-side, firing N independent requests).
        Pin the new shape so it can't silently regress.
        """
        mod = self._load()
        spec = next(s for s in mod.SPECS if s.name == "qwen/multi-image")
        assert spec.image is True
        assert spec.num_images == 2
        cmd = next(c for c in mod.COMMANDS if c.name == "qwen/multi-image")
        assert "{files}" in cmd.cmd_template
        assert cmd.cmd_template.startswith("mm --profile vlmgw cat")
        # No helper-script invocation.
        assert "_multi_image_call" not in cmd.cmd_template
        assert "python" not in cmd.cmd_template.split()
        assert cmd.batch == 2
        assert cmd.requires_kind == "image"

    def test_pinned_file_rows_bypass_file_placeholder(self):
        """OCR / pose specs hard-code the input path (no ``{file}`` token).

        The harness's bench-dir scan is bypassed for these rows so
        the model gets a domain-appropriate image (text scan for OCR,
        tennis player for pose) regardless of what's in the bench
        target directory.
        """
        mod = self._load()
        # Domain pin spot-check: florence2/ocr / dots-ocr/* /
        # paddleocr/* should all reference the OCR image; vitpose/pose
        # should reference the tennis image.
        ocr_image_basename = "image-ocr.jpg"
        pose_image_basename = "2.1-detect-count-tennis.jpg"

        ocr_specs = [
            s for s in mod.SPECS if s.name.startswith(("florence2/ocr", "dots-ocr/", "paddleocr/"))
        ]
        assert ocr_specs, "expected at least one OCR spec"
        for spec in ocr_specs:
            assert spec.pinned_file is not None, spec.name
            assert spec.pinned_file.name == ocr_image_basename, (spec.name, spec.pinned_file)

        pose_spec = next(s for s in mod.SPECS if s.name == "vitpose/pose")
        assert pose_spec.pinned_file is not None
        assert pose_spec.pinned_file.name == pose_image_basename

        # Resolved cmd_template carries the absolute path verbatim
        # (no ``{file}`` placeholder, no ``{files}``).
        for spec in [*ocr_specs, pose_spec]:
            cmd = next(c for c in mod.COMMANDS if c.name == spec.name)
            assert "{file}" not in cmd.cmd_template, cmd.cmd_template
            assert "{files}" not in cmd.cmd_template, cmd.cmd_template
            assert str(spec.pinned_file) in cmd.cmd_template, cmd.cmd_template
            # ``requires_kind`` is None so the harness doesn't try to
            # pick a file from the bench dir for this row.
            assert cmd.requires_kind is None, (spec.name, cmd.requires_kind)

    def test_specs_translate_with_correct_group_and_tags(self):
        """Spec rows land in `model` (or `model+llm` for cross-model pipelines)
        and carry only the `model` tag.

        ``extra_body`` is intentionally NOT a tag column -- it's
        inlined into the resolved Command cell instead, so tag
        metadata stays compact.
        """
        mod = self._load()
        # COMMANDS layout: NOOP_SPECS then SPECS then auxiliary lists.
        offset = len(mod.NOOP_SPECS)
        spec_cmds = mod.COMMANDS[offset : offset + len(mod.SPECS)]
        for spec, cmd in zip(mod.SPECS, spec_cmds, strict=True):
            expected_group = "model+llm" if "llm" in spec.extra_body else "model"
            assert cmd.group == expected_group, (spec.name, cmd.group, expected_group)
            assert cmd.name == spec.name
            # Only `model` is surfaced as a tag column.
            assert set(cmd.tags) == {"model"}, cmd.tags
            assert cmd.tags["model"] == spec.model
            # Every model name must follow the <org>/<model-name>
            # convention -- enforced uniformly so the Model column
            # is unambiguous across providers.
            assert "/" in cmd.tags["model"], (spec.name, cmd.tags["model"])

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
            # Cross-model pipelines reference the post-processor via
            # extra_body.llm using the same <org>/<name> convention.
            assert "/" in spec.extra_body["llm"], spec.extra_body["llm"]

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

    def test_image_res_uses_client_side_encoder_resize(self):
        """`image-res` rows downsample with `--encode.strategy_opts max_width=N`.

        The previous incarnation of this sweep passed
        ``image_resolution`` via ``--generate.extra-body`` -- a
        server-side knob -- which is wrong: the gateway is OpenAI-
        compatible and image resize is supposed to happen client-side,
        in the encoder, BEFORE the bytes hit the wire. This test pins
        the correct mechanism so the sweep can't silently regress.
        """
        mod = self._load()
        rows = [c for c in mod.COMMANDS if c.group == "image-res"]
        assert len(rows) == 3
        assert {c.name for c in rows} == {
            "qwen/image-512",
            "qwen/image-1024",
            "qwen/image-1536",
        }
        for cmd in rows:
            assert "--encode.strategy_opts max_width=" in cmd.cmd_template
            # Server-side image_resolution must NOT appear in the
            # resolved command. Anywhere.
            assert "image_resolution" not in cmd.cmd_template
            assert "--generate.extra-body" not in cmd.cmd_template

    def test_every_command_has_org_prefixed_model_tag(self):
        """Every non-validation row uses an ``<org>/<model-name>`` model tag.

        Validation rows pin ``(default)`` because the row exercises
        argument-parsing failures before the model is even looked up;
        every other row must follow the namespaced convention so the
        Model column is uniformly resolvable.
        """
        mod = self._load()
        for cmd in mod.COMMANDS:
            if cmd.group == "validation":
                continue
            assert cmd.tags.get("model"), cmd.name
            assert "/" in cmd.tags["model"], (cmd.name, cmd.tags["model"])


class TestColumnsAndCommandCell:
    """Layout: ``Group | Model | Base Command | Extra Args | <metrics>``.

    ``Profile`` and ``Mode`` are intentionally NOT separate columns:
    profile is constant across a benchfile run (so showing it on every
    row is noise), and mode is part of the base command itself. The
    ``Command`` cell is split into ``Base Command`` (stable shell
    skeleton: ``mm cat <img> --mode fast --no-cache --format json``)
    and ``Extra Args`` (variant-specific knobs like ``--prompt`` /
    ``--generate.*`` / ``--encode.*``) so the eye lands on the
    *variation* between rows rather than on the boilerplate.
    """

    def _make_vlmgw_like_benchfile(self, tmp_path: Path) -> Path:
        """Two-row benchfile mirroring the vlmgw shape (image + video).

        Both rows pin ``--profile vlmgw --mode fast --model
        <org>/<name>``. Each row carries one ``Extra Args`` flag
        (``--prompt`` on the image row, ``--generate.extra-body`` on
        the video row) so we can exercise the base/extra split.
        """
        bf = tmp_path / "bf.py"
        bf.write_text(
            dedent(
                """
                from mm.commands.bench_commands import BenchCommand

                COMMANDS = [
                    BenchCommand(
                        "img-row",
                        "model",
                        "mm --profile vlmgw cat {file} --mode fast "
                        "--model org-a/model-a --no-cache --format json "
                        "--prompt 'describe this'",
                        requires_kind="image",
                        smallest=True,
                        skip_reason="no image files",
                        tags={"model": "org-a/model-a"},
                    ),
                    BenchCommand(
                        "vid-row",
                        "model",
                        "mm --profile vlmgw cat {file} --mode fast "
                        "--model org-b/model-b --no-cache --format json "
                        "--generate.extra-body '{\\"video_fps\\":1.0}'",
                        requires_kind="video",
                        smallest=True,
                        skip_reason="no video files",
                        tags={"model": "org-b/model-b"},
                    ),
                ]
                """
            )
        )
        return bf

    def test_tags_surface_in_json(self, tmp_path: Path, small_tree: Path):
        bf = self._make_vlmgw_like_benchfile(tmp_path)
        r = runner.invoke(
            app,
            ["bench", str(small_tree), "-b", str(bf), "--dry-run", "--format", "json"],
        )
        assert r.exit_code == 0, r.output
        data = json.loads(r.stdout)
        rows = {row["name"]: row for row in data["results"]}

        assert rows["img-row"]["tags"] == {"model": "org-a/model-a"}
        assert rows["img-row"]["requires_kind"] == "image"
        assert rows["vid-row"]["requires_kind"] == "video"
        # ``profile`` / ``mode`` are intentionally NOT separate JSON
        # keys -- they're either redundant (constant per run) or part
        # of the base command itself.
        assert "profile" not in rows["img-row"]
        assert "mode" not in rows["img-row"]

    def test_minimal_row_keeps_json_compact(self, tmp_path: Path, small_tree: Path):
        """A row with no tags / no requires_kind keeps the JSON shape minimal."""
        bf = tmp_path / "bf.py"
        bf.write_text(
            dedent(
                """
                from mm.commands.bench_commands import BenchCommand
                COMMANDS = [BenchCommand("alpha", "demo", "echo alpha")]
                """
            )
        )
        r = runner.invoke(
            app,
            ["bench", str(small_tree), "-b", str(bf), "--dry-run", "--format", "json"],
        )
        assert r.exit_code == 0, r.output
        data = json.loads(r.stdout)
        row = data["results"][0]
        assert "profile" not in row
        assert "mode" not in row
        assert "requires_kind" not in row
        assert "tags" not in row

    def test_columns_appear_in_fixed_order(
        self, tmp_path: Path, small_tree: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Header order: ``Group | Model | Base Command | Extra Args | <metrics>``."""
        bf = self._make_vlmgw_like_benchfile(tmp_path)
        monkeypatch.setenv("COLUMNS", "260")
        r = runner.invoke(
            app,
            ["bench", str(small_tree), "-b", str(bf), "--dry-run", "--format", "rich"],
        )
        assert r.exit_code == 0, r.output
        plain = _strip_ansi(r.stdout)
        header_line = next(
            line for line in plain.splitlines() if "Group" in line and "Base Command" in line
        )

        def _idx(label: str) -> int:
            m = re.search(rf"\b{re.escape(label)}\b", header_line)
            assert m, f"label {label!r} not in header line: {header_line!r}"
            return m.start()

        assert (
            _idx("Group") < _idx("Model") < _idx("Base Command") < _idx("Extra Args") < _idx("Mean")
        )
        # Profile / Mode / Extra Body / plain "Command" are all
        # intentionally absent from the new layout.
        assert "Profile" not in header_line
        assert re.search(r"\bMode\b", header_line) is None
        assert "Extra Body" not in header_line

    def test_command_cell_strips_profile_and_model(
        self, tmp_path: Path, small_tree: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """``--profile X`` and ``--model X`` are dropped from the Base Command cell."""
        bf = self._make_vlmgw_like_benchfile(tmp_path)
        monkeypatch.setenv("COLUMNS", "260")
        r = runner.invoke(
            app,
            ["bench", str(small_tree), "-b", str(bf), "--dry-run", "--format", "rich"],
        )
        assert r.exit_code == 0, r.output
        plain = _strip_ansi(r.stdout)
        # The model identifier appears in the Model column, but the
        # ``--model`` / ``--profile`` flag tokens themselves must not
        # appear anywhere in the data rows.
        assert "org-a/model-a" in plain
        body_lines = [ln for ln in plain.splitlines() if "<img>" in ln or "<vid>" in ln]
        assert body_lines, "expected at least one body row with placeholder substitution"
        for ln in body_lines:
            assert "--profile" not in ln, ln
            assert "--model" not in ln, ln

    def test_base_command_keeps_actual_mode_value(
        self, tmp_path: Path, small_tree: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """``--mode fast`` stays literally in Base Command (no <mode> templatize)."""
        bf = self._make_vlmgw_like_benchfile(tmp_path)
        monkeypatch.setenv("COLUMNS", "260")
        r = runner.invoke(
            app,
            ["bench", str(small_tree), "-b", str(bf), "--dry-run", "--format", "rich"],
        )
        assert r.exit_code == 0, r.output
        plain = _strip_ansi(r.stdout)
        assert "--mode fast" in plain
        # And the placeholder form must NOT appear -- mode is no
        # longer pulled out into its own column.
        assert "--mode <mode>" not in plain

    def test_extra_args_column_holds_prompt_and_generate(
        self, tmp_path: Path, small_tree: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """``--prompt`` and ``--generate.*`` go into the ``Extra Args`` column.

        Concretely: at least one body row carries each flag, and the
        header row carries the new ``Extra Args`` column label.
        """
        bf = self._make_vlmgw_like_benchfile(tmp_path)
        monkeypatch.setenv("COLUMNS", "260")
        r = runner.invoke(
            app,
            ["bench", str(small_tree), "-b", str(bf), "--dry-run", "--format", "rich"],
        )
        assert r.exit_code == 0, r.output
        plain = _strip_ansi(r.stdout)
        assert "--prompt" in plain
        assert "--generate.extra-body" in plain
        header_line = next(
            line for line in plain.splitlines() if "Base Command" in line and "Extra Args" in line
        )
        assert header_line  # already filtered above

    def test_command_cell_uses_kind_placeholder(
        self, tmp_path: Path, small_tree: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """``<img>`` for image rows; ``<vid>`` for video rows."""
        bf = self._make_vlmgw_like_benchfile(tmp_path)
        monkeypatch.setenv("COLUMNS", "260")
        r = runner.invoke(
            app,
            ["bench", str(small_tree), "-b", str(bf), "--dry-run", "--format", "rich"],
        )
        assert r.exit_code == 0, r.output
        plain = _strip_ansi(r.stdout)
        assert "<img>" in plain
        assert "<vid>" in plain

    def test_default_suite_hides_extra_columns(
        self, small_tree: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Default benchmark suite has no model tags and no extra args.

        Layout collapses to ``Group | Base Command | <metrics>`` --
        ``Model`` and ``Extra Args`` are conditionally hidden, and
        ``Profile`` / ``Mode`` were dropped wholesale.
        """
        monkeypatch.setenv("COLUMNS", "260")
        r = runner.invoke(
            app,
            ["bench", str(small_tree), "--dry-run", "--format", "rich"],
        )
        assert r.exit_code == 0, r.output
        plain = _strip_ansi(r.stdout)
        header_line = next(
            line for line in plain.splitlines() if "Group" in line and "Base Command" in line
        )
        assert "Model" not in header_line
        assert "Extra Args" not in header_line
        assert "Profile" not in header_line
        assert re.search(r"\bMode\b", header_line) is None


class TestArgvHelpers:
    """Unit-level coverage for the argv-manipulation helpers."""

    def test_extract_flag_space_form(self):
        from mm.commands.bench import _extract_flag

        argv = ["mm", "--profile", "vlmgw", "cat", "x"]
        assert _extract_flag(argv, "--profile") == "vlmgw"

    def test_extract_flag_equals_form(self):
        from mm.commands.bench import _extract_flag

        argv = ["mm", "--profile=vlmgw", "cat", "x"]
        assert _extract_flag(argv, "--profile") == "vlmgw"

    def test_extract_flag_aliases(self):
        from mm.commands.bench import _extract_flag

        argv = ["mm", "cat", "x", "-m", "fast"]
        assert _extract_flag(argv, "--mode", "-m") == "fast"

    def test_extract_flag_missing(self):
        from mm.commands.bench import _extract_flag

        assert _extract_flag(["echo", "hi"], "--profile") == ""

    def test_strip_flag_removes_value(self):
        from mm.commands.bench import _strip_flag

        argv = ["mm", "--profile", "vlmgw", "cat", "x"]
        assert _strip_flag(argv, "--profile") == ["mm", "cat", "x"]
        argv2 = ["mm", "--profile=vlmgw", "cat", "x"]
        assert _strip_flag(argv2, "--profile") == ["mm", "cat", "x"]

    def test_kind_placeholder(self):
        from mm.commands.bench import _kind_placeholder

        assert _kind_placeholder("image") == "<img>"
        assert _kind_placeholder("video") == "<vid>"
        assert _kind_placeholder("audio") == "<aud>"
        assert _kind_placeholder("document") == "<doc>"
        assert _kind_placeholder("code") == "<code>"
        assert _kind_placeholder(None) == "<file>"
        assert _kind_placeholder("") == "<file>"
        # Unknown kinds fall through to a self-describing token.
        assert _kind_placeholder("blueprint") == "<blueprint>"

    def test_replace_paths_handles_template_tokens(self):
        from mm.commands.bench import _replace_paths

        argv = ["mm", "cat", "{file}", "--no-cache"]
        assert _replace_paths(argv, "<img>") == ["mm", "cat", "<img>", "--no-cache"]
        argv2 = ["mm", "find", "{dir}"]
        assert _replace_paths(argv2, "<img>") == ["mm", "find", "<dir>"]

    def test_split_base_extra_partitions_argv(self):
        """``--prompt`` / ``--generate.*`` / ``--encode.*`` move to extra; the rest stays in base."""
        from mm.commands.bench import _split_base_extra

        argv = [
            "mm",
            "cat",
            "/tmp/x.jpg",
            "--mode",
            "accurate",
            "--no-cache",
            "--format",
            "json",
            "--prompt",
            "describe",
            "--generate.extra-body",
            '{"method":"caption"}',
            "--encode.strategy_opts",
            "max_width=512",
        ]
        base, extra = _split_base_extra(argv)
        assert base == [
            "mm",
            "cat",
            "/tmp/x.jpg",
            "--mode",
            "accurate",
            "--no-cache",
            "--format",
            "json",
        ]
        assert extra == [
            "--prompt",
            "describe",
            "--generate.extra-body",
            '{"method":"caption"}',
            "--encode.strategy_opts",
            "max_width=512",
        ]

    def test_split_base_extra_handles_equals_form(self):
        """``--prompt=foo`` (equals-bundled) keeps the value attached to the flag."""
        from mm.commands.bench import _split_base_extra

        argv = ["mm", "cat", "x", "--prompt=hello", "--no-cache"]
        base, extra = _split_base_extra(argv)
        assert base == ["mm", "cat", "x", "--no-cache"]
        assert extra == ["--prompt=hello"]

    def test_split_base_extra_with_no_extras(self):
        """Argvs without any extra-flag prefix produce an empty extra list."""
        from mm.commands.bench import _split_base_extra

        argv = ["mm", "find", "{dir}", "--format", "json"]
        base, extra = _split_base_extra(argv)
        assert base == argv
        assert extra == []

    def test_build_command_cells_full_pipeline(self, tmp_path: Path):
        """End-to-end: profile/model dropped, paths swapped, base/extra split."""
        from mm.commands.bench import BenchResult, _build_command_cells

        f = tmp_path / "x.jpg"
        f.write_bytes(b"\x89PNG\r\n\x1a\n")
        joined = (
            f"mm --profile vlmgw cat {f!s} --mode fast --model org/m "
            f"--no-cache --format json --prompt describe"
        )
        r = BenchResult(
            "n",
            "g",
            preview_lines=[joined],
            requires_kind="image",
            tags={"model": "org/m"},
        )
        base, extra = _build_command_cells(r)
        # Base: profile/model stripped, real path -> <img>, mode value retained.
        assert "--profile" not in base
        assert "vlmgw" not in base
        assert "--model" not in base
        assert "org/m" not in base
        assert "--mode fast" in base
        assert "<img>" in base
        assert "--no-cache" in base
        assert "--format json" in base
        # Extra: only the variant-specific knob.
        assert extra == "--prompt describe"

    def test_build_command_cells_empty_extra(self, tmp_path: Path):
        """Rows without --prompt/--generate.*/--encode.* return an empty extra string."""
        from mm.commands.bench import BenchResult, _build_command_cells

        f = tmp_path / "x.jpg"
        f.write_bytes(b"\x89PNG\r\n\x1a\n")
        joined = f"mm --profile vlmgw cat {f!s} --mode fast --no-cache --format json"
        r = BenchResult("n", "g", preview_lines=[joined], requires_kind="image")
        base, extra = _build_command_cells(r)
        assert "<img>" in base
        assert "--mode fast" in base
        assert extra == ""

    def test_build_command_cells_falls_back_to_template_for_skipped(self):
        """Skipped rows have empty preview_lines; cell uses cmd_template."""
        from mm.commands.bench import BenchResult, _build_command_cells

        r = BenchResult(
            "n",
            "g",
            cmd_template="mm --profile vlmgw cat {file} --mode fast --prompt hi",
            requires_kind="image",
            skipped=True,
            skip_reason="no image files",
        )
        base, extra = _build_command_cells(r)
        assert "<img>" in base
        assert "--mode fast" in base
        assert "vlmgw" not in base
        assert extra == "--prompt hi"


# ── markdown recording ───────────────────────────────────────────────


class TestDisabledRows:
    """`BenchCommand.disabled=True` is render-only: appears in the table (dimmed)
    but the harness never invokes its argv."""

    def test_disabled_row_is_marked_in_json(
        self, tmp_path: Path, small_tree: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """JSON surfaces ``skipped: true`` plus ``skip_reason: disabled`` plus ``disabled: true``."""
        # ``--dry-run`` keeps the markdown recorder dormant so this
        # test doesn't leak a ``benchmarks/<date>-mm-bench-bf.md``
        # file into whatever ``cwd`` pytest happens to inherit.
        monkeypatch.chdir(tmp_path)
        bf = _write_benchfile(
            tmp_path / "bf.py",
            """
            from mm.commands.bench_commands import BenchCommand
            COMMANDS = [
                BenchCommand("alive", "demo", "echo alive"),
                BenchCommand("muted", "demo", "echo muted", disabled=True),
            ]
            """,
        )
        with patch("mm.commands.bench._time_cmd") as time_cmd:
            time_cmd.return_value = (
                [1.0],
                type("P", (), {"stdout": "", "stderr": "", "returncode": 0})(),
            )
            r = runner.invoke(
                app,
                ["bench", str(small_tree), "-b", str(bf), "-r", "1", "-w", "0", "--format", "json"],
            )
        assert r.exit_code == 0, r.output
        rows = {row["name"]: row for row in json.loads(r.stdout)["results"]}
        # Live row: not skipped, not disabled.
        assert rows["alive"].get("skipped") is None or rows["alive"]["skipped"] is False
        assert "disabled" not in rows["alive"]
        # Disabled row: skipped + skip_reason + disabled flags all set.
        assert rows["muted"]["skipped"] is True
        assert rows["muted"]["skip_reason"] == "disabled"
        assert rows["muted"]["disabled"] is True

    def test_disabled_row_never_invokes_subprocess(
        self, tmp_path: Path, small_tree: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """The runner short-circuits BEFORE calling _time_cmd for disabled rows."""
        monkeypatch.chdir(tmp_path)
        bf = _write_benchfile(
            tmp_path / "bf.py",
            """
            from mm.commands.bench_commands import BenchCommand
            COMMANDS = [
                BenchCommand("disabled-row", "demo", "echo nope", disabled=True),
            ]
            """,
        )
        with patch("mm.commands.bench._time_cmd") as time_cmd:
            r = runner.invoke(
                app,
                ["bench", str(small_tree), "-b", str(bf), "-r", "1", "-w", "0", "--format", "json"],
            )
        assert r.exit_code == 0, r.output
        time_cmd.assert_not_called()
        data = json.loads(r.stdout)
        assert data["results"][0]["disabled"] is True

    def test_disabled_row_renders_dimmed_in_rich(
        self, tmp_path: Path, small_tree: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """The rich table embeds the dim ANSI sequence on disabled rows.

        Rich applies row-level ``style="dim"`` as the ANSI ``\\x1b[2m``
        opener around every cell of that row. We probe the raw output
        for a disabled-row line bearing the dim opener, plus the
        ``skipped: disabled`` trailer.
        """
        bf = _write_benchfile(
            tmp_path / "bf.py",
            """
            from mm.commands.bench_commands import BenchCommand
            COMMANDS = [
                BenchCommand("alive", "demo", "echo alive"),
                BenchCommand("muted", "demo", "echo muted", disabled=True),
            ]
            """,
        )
        monkeypatch.setenv("COLUMNS", "260")
        # ``CliRunner`` strips colour by default; force-rich stays
        # alive only when output is captured with ANSI codes intact.
        r = runner.invoke(
            app,
            ["bench", str(small_tree), "-b", str(bf), "--dry-run", "--format", "rich"],
            color=True,
        )
        assert r.exit_code == 0, r.output
        # Disabled row is annotated as ``skipped: disabled`` in the
        # metrics column. Validate that the row is present, no live
        # metric appears for it, and the ``\\x1b[2m`` (dim) sequence
        # appears somewhere on the muted row's line.
        muted_lines = [ln for ln in r.stdout.splitlines() if "muted" in ln]
        assert muted_lines, "expected the disabled row to render"
        assert any("skipped: disabled" in _strip_ansi(ln) for ln in muted_lines)
        # At least one cell on the muted row must carry the dim ANSI
        # opener (``\\x1b[2m``) -- proves full-row dimming is in effect.
        assert any("\x1b[2m" in ln for ln in muted_lines), muted_lines


class TestRecordingHelpers:
    """Unit tests for the recording helper functions (no subprocesses)."""

    def test_derive_recording_stem_default(self):
        from mm.commands.bench import _derive_recording_stem

        assert _derive_recording_stem(None) == "default"

    def test_derive_recording_stem_strips_bench_commands_suffix(self, tmp_path: Path):
        from mm.commands.bench import _derive_recording_stem

        bf = tmp_path / "vlmgw_bench_commands.py"
        bf.write_text("COMMANDS = []\n")
        assert _derive_recording_stem(bf) == "vlmgw"

    def test_derive_recording_stem_keeps_other_stems(self, tmp_path: Path):
        from mm.commands.bench import _derive_recording_stem

        bf = tmp_path / "custom.py"
        bf.write_text("COMMANDS = []\n")
        assert _derive_recording_stem(bf) == "custom"

    def test_derive_recording_path_uses_yymmdd(self, tmp_path: Path):
        import datetime as dt

        from mm.commands.bench import _derive_recording_path

        path = _derive_recording_path(None, root=tmp_path / "benchmarks")
        today = dt.datetime.now().strftime("%y%m%d")
        assert path.name == f"{today}-mm-bench-default.md"
        assert path.parent == tmp_path / "benchmarks"

    def test_stdout_fence_lang_json_for_object(self):
        from mm.commands.bench import _stdout_fence_lang

        assert _stdout_fence_lang('{"a": 1}') == "json"
        assert _stdout_fence_lang("  \n  [1,2,3]") == "json"

    def test_stdout_fence_lang_text_for_other(self):
        from mm.commands.bench import _stdout_fence_lang

        assert _stdout_fence_lang("hello world\n") == "text"
        assert _stdout_fence_lang("") == "text"

    def test_normalize_stdout_paths_replaces_argv_abs_paths(self, tmp_path: Path):
        from mm.commands.bench import _normalize_stdout_paths

        f = tmp_path / "img.jpg"
        f.write_bytes(b"x")
        argv_str = f"mm cat {f} --mode fast"
        stdout = f'{{"path": "{f}", "size": 1}}'
        out = _normalize_stdout_paths(argv_str, stdout)
        assert str(f) not in out
        assert "img.jpg" in out

    def test_normalize_stdout_paths_skips_relative_tokens(self):
        from mm.commands.bench import _normalize_stdout_paths

        out = _normalize_stdout_paths("mm find . --format json", "no abs paths here")
        assert out == "no abs paths here"

    def test_format_recording_output_skipped(self):
        from mm.commands.bench import BenchResult, _format_recording_output

        r = BenchResult("x", "g", skipped=True, skip_reason="no image files")
        body, lang = _format_recording_output(r, "")
        assert lang == "text"
        assert body == "[skipped: no image files]"

    def test_format_recording_output_non_zero_exit(self):
        from mm.commands.bench import BenchResult, _format_recording_output

        r = BenchResult(
            "x",
            "g",
            last_stderr="line1\nline2\nline3\nline4\nline5\nline6\nline7",
            returncode=2,
        )
        body, lang = _format_recording_output(r, "")
        assert lang == "text"
        assert body.startswith("[exit 2]")
        # Tail keeps the last 5 stderr lines.
        assert "line3" in body
        assert "line7" in body
        assert "line1" not in body
        assert "line2" not in body

    def test_format_recording_output_truncates_long_stdout(self):
        """Verbose model outputs are capped at the recorder's per-row budget."""
        from mm.commands.bench import (
            BenchResult,
            _MAX_RECORDING_STDOUT_BYTES,
            _format_recording_output,
        )

        # 4x the cap; well over budget so the truncation branch fires.
        long_body = "x" * (_MAX_RECORDING_STDOUT_BYTES * 4)
        r = BenchResult("x", "g", last_stdout=long_body, returncode=0)
        body, _lang = _format_recording_output(r, "")
        # Body shrinks below 2x the cap (head + truncation marker),
        # carrying an auditable annotation of how much was dropped.
        assert len(body.encode("utf-8")) < 2 * _MAX_RECORDING_STDOUT_BYTES
        assert "bytes truncated]" in body

    def test_format_recording_output_short_stdout_passthrough(self):
        """Short outputs flow through untouched -- no marker, no trim."""
        from mm.commands.bench import BenchResult, _format_recording_output

        r = BenchResult("x", "g", last_stdout="ok\n", returncode=0)
        body, _lang = _format_recording_output(r, "")
        assert body.rstrip() == "ok"
        assert "truncated" not in body

    def test_format_recording_output_json_stdout(self, tmp_path: Path):
        from mm.commands.bench import BenchResult, _format_recording_output

        f = tmp_path / "img.jpg"
        f.write_bytes(b"x")
        argv_str = f"mm cat {f}"
        r = BenchResult(
            "x",
            "g",
            last_stdout=f'{{"path": "{f}"}}\n',
            returncode=0,
        )
        body, lang = _format_recording_output(r, argv_str)
        assert lang == "json"
        # Path normalization runs (argv has the abs path) and ANSI strip
        # is a no-op for plain text.
        assert "img.jpg" in body
        assert str(f) not in body

    def test_build_args_line_image_with_mode(self):
        from mm.commands.bench import BenchResult, _build_args_line

        r = BenchResult(
            "x",
            "g",
            requires_kind="image",
            data_file_paths=["/tmp/test/1-vqa-car.jpg"],
        )
        argv = ["mm", "cat", "/tmp/test/1-vqa-car.jpg", "--mode", "fast"]
        line = _build_args_line(r, argv)
        assert line.startswith("args: ")
        # JSON-parse to assert structure independent of key ordering.
        payload = json.loads(line[len("args: ") :])
        assert payload == {"img": "1-vqa-car.jpg", "mode": "fast"}

    def test_build_args_line_multi_image(self):
        from mm.commands.bench import BenchResult, _build_args_line

        r = BenchResult(
            "x",
            "g",
            requires_kind="image",
            data_file_paths=["/tmp/a.jpg", "/tmp/b.jpg"],
        )
        argv = ["python", "_multi_image_call.py", "/tmp/a.jpg", "/tmp/b.jpg"]
        line = _build_args_line(r, argv)
        payload = json.loads(line[len("args: ") :])
        # Multiple files -> list under the kind key. ``mode`` absent
        # because argv has no ``--mode`` flag.
        assert payload == {"img": ["a.jpg", "b.jpg"]}

    def test_build_args_line_empty_when_no_data_or_mode(self):
        from mm.commands.bench import BenchResult, _build_args_line

        r = BenchResult("x", "g")
        assert _build_args_line(r, ["mm", "version"]) == ""

    def test_build_footer_line_uses_last_round(self):
        from mm.commands.bench import BenchResult, _build_footer_line

        r = BenchResult(
            "x",
            "g",
            timings_ms=[2900.0, 2950.0, 3100.0],  # last round = 3.1s
            total_bytes=39080,
        )
        line = _build_footer_line(r)
        # 3.1s elapsed; 39080 B / 3.1 s ≈ 12.3 KB/s.
        assert "3.10s" in line
        assert "38.2 KB" in line
        assert "/s" in line
        assert "•" in line

    def test_build_footer_line_empty_for_zero_round_dry_run(self):
        from mm.commands.bench import BenchResult, _build_footer_line

        r = BenchResult("x", "g", is_dry_run=True)
        assert _build_footer_line(r) == ""


class TestRecordingFile:
    """End-to-end tests covering ``benchmarks/<YYMMDD>-mm-bench-*.md``."""

    @staticmethod
    def _today_filename(suite: str) -> str:
        import datetime as dt

        return f"{dt.datetime.now().strftime('%y%m%d')}-mm-bench-{suite}.md"

    def test_recording_written_for_default_suite(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, small_tree: Path
    ):
        monkeypatch.chdir(tmp_path)
        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "--command",
                "find",
                "-r",
                "1",
                "-w",
                "0",
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0, r.output
        rec = tmp_path / "benchmarks" / self._today_filename("default")
        assert rec.exists(), f"expected {rec}, cwd={list(tmp_path.iterdir())}"
        body = rec.read_text()
        assert body.startswith("# mm bench recording — default — ")
        # Each row's Rich-table snapshot is emitted as raw markdown
        # (not inside a fence) so renderers display the box-drawing
        # characters directly. Probe column-header text to confirm.
        assert "Group" in body
        assert "Base Command" in body
        # Stdout is still fenced (json when it looks like JSON, text
        # otherwise).
        assert "```json" in body or "```text" in body

    def test_recording_summarises_disabled_rows(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        small_tree: Path,
    ):
        """Disabled rows land in a `## Disabled` roll-up, not as per-row tables.

        Per-row Rich-table snapshots for disabled rows would balloon
        the recording past the 100 KB pre-commit cap on bigger suites
        without adding any diagnostic value (no stdout, no timing). The
        compact roll-up keeps the matrix coverage acknowledged while
        focusing the body on rows that actually executed.
        """
        monkeypatch.chdir(tmp_path)
        bf = _write_benchfile(
            tmp_path / "summary_bench_commands.py",
            """
            from mm.commands.bench_commands import BenchCommand
            COMMANDS = [
                BenchCommand("alive", "demo", "echo alive"),
                BenchCommand("muted", "demo", "echo muted",
                             disabled=True, tags={"model": "x/y"}),
            ]
            """,
        )
        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "--bench-file",
                str(bf),
                "-r",
                "1",
                "-w",
                "0",
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0, r.output
        rec = tmp_path / "benchmarks" / self._today_filename("summary")
        body = rec.read_text()
        # Disabled row is in the roll-up section, NOT as its own
        # Rich-table block.
        assert "## Disabled (1)" in body
        assert "- `demo/muted` — `x/y`" in body
        # Active row still gets the per-row Rich-table treatment.
        assert "alive" in body
        # The body holds exactly ONE Rich-table block (for the active
        # ``alive`` row); the disabled row appears only in the roll-up
        # bullet list, no per-row table.
        assert body.count("╭") == 1, body

    def test_recording_written_for_benchfile(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        small_tree: Path,
    ):
        monkeypatch.chdir(tmp_path)
        bf = _write_benchfile(
            tmp_path / "demo_bench_commands.py",
            """
            from mm.commands.bench_commands import BenchCommand
            COMMANDS = [BenchCommand("hello", "demo", "echo hello")]
            """,
        )
        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "--bench-file",
                str(bf),
                "-r",
                "1",
                "-w",
                "0",
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0, r.output
        rec = tmp_path / "benchmarks" / self._today_filename("demo")
        assert rec.exists()
        body = rec.read_text()
        assert "# mm bench recording — demo — " in body
        # Captured stdout from `echo hello`.
        assert "hello" in body

    def test_recording_skipped_for_dry_run(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, small_tree: Path
    ):
        monkeypatch.chdir(tmp_path)
        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "--command",
                "find",
                "--dry-run",
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0, r.output
        bench_dir = tmp_path / "benchmarks"
        # Either the directory wasn't created at all, or it has no
        # mm-bench-*.md files.
        if bench_dir.exists():
            assert not list(bench_dir.glob("*-mm-bench-*.md"))

    def test_recording_skipped_for_host_info(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.chdir(tmp_path)
        r = runner.invoke(app, ["bench", str(tmp_path), "--host-info"])
        assert r.exit_code == 0, r.output
        bench_dir = tmp_path / "benchmarks"
        if bench_dir.exists():
            assert not list(bench_dir.glob("*-mm-bench-*.md"))

    def test_recording_strips_absolute_paths(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        small_tree: Path,
    ):
        """An echo of the absolute path argument is rewritten to its basename."""
        monkeypatch.chdir(tmp_path)
        f = tmp_path / "marker.jpg"
        f.write_bytes(b"x")
        bf = _write_benchfile(
            tmp_path / "abs_paths_bench_commands.py",
            f"""
            from mm.commands.bench_commands import BenchCommand
            COMMANDS = [BenchCommand("echo-abs", "demo", "echo {f}")]
            """,
        )
        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "--bench-file",
                str(bf),
                "-r",
                "1",
                "-w",
                "0",
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0, r.output
        rec = tmp_path / "benchmarks" / self._today_filename("abs_paths")
        body = rec.read_text()
        # Captured stdout had the abs path, but the recording shows the
        # basename only.
        assert "marker.jpg" in body
        assert str(f) not in body

    def test_recording_handles_non_zero_exit(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        small_tree: Path,
    ):
        monkeypatch.chdir(tmp_path)
        bf = _write_benchfile(
            tmp_path / "fail_bench_commands.py",
            """
            from mm.commands.bench_commands import BenchCommand
            COMMANDS = [
                BenchCommand("fail", "demo",
                             "sh -c 'echo boom 1>&2; exit 7'"),
            ]
            """,
        )
        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "--bench-file",
                str(bf),
                "-r",
                "1",
                "-w",
                "0",
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0, r.output
        rec = tmp_path / "benchmarks" / self._today_filename("fail")
        body = rec.read_text()
        assert "[exit 7]" in body
        assert "boom" in body

    def test_recording_path_logged_to_stderr(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, small_tree: Path
    ):
        monkeypatch.chdir(tmp_path)
        r = runner.invoke(
            app,
            [
                "bench",
                str(small_tree),
                "--command",
                "find",
                "-r",
                "1",
                "-w",
                "0",
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0, r.output
        # ``CliRunner.output`` is the merged stdout+stderr stream; the
        # recording line is written to stderr via ``typer.echo(...,
        # err=True)``.
        assert "Wrote recording to " in r.output
        assert "-mm-bench-default.md" in r.output
