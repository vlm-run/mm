"""Tests for ``mm cat`` auto-detection and dispatch."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mm.cli import app
from mm.utils import AUDIO_EXTS, IMAGE_EXTS, VIDEO_EXTS, file_kind
from typer.testing import CliRunner

from .test_utils import write_minimal_mp4, write_png

runner = CliRunner()


# ── Helpers ───────────────────────────────────────────────────────────


def _minimal_single_page_pdf(path: Path) -> None:
    """Tiny valid PDF with one (Hello World) text op — same structure as test_integration."""
    content = (
        b"%PDF-1.0\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Contents 4 0 R/Resources<</Font<</F1<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>>>>>>>endobj\n"
        b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 100 700 Td (Hello World) Tj ET\nendstream\nendobj\n"
        b"xref\n0 5\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000306 00000 n \n"
        b"trailer<</Size 5/Root 1 0 R>>\nstartxref\n406\n%%EOF"
    )
    path.write_bytes(content)


# ── Fixture: mixed directory ──────────────────────────────────────────


@pytest.fixture
def mixed_dir(tmp_path: Path) -> Path:
    """Directory with one file per major type."""
    write_png(tmp_path / "photo.png", 64, 48)
    write_minimal_mp4(tmp_path / "clip.mp4")
    (tmp_path / "track.mp3").write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 200)
    (tmp_path / "readme.md").write_text("# Title\n\nHello world.\n")
    (tmp_path / "main.py").write_text("def run():\n    return 42\n")
    (tmp_path / "config.toml").write_text("[server]\nport = 3000\n")
    return tmp_path


# ── file_kind unit tests ────────────────────────────────────────────


class TestFileKindDetection:
    """Verify file_kind classifies by extension."""

    @pytest.mark.parametrize("ext", sorted(IMAGE_EXTS))
    def test_image_extensions(self, ext):
        assert file_kind(Path(f"test{ext}")) == "image"

    @pytest.mark.parametrize("ext", sorted(VIDEO_EXTS))
    def test_video_extensions(self, ext):
        assert file_kind(Path(f"test{ext}")) == "video"

    @pytest.mark.parametrize("ext", sorted(AUDIO_EXTS))
    def test_audio_extensions(self, ext):
        assert file_kind(Path(f"test{ext}")) == "audio"

    def test_pdf(self):
        assert file_kind(Path("paper.pdf")) == "document"

    @pytest.mark.parametrize("ext", [".py", ".rs", ".js", ".md", ".toml", ".txt", ".csv"])
    def test_text_fallback(self, ext):
        assert file_kind(Path(f"file{ext}")) == "text"


# ── Default mode (fast) ─────────────────────────────────────────────


class TestFastDefault:
    """Default ``cat`` mode is now ``fast`` (peek replaces the old metadata tier)."""

    def test_text_passthrough_default(self, mixed_dir: Path, isolated_db):
        r = runner.invoke(app, ["cat", str(mixed_dir / "readme.md")])
        assert r.exit_code == 0
        assert "Title" in r.output

    def test_code_passthrough_default(self, mixed_dir: Path, isolated_db):
        r = runner.invoke(app, ["cat", str(mixed_dir / "main.py")])
        assert r.exit_code == 0
        assert "def run" in r.output

    def test_text_does_not_call_llm(self, monkeypatch, mixed_dir: Path, isolated_db):
        """``mm cat`` on text/code must never instantiate the LLM backend."""
        from mm import llm

        class _Sentinel:
            def __init__(self, *args, **kwargs):
                raise AssertionError(
                    "LlmBackend was constructed under cat for a text file; "
                    "the cat-text path must not invoke an LLM."
                )

        monkeypatch.setattr(llm, "LlmBackend", _Sentinel)

        r = runner.invoke(app, ["cat", str(mixed_dir / "main.py")])
        assert r.exit_code == 0

    def test_metadata_mode_rejected(self, mixed_dir: Path):
        """``--mode metadata`` is no longer valid; users get a friendly hint."""
        r = runner.invoke(app, ["cat", str(mixed_dir / "main.py"), "-m", "metadata"])
        assert r.exit_code != 0
        combined = (r.output or "") + (getattr(r, "stderr", "") or "")
        assert "fast" in combined.lower() and "accurate" in combined.lower()

    def test_default_mode_json_emits_fast(self, mixed_dir: Path, isolated_db):
        r = runner.invoke(app, ["cat", str(mixed_dir / "main.py"), "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.stdout)
        assert isinstance(data, list) and data
        assert data[0].get("mode") == "fast"

    def test_pretty_json_format_indents_and_breaks_lines(self, mixed_dir: Path):
        """``--format pretty-json`` always indents, regardless of TTY/pipe.

        The wire shape matches ``--format json`` (same ``{path, mode,
        content}`` envelope so downstream parsers don't need to fork
        on the format flag); only the serializer's ``indent`` argument
        differs. Useful for capturing into markdown / docs / recordings
        where multi-line JSON renders far more readably than a
        single-line escape soup.
        """
        r = runner.invoke(app, ["cat", str(mixed_dir / "main.py"), "--format", "pretty-json"])
        assert r.exit_code == 0
        # Same envelope as `json`: ingestable by anyone who already
        # parses `mm cat --format json`.
        data = json.loads(r.stdout)
        assert isinstance(data, list) and data
        assert {"path", "mode", "content"}.issubset(data[0])
        # And the *serialised* form has line breaks + indentation
        # (multiple top-level newlines means the printer formatted it,
        # not just that ``content`` happened to contain ``\n``).
        assert r.output.count("\n") >= 4
        assert "  " in r.output  # 2-space indent

    def test_json_vs_pretty_json_share_payload_shape(self, mixed_dir: Path):
        """Parsing either format yields the same dict (only whitespace differs)."""
        compact = runner.invoke(app, ["cat", str(mixed_dir / "main.py"), "--format", "json"])
        pretty = runner.invoke(app, ["cat", str(mixed_dir / "main.py"), "--format", "pretty-json"])
        assert compact.exit_code == 0 and pretty.exit_code == 0
        assert json.loads(compact.output) == json.loads(pretty.output)


# ── Fast mode (explicit) ─────────────────────────────────────────────


class TestFastModeExplicit:
    """Fast mode now requires the explicit `-m fast` flag."""

    def test_text_fast_passthrough(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "readme.md"), "-m", "fast"])
        assert r.exit_code == 0
        assert "Title" in r.output

    def test_code_fast_passthrough(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "main.py"), "-m", "fast"])
        assert r.exit_code == 0
        assert "def run" in r.output


# ── head / tail ───────────────────────────────────────────────────────


class TestHeadTail:
    def test_head_limits_lines(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "readme.md"), "-n", "1"])
        assert r.exit_code == 0
        lines = r.output.strip().splitlines()
        assert len(lines) == 1

    def test_tail_limits_lines(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "readme.md"), "-n", "-1"])
        assert r.exit_code == 0
        lines = r.output.strip().splitlines()
        assert len(lines) == 1


class TestCatPdf:
    """CLI smoke: ``mm cat`` on a PDF runs the document fast/accurate pipeline.

    Default mode (``fast``) and explicit ``-m fast`` both go through the
    same ``page-text`` encoder, so the rendered text matches.
    """

    def test_pdf_default_json_extracts_text(self, tmp_path: Path, isolated_db: Path):
        """Default mode is now ``fast`` — runs the document fast pipeline (pypdfium2 page-text)."""
        pdf = tmp_path / "hello.pdf"
        _minimal_single_page_pdf(pdf)
        r = runner.invoke(app, ["cat", str(pdf), "--format", "json"])
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert len(data) == 1
        assert data[0].get("mode") == "fast"
        assert "Hello" in data[0].get("content", "")

    def test_pdf_explicit_fast_json_extracts_text(self, tmp_path: Path, isolated_db: Path):
        pdf = tmp_path / "hello.pdf"
        _minimal_single_page_pdf(pdf)
        r = runner.invoke(
            app,
            ["cat", str(pdf), "-m", "fast", "--format", "json"],
        )
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert len(data) == 1
        assert data[0].get("mode") == "fast"
        assert "Hello" in data[0].get("content", "")


# ── Error handling ────────────────────────────────────────────────────


class TestErrors:
    def test_no_files_exits_nonzero(self):
        r = runner.invoke(app, ["cat"])
        assert r.exit_code != 0

    def test_nonexistent_file(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "nope.txt")])
        combined = (r.output or "") + (getattr(r, "stderr", "") or "")
        assert "not found" in combined.lower()

    def test_invalid_mode(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "main.py"), "-m", "bogus"])
        assert r.exit_code != 0
        combined = (r.output or "") + (getattr(r, "stderr", "") or "")
        # Error enumerates the two valid modes plus a hint at peek for raw metadata.
        for token in ("fast", "accurate"):
            assert token in combined.lower()


class TestExpandPathArg:
    """``mm.utils.expand_path_arg`` / ``expand_path_args`` unit tests."""

    def test_file_returns_resolved_path(self, tmp_path: Path):
        from mm.utils import expand_path_arg

        f = tmp_path / "x.md"
        f.write_text("x\n")
        result = expand_path_arg(f)
        # Resolved -- absolute, no symlinks/``.``/``..`` segments -- so the
        # returned form is a reliable de-dup key alongside directory walks.
        assert result == [f.resolve()]
        assert result[0].is_absolute()

    def test_file_relative_input_returns_absolute(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A relative file input still resolves to an absolute path.

        Without this guarantee, callers that mix file and directory args
        would see mismatched de-dup keys (directory walks always yield
        absolute paths via the Rust ``Scanner``).
        """
        from mm.utils import expand_path_arg

        f = tmp_path / "x.md"
        f.write_text("x\n")
        monkeypatch.chdir(tmp_path)
        result = expand_path_arg("x.md")
        assert result == [f.resolve()]
        assert result[0].is_absolute()

    def test_directory_returns_inside_files(self, tmp_path: Path):
        from mm.utils import expand_path_arg

        (tmp_path / "a.md").write_text("a\n")
        (tmp_path / "b.md").write_text("b\n")
        names = sorted(p.name for p in expand_path_arg(tmp_path))
        assert names == ["a.md", "b.md"]

    def test_missing_path_raises_filenotfound(self, tmp_path: Path):
        from mm.utils import expand_path_arg

        with pytest.raises(FileNotFoundError):
            expand_path_arg(tmp_path / "missing")

    def test_expand_path_args_dedupes(self, tmp_path: Path):
        from mm.utils import expand_path_args

        a = tmp_path / "a.md"
        a.write_text("a\n")
        b = tmp_path / "b.md"
        b.write_text("b\n")
        result = expand_path_args([tmp_path, a])
        names = [p.name for p in result]
        # ``a.md`` shows up once even though it's reachable from both inputs.
        assert names.count("a.md") == 1
        assert "b.md" in names

    def test_expand_path_args_dedupes_mixed_relative_and_absolute(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Regression: relative file + absolute directory still de-dupe.

        Directory walks return absolute paths, so the file branch must
        also normalize to an absolute path before de-dup. Otherwise mixing
        ``mm cat ./folder ./folder/a.md`` would process ``a.md`` twice.
        """
        from mm.utils import expand_path_args

        a = tmp_path / "a.md"
        a.write_text("a\n")
        monkeypatch.chdir(tmp_path)
        # Mix relative file arg with an absolute directory arg.
        result = expand_path_args([tmp_path, "a.md"])
        names = [p.name for p in result]
        assert names.count("a.md") == 1


class TestCatDirectoryArg:
    """``mm cat <folder>`` expands directories into their files.

    The CLI-level tests deliberately use folders that resolve to a *single*
    file after expansion. ``mm cat`` processes multiple files via an internal
    threadpool with shared SQLite connections, and concurrent text/code
    files occasionally hit ``database is locked`` errors -- a pre-existing
    concurrency limitation that is out of scope for this change. Folder
    walking and de-duplication semantics are exhaustively covered at the
    unit level in :class:`TestExpandPathArg`.
    """

    def test_directory_accepted_as_argument(self, tmp_path: Path, isolated_db):
        """``mm cat <folder>`` exits cleanly and emits the folder's content."""
        (tmp_path / "a.md").write_text("alpha-marker\n")
        r = runner.invoke(app, ["cat", str(tmp_path), "-y"])
        assert r.exit_code == 0, r.output
        assert "alpha-marker" in r.output

    def test_directory_recursive(self, tmp_path: Path, isolated_db):
        """Nested files are reached by the recursive Scanner walk."""
        sub = tmp_path / "nested"
        sub.mkdir()
        (sub / "leaf.md").write_text("leaf-marker\n")
        r = runner.invoke(app, ["cat", str(tmp_path), "-y"])
        assert r.exit_code == 0, r.output
        assert "leaf-marker" in r.output

    def test_directory_no_ignore_flag(self, tmp_path: Path, isolated_db):
        """``--no-ignore`` is wired through to folder expansion end-to-end."""
        (tmp_path / "keep.md").write_text("keep-marker\n")
        r = runner.invoke(app, ["cat", str(tmp_path), "--no-ignore", "-y"])
        assert r.exit_code == 0, r.output
        assert "keep-marker" in r.output

    def test_mixed_file_and_directory_dedupes(self, tmp_path: Path, isolated_db):
        """A file listed both directly and inside a folder is processed once.

        After dedupe, the surviving path list has length 1, so cat takes
        its single-file render path (no ``<a.md>`` banner). ``alpha``
        therefore shows up exactly once -- if dedupe were broken we'd see
        it twice.
        """
        (tmp_path / "a.md").write_text("alpha-marker\n")
        r = runner.invoke(app, ["cat", str(tmp_path), str(tmp_path / "a.md"), "-y"])
        assert r.exit_code == 0, r.output
        assert r.output.count("alpha-marker") == 1

    def test_mixed_relative_file_and_absolute_directory_dedupes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_db
    ):
        """Regression: ``mm cat <abs-folder> <relative-file>`` de-dupes.

        Before the fix, the directory branch produced absolute paths but
        the file branch keyed on the user's raw (relative) string, so the
        same file was processed twice.
        """
        (tmp_path / "a.md").write_text("alpha-marker\n")
        monkeypatch.chdir(tmp_path)
        r = runner.invoke(app, ["cat", str(tmp_path), "a.md", "-y"])
        assert r.exit_code == 0, r.output
        assert r.output.count("alpha-marker") == 1


