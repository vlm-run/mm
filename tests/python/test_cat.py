"""Tests for `mm cat` auto-detection and dispatch.

Verifies that the CLI correctly auto-detects file types (image, video,
audio, pdf, text) and dispatches to the right handler based on extension
and the --mode flag (fast/accurate).
"""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import pytest
from mm.cli import app
from mm.commands.cat import _file_kind
from mm.constants import AUDIO_EXTS, IMAGE_EXTS, VIDEO_EXTS
from typer.testing import CliRunner

runner = CliRunner()


# ── Helpers ───────────────────────────────────────────────────────────


def _write_png(path: Path, width: int, height: int):
    raw = b""
    for _ in range(height):
        raw += b"\x00" + b"\x80\x00\x40" * width
    compressed = zlib.compress(raw)

    def _chunk(ctype, data):
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", ihdr_data)
    png += _chunk(b"IDAT", compressed)
    png += _chunk(b"IEND", b"")
    path.write_bytes(png)


# ── Fixture: mixed directory ──────────────────────────────────────────


@pytest.fixture
def mixed_dir(tmp_path: Path) -> Path:
    """Directory with one file per major type."""
    _write_png(tmp_path / "photo.png", 64, 48)
    (tmp_path / "clip.mp4").write_bytes(b"\x00" * 200)
    (tmp_path / "track.mp3").write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 200)
    (tmp_path / "readme.md").write_text("# Title\n\nHello world.\n")
    (tmp_path / "main.py").write_text("def run():\n    return 42\n")
    (tmp_path / "config.toml").write_text("[server]\nport = 3000\n")
    return tmp_path


# ── _file_kind unit tests ────────────────────────────────────────────


class TestFileKindDetection:
    """Verify _file_kind classifies by extension."""

    @pytest.mark.parametrize("ext", sorted(IMAGE_EXTS))
    def test_image_extensions(self, ext):
        assert _file_kind(Path(f"test{ext}")) == "image"

    @pytest.mark.parametrize("ext", sorted(VIDEO_EXTS))
    def test_video_extensions(self, ext):
        assert _file_kind(Path(f"test{ext}")) == "video"

    @pytest.mark.parametrize("ext", sorted(AUDIO_EXTS))
    def test_audio_extensions(self, ext):
        assert _file_kind(Path(f"test{ext}")) == "audio"

    def test_pdf(self):
        assert _file_kind(Path("paper.pdf")) == "document"

    @pytest.mark.parametrize("ext", [".py", ".rs", ".js", ".md", ".toml", ".txt", ".csv"])
    def test_text_fallback(self, ext):
        assert _file_kind(Path(f"file{ext}")) == "text"


# ── Fast mode (default) ──────────────────────────────────────────────


class TestFastImage:
    def test_image_shows_dimensions(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "photo.png"), "--no-cache"])
        assert r.exit_code == 0
        assert "64x48" in r.output

    def test_image_shows_hash(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "photo.png"), "--format", "json"])
        data = json.loads(r.output)
        assert "Hash" in data[0]["content"] or "hash" in data[0]["content"].lower()

    def test_image_shows_mime(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "photo.png")])
        assert "png" in r.output.lower()


class TestFastVideo:
    def test_video_metadata(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "clip.mp4")])
        assert r.exit_code == 0


class TestFastAudio:
    def test_audio_metadata(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "track.mp3")])
        assert r.exit_code == 0


class TestFastText:
    def test_text_passthrough(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "readme.md")])
        assert r.exit_code == 0
        assert "Title" in r.output

    def test_code_passthrough(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "main.py")])
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

    def test_head_on_image_limits_output(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "photo.png"), "-n", "1"])
        assert r.exit_code == 0
        lines = r.output.strip().splitlines()
        assert len(lines) == 1


# ── Multiple files ────────────────────────────────────────────────────


