"""Tests for `mm cat` auto-detection and dispatch.

Verifies that the CLI correctly auto-detects file types (image, video,
audio, pdf, text) and dispatches to the right handler based on extension
and the --mode flag (fast/accurate).
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest
from mm.cli import app
from mm.utils import AUDIO_EXTS, IMAGE_EXTS, VIDEO_EXTS, file_kind
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


# ── Fast mode (default) ──────────────────────────────────────────────


class TestFastVideo:
    def test_video_metadata(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "clip.mp4")])
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