# ── Override surfaces: --model / --prompt / --generate.extra-body ─────


class TestValidateExtraBodyJson:
    """Unit tests for cat._validate_extra_body_json — JSON validation only."""

    def test_none_passes_through(self):
        from mm.commands.cat import _validate_extra_body_json

        assert _validate_extra_body_json(None) is None

    def test_object_passes_through(self):
        from mm.commands.cat import _validate_extra_body_json

        raw = '{"method":"detect","method_params":{"object":"fish"}}'
        assert _validate_extra_body_json(raw) == raw

    def test_bad_json_raises_typer_exit(self):
        import typer
        from mm.commands.cat import _validate_extra_body_json

        with pytest.raises(typer.Exit):
            _validate_extra_body_json("{not json}")

    def test_non_object_raises_typer_exit(self):
        import typer
        from mm.commands.cat import _validate_extra_body_json

        with pytest.raises(typer.Exit):
            _validate_extra_body_json("[1,2,3]")


class TestCatGenerateExtraBodyCli:
    """CLI smoke tests for --generate.extra-body JSON validation."""

    def test_bad_extra_body_json_fails(self, mixed_dir: Path):
        r = runner.invoke(
            app,
            [
                "cat",
                str(mixed_dir / "readme.md"),
                "--generate.extra-body",
                "{not json}",
            ],
        )
        assert r.exit_code != 0
        combined = (r.output or "") + (getattr(r, "stderr", "") or "")
        assert "extra-body" in combined.lower() or "json" in combined.lower()

    def test_extra_body_array_rejected(self, mixed_dir: Path):
        r = runner.invoke(
            app,
            [
                "cat",
                str(mixed_dir / "readme.md"),
                "--generate.extra-body",
                "[1,2,3]",
            ],
        )
        assert r.exit_code != 0