class TestMultiFile:
    def test_two_files_json(self, mixed_dir: Path):
        r = runner.invoke(
            app,
            [
                "cat",
                str(mixed_dir / "main.py"),
                str(mixed_dir / "readme.md"),
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert len(data) == 2
        paths = {d["path"] for d in data}
        assert any("main.py" in p for p in paths)
        assert any("readme.md" in p for p in paths)

    def test_mixed_types_json(self, mixed_dir: Path):
        r = runner.invoke(
            app,
            [
                "cat",
                str(mixed_dir / "main.py"),
                str(mixed_dir / "photo.png"),
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert len(data) == 2


# ── Error handling ────────────────────────────────────────────────────


class TestErrors:
    def test_no_files_exits_nonzero(self):
        r = runner.invoke(app, ["cat"])
        assert r.exit_code != 0

    def test_nonexistent_file(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "nope.txt")])
        combined = (r.output or "") + (getattr(r, "stderr", "") or "")
        assert "not found" in combined.lower()

    def test_mix_of_existing_and_missing(self, mixed_dir: Path):
        r = runner.invoke(
            app,
            [
                "cat",
                str(mixed_dir / "main.py"),
                str(mixed_dir / "missing.txt"),
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0
        assert "not found" in r.output.lower()
        assert "main.py" in r.output

    def test_invalid_mode(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "main.py"), "-m", "bogus"])
        assert r.exit_code != 0


# ── Accurate mode cache handling ──────────────────────────────────────


class TestAccurateCacheError:
    """Verify that error results from accurate mode are not persisted in the cache."""

    def test_error_result_not_cached(self, tmp_path: Path):
        from unittest.mock import MagicMock, patch

        from mm.commands.cat import _CatOpts, _run_accurate

        txt = tmp_path / "test.txt"
        txt.write_text("hello")

        opts = _CatOpts(
            n=None,
            output_dir=None,
            mode="accurate",
            no_cache=False,
            format="rich",
            encode_overrides={},
            generate_overrides={},
            pipelines={},
        )

        mock_db = MagicMock()
        mock_db.get_l2.return_value = None

        with (
            patch("mm.commands.cat._accurate_dispatch", return_value="[LLM error: connection refused]"),
            patch("mm.store.util.get_content_hash", return_value="fakehash123"),
            patch("mm.store.db.MmDatabase", return_value=mock_db),
            patch("mm.profile.get_profile") as mock_profile,
        ):
            mock_profile.return_value.name = "default"
            mock_profile.return_value.model = "test-model"
            result = _run_accurate(txt, "text", opts)

        assert result == "[LLM error: connection refused]"
        mock_db.put_l2.assert_not_called()

    def test_success_result_is_cached(self, tmp_path: Path):
        from unittest.mock import MagicMock, patch

        from mm.commands.cat import _CatOpts, _run_accurate

        txt = tmp_path / "test.txt"
        txt.write_text("hello")

        opts = _CatOpts(
            n=None,
            output_dir=None,
            mode="accurate",
            no_cache=False,
            format="rich",
            encode_overrides={},
            generate_overrides={},
            pipelines={},
        )

        mock_db = MagicMock()
        mock_db.get_l2.return_value = None

        with (
            patch("mm.commands.cat._accurate_dispatch", return_value="A beautiful sunset over the ocean."),
            patch("mm.store.util.get_content_hash", return_value="fakehash123"),
            patch("mm.store.db.MmDatabase", return_value=mock_db),
            patch("mm.profile.get_profile") as mock_profile,
        ):
            mock_profile.return_value.name = "default"
            mock_profile.return_value.model = "test-model"
            result = _run_accurate(txt, "text", opts)

        assert result == "A beautiful sunset over the ocean."
        mock_db.put_l2.assert_called_once_with(
            uri=str(txt.resolve()),
            content_hash="fakehash123",
            profile="default",
            model="test-model",
            content="A beautiful sunset over the ocean.",
            mode="accurate",
            detail=False,
            extra="",
        )

    def test_various_error_prefixes_not_cached(self, tmp_path: Path):
        from unittest.mock import MagicMock, patch

        from mm.commands.cat import _CatOpts, _run_accurate

        txt = tmp_path / "test.txt"
        txt.write_text("hello")

        opts = _CatOpts(
            n=None,
            output_dir=None,
            mode="accurate",
            no_cache=False,
            format="rich",
            encode_overrides={},
            generate_overrides={},
            pipelines={},
        )

        error_messages = [
            "[Video L2 failed: timeout]",
            "[ffmpeg not found — cannot process video.mp4]",
            "[whisper not installed — pip install mm[extract]]",
            "[LLM error: 401 Unauthorized]",
        ]

        for error_msg in error_messages:
            mock_db = MagicMock()
            mock_db.get_l2.return_value = None

            with (
                patch("mm.commands.cat._accurate_dispatch", return_value=error_msg),
                patch("mm.store.util.get_content_hash", return_value="hash"),
                patch("mm.store.db.MmDatabase", return_value=mock_db),
                patch("mm.profile.get_profile") as mock_profile,
            ):
                mock_profile.return_value.name = "default"
                mock_profile.return_value.model = "m"
                _run_accurate(txt, "text", opts)

            mock_db.put_l2.assert_not_called()


# ── JSON output includes mode ────────────────────────────────────────


class TestJsonOutput:
    def test_json_includes_mode(self, mixed_dir: Path):
        r = runner.invoke(
            app,
            ["cat", str(mixed_dir / "main.py"), "--format", "json"],
        )
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data[0]["mode"] == "fast"

    def test_json_accurate_mode(self, mixed_dir: Path):
        r = runner.invoke(
            app,
            ["cat", str(mixed_dir / "main.py"), "--format", "json", "-m", "accurate"],
        )
        # Will fail at LLM step, but we can check the error includes mode
        # or it completes if the pipeline is encode-only
        assert r.exit_code == 0