class TestCatDroppedFlags:
    """Regression guards: flags removed in PR #106 must error out."""

    @pytest.mark.parametrize(
        "flag,value",
        [
            ("--extra-body", '{"method":"ocr"}'),
            ("-e", '{"method":"ocr"}'),
            ("--method", "ocr"),
            ("--method-params", '{"lang":"ch"}'),
        ],
    )
    def test_legacy_flag_no_longer_recognised(self, mixed_dir: Path, flag: str, value: str):
        r = runner.invoke(
            app,
            ["cat", str(mixed_dir / "readme.md"), flag, value],
        )
        assert r.exit_code != 0


class TestCatModelAlias:
    """`--model` and `--generate.model` are accepted as aliases for the same option."""

    def test_short_form_accepted(self, mixed_dir: Path):
        r = runner.invoke(
            app,
            ["cat", str(mixed_dir / "readme.md"), "--model", "moondream2"],
        )
        # Default mode is metadata (no LLM call), but the flag must parse cleanly.
        assert r.exit_code == 0, (r.output, getattr(r, "stderr", ""))

    def test_dotted_form_accepted(self, mixed_dir: Path):
        r = runner.invoke(
            app,
            ["cat", str(mixed_dir / "readme.md"), "--generate.model", "moondream2"],
        )
        assert r.exit_code == 0, (r.output, getattr(r, "stderr", ""))


class TestCatPromptAlias:
    """`--prompt` and `--generate.prompt` are accepted as aliases for the same option."""

    def test_short_form_accepted(self, mixed_dir: Path):
        r = runner.invoke(
            app,
            ["cat", str(mixed_dir / "readme.md"), "--prompt", "Summarize:"],
        )
        assert r.exit_code == 0, (r.output, getattr(r, "stderr", ""))

    def test_dotted_form_accepted(self, mixed_dir: Path):
        r = runner.invoke(
            app,
            ["cat", str(mixed_dir / "readme.md"), "--generate.prompt", "Summarize:"],
        )
        assert r.exit_code == 0, (r.output, getattr(r, "stderr", ""))


class TestCatAudioOverrides:
    """Verify --encode.backend and --encode.strategy_opts flow to transcribe()."""

    @pytest.fixture(autouse=True)
    def _audio_file(self, tmp_path: Path):
        self.audio = tmp_path / "test.mp3"
        self.audio.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 200)

    @pytest.fixture(autouse=True)
    def _mock_audio(self, monkeypatch):
        """Mock extract_audio and transcribe to capture call args."""
        from unittest.mock import MagicMock

        from mm.common.audio import TranscriptionResult

        mock_audio_result = MagicMock()
        mock_audio_result.path = Path("/tmp/extracted.wav")

        self.mock_extract = MagicMock(return_value=mock_audio_result)
        self.mock_ffmpeg_avail = MagicMock(return_value=True)
        self.mock_transcribe_avail = MagicMock(return_value=True)
        self.mock_transcribe = MagicMock(
            return_value=TranscriptionResult(
                text="Hello world",
                segments=[],
                language="en",
                elapsed_ms=100.0,
                model_size="test",
                device="remote",
                backend="openai",
            )
        )

        monkeypatch.setattr("mm.video.extract_audio", self.mock_extract)
        monkeypatch.setattr("mm.video.ffmpeg_available", self.mock_ffmpeg_avail)
        monkeypatch.setattr("mm.common.audio.transcribe", self.mock_transcribe)
        monkeypatch.setattr("mm.common.audio.transcribe_available", self.mock_transcribe_avail)

    def test_default_backend_is_none(self, isolated_db):
        """mm cat audio.mp3 — backend defaults to None (resolves to openai)."""
        r = runner.invoke(app, ["cat", str(self.audio)])
        assert r.exit_code == 0, r.output
        call_kwargs = self.mock_transcribe.call_args
        assert call_kwargs[1].get("backend") in (None, "openai")

    def test_explicit_backend_mlx(self, isolated_db):
        """mm cat audio.mp3 --encode.backend mlx passes backend='mlx'."""
        r = runner.invoke(app, ["cat", str(self.audio), "--encode.backend", "mlx"])
        assert r.exit_code == 0, r.output
        call_kwargs = self.mock_transcribe.call_args
        assert call_kwargs[1]["backend"] == "mlx"

    def test_encode_model_flag(self, isolated_db):
        """mm cat audio.mp3 --encode.model whisper-1 passes model='whisper-1'."""
        r = runner.invoke(app, ["cat", str(self.audio), "--encode.model", "whisper-1"])
        assert r.exit_code == 0, r.output
        call_kwargs = self.mock_transcribe.call_args
        assert call_kwargs[1]["model"] == "whisper-1"

    def test_strategy_opts_base_url(self, isolated_db):
        """mm cat audio.mp3 --encode.strategy_opts base_url=https://api.openai.com/v1."""
        r = runner.invoke(
            app,
            [
                "cat",
                str(self.audio),
                "--encode.strategy_opts",
                "base_url=https://api.openai.com/v1",
            ],
        )
        assert r.exit_code == 0, r.output
        call_kwargs = self.mock_transcribe.call_args
        assert call_kwargs[1]["base_url"] == "https://api.openai.com/v1"


class TestEffectiveModel:
    """Pipeline-merged model takes precedence over profile default; profile is the fallback."""

    def test_pipeline_pinned_model_wins(self):
        from mm.cat_utils.base_utils import effective_model
        from mm.pipelines.schema import Generate, PipelineSpec

        spec = PipelineSpec(
            kind="image",
            mode="accurate",
            generate=Generate(prompt="x", model="paddleocr-v5"),
        )
        assert effective_model(spec, "profile-default") == "paddleocr-v5"

    def test_profile_default_when_unpinned(self):
        from mm.cat_utils.base_utils import effective_model
        from mm.pipelines.schema import Generate, PipelineSpec

        spec = PipelineSpec(
            kind="image",
            mode="accurate",
            generate=Generate(prompt="x"),
        )
        assert effective_model(spec, "profile-default") == "profile-default"

    def test_no_generate_falls_back_to_profile(self):
        from mm.cat_utils.base_utils import effective_model
        from mm.pipelines.schema import PipelineSpec

        spec = PipelineSpec(kind="image", mode="fast", generate=None)
        assert effective_model(spec, "profile-default") == "profile-default"
