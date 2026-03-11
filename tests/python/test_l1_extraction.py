"""Comprehensive tests for L1 content extraction.

Validates code extraction (line counts, language, preview),
image extraction (dimensions, hash, EXIF), video extraction (ffprobe),
and CLI integration for cat/head/tail/grep.
"""

from __future__ import annotations

import json
import struct
import subprocess
import zlib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vlmctx.cli import app
from vlmctx.context import Context

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


def _write_jpeg(path: Path, width: int = 10, height: int = 10):
    try:
        from PIL import Image
        img = Image.new("RGB", (width, height), color=(64, 128, 0))
        img.save(str(path), format="JPEG")
    except ImportError:
        path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 200 + b"\xff\xd9")


def _ffprobe_available() -> bool:
    try:
        subprocess.run(["ffprobe", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _make_test_video(path: Path, width: int = 320, height: int = 240, duration: float = 1.0, fps: int = 10):
    """Generate a real video via ffmpeg."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=blue:s={width}x{height}:d={duration}:r={fps}",
            "-f", "lavfi",
            "-i", f"sine=frequency=440:duration={duration}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "64k",
            str(path),
        ],
        capture_output=True,
        timeout=30,
    )


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def code_tree(tmp_path: Path) -> Path:
    """Tree with varied code files for L1 code extraction tests."""
    (tmp_path / "hello.py").write_text(
        "#!/usr/bin/env python3\n"
        "def greet(name: str) -> str:\n"
        "    return f'Hello, {name}!'\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    print(greet('world'))\n"
    )
    (tmp_path / "main.rs").write_text(
        "fn main() {\n"
        "    println!(\"Hello, world!\");\n"
        "}\n"
    )
    (tmp_path / "app.js").write_text(
        "const express = require('express');\n"
        "const app = express();\n"
        "app.get('/', (req, res) => res.send('Hi'));\n"
        "app.listen(3000);\n"
    )
    (tmp_path / "config.yaml").write_text("server:\n  port: 8080\n  host: localhost\n")
    (tmp_path / "readme.md").write_text("# Project\n\nA test project with **bold** text.\n\nEnd.\n")
    return tmp_path


@pytest.fixture
def image_tree(tmp_path: Path) -> Path:
    """Tree with valid image files for L1 image extraction tests."""
    _write_png(tmp_path / "small.png", 16, 16)
    _write_png(tmp_path / "wide.png", 1920, 1080)
    _write_jpeg(tmp_path / "photo.jpg", 640, 480)
    return tmp_path


@pytest.fixture
def video_tree(tmp_path: Path) -> Path:
    """Tree with a real video file (requires ffmpeg)."""
    if not _ffmpeg_available():
        pytest.skip("ffmpeg not installed")
    video_path = tmp_path / "test_clip.mp4"
    _make_test_video(video_path, width=320, height=240, duration=2.0, fps=15)
    assert video_path.exists() and video_path.stat().st_size > 100
    return tmp_path


# ── Code L1 Extraction ───────────────────────────────────────────────


class TestCodeL1:
    """L1 extraction for code/text/config files."""

    def test_python_line_count(self, code_tree: Path):
        ctx = Context(code_tree)
        result = ctx._scanner.extract_l1("hello.py")
        assert result.line_count == 6

    def test_python_word_count(self, code_tree: Path):
        ctx = Context(code_tree)
        result = ctx._scanner.extract_l1("hello.py")
        assert result.word_count is not None and result.word_count > 5

    def test_python_language_detection(self, code_tree: Path):
        ctx = Context(code_tree)
        result = ctx._scanner.extract_l1("hello.py")
        assert result.language == "python"

    def test_rust_language_detection(self, code_tree: Path):
        ctx = Context(code_tree)
        result = ctx._scanner.extract_l1("main.rs")
        assert result.language == "rust"

    def test_js_language_detection(self, code_tree: Path):
        ctx = Context(code_tree)
        result = ctx._scanner.extract_l1("app.js")
        assert result.language == "javascript"

    def test_yaml_language_detection(self, code_tree: Path):
        ctx = Context(code_tree)
        result = ctx._scanner.extract_l1("config.yaml")
        assert result.language == "yaml"

    def test_markdown_language_detection(self, code_tree: Path):
        ctx = Context(code_tree)
        result = ctx._scanner.extract_l1("readme.md")
        assert result.language == "markdown"

    def test_text_preview_populated(self, code_tree: Path):
        ctx = Context(code_tree)
        result = ctx._scanner.extract_l1("hello.py")
        assert result.text_preview is not None
        assert "greet" in result.text_preview

    def test_text_preview_length_capped(self, code_tree: Path):
        ctx = Context(code_tree)
        result = ctx._scanner.extract_l1("hello.py")
        assert len(result.text_preview) <= 500

    def test_content_hash_populated(self, code_tree: Path):
        ctx = Context(code_tree)
        result = ctx._scanner.extract_l1("hello.py")
        assert result.content_hash is not None
        assert len(result.content_hash) == 16  # xxh3 hex

    def test_content_hash_deterministic(self, code_tree: Path):
        ctx = Context(code_tree)
        h1 = ctx._scanner.extract_l1("hello.py").content_hash
        h2 = ctx._scanner.extract_l1("hello.py").content_hash
        assert h1 == h2

    def test_different_files_different_hashes(self, code_tree: Path):
        ctx = Context(code_tree)
        h1 = ctx._scanner.extract_l1("hello.py").content_hash
        h2 = ctx._scanner.extract_l1("main.rs").content_hash
        assert h1 != h2

    def test_cat_level1_for_code(self, code_tree: Path):
        ctx = Context(code_tree)
        content = ctx.cat("hello.py", level=1)
        assert "greet" in content
        assert "Lines:" in content

    def test_no_dimensions_for_code(self, code_tree: Path):
        ctx = Context(code_tree)
        result = ctx._scanner.extract_l1("hello.py")
        assert result.dimensions is None

    def test_no_exif_for_code(self, code_tree: Path):
        ctx = Context(code_tree)
        result = ctx._scanner.extract_l1("hello.py")
        assert result.exif_camera is None
        assert result.exif_date is None
        assert result.exif_gps is None


# ── Image L1 Extraction ──────────────────────────────────────────────


class TestImageL1:
    """L1 extraction for image files (dimensions, hash, EXIF)."""

    def test_png_dimensions(self, image_tree: Path):
        ctx = Context(image_tree)
        result = ctx._scanner.extract_l1("small.png")
        assert result.dimensions == "16x16"

    def test_wide_png_dimensions(self, image_tree: Path):
        ctx = Context(image_tree)
        result = ctx._scanner.extract_l1("wide.png")
        assert result.dimensions == "1920x1080"

    def test_jpeg_dimensions(self, image_tree: Path):
        ctx = Context(image_tree)
        result = ctx._scanner.extract_l1("photo.jpg")
        try:
            import PIL  # noqa
            assert result.dimensions is not None
            assert "x" in result.dimensions
        except ImportError:
            pass  # fallback JPEG stub may not have parseable dims

    def test_image_content_hash(self, image_tree: Path):
        ctx = Context(image_tree)
        result = ctx._scanner.extract_l1("small.png")
        assert result.content_hash is not None
        assert len(result.content_hash) == 16

    def test_image_magic_mime(self, image_tree: Path):
        ctx = Context(image_tree)
        result = ctx._scanner.extract_l1("small.png")
        assert result.magic_mime is not None
        assert "png" in result.magic_mime.lower()

    def test_jpeg_magic_mime(self, image_tree: Path):
        ctx = Context(image_tree)
        result = ctx._scanner.extract_l1("photo.jpg")
        if result.magic_mime:
            assert "jpeg" in result.magic_mime.lower() or "jpg" in result.magic_mime.lower()

    def test_image_no_line_count(self, image_tree: Path):
        ctx = Context(image_tree)
        result = ctx._scanner.extract_l1("small.png")
        assert result.line_count is None

    def test_image_no_word_count(self, image_tree: Path):
        ctx = Context(image_tree)
        result = ctx._scanner.extract_l1("small.png")
        assert result.word_count is None

    def test_image_no_language(self, image_tree: Path):
        ctx = Context(image_tree)
        result = ctx._scanner.extract_l1("small.png")
        assert result.language is None

    def test_exif_fields_exist(self, image_tree: Path):
        """EXIF fields should be present (None for synthetic test images)."""
        ctx = Context(image_tree)
        result = ctx._scanner.extract_l1("small.png")
        assert hasattr(result, "exif_camera")
        assert hasattr(result, "exif_date")
        assert hasattr(result, "exif_gps")
        assert hasattr(result, "exif_orientation")

    def test_cat_level1_image(self, image_tree: Path):
        result = runner.invoke(app, [
            "cat", str(image_tree / "small.png"), "--level", "1",
        ])
        assert result.exit_code == 0
        assert "16x16" in result.output

    def test_cat_image_json(self, image_tree: Path):
        result = runner.invoke(app, [
            "cat", str(image_tree / "small.png"), "--level", "1", "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert "16x16" in data[0]["content"]


# ── Video L1 Extraction ──────────────────────────────────────────────


@pytest.mark.skipif(not _ffprobe_available(), reason="ffprobe not installed")
class TestVideoL1:
    """L1 extraction for video files via ffprobe."""

    def test_video_resolution(self, video_tree: Path):
        from vlmctx.video import extract_video_metadata
        meta = extract_video_metadata(video_tree / "test_clip.mp4")
        assert meta.width == 320
        assert meta.height == 240

    def test_video_duration(self, video_tree: Path):
        from vlmctx.video import extract_video_metadata
        meta = extract_video_metadata(video_tree / "test_clip.mp4")
        assert meta.duration_s is not None
        assert 1.5 < meta.duration_s < 3.0  # approx 2s

    def test_video_fps(self, video_tree: Path):
        from vlmctx.video import extract_video_metadata
        meta = extract_video_metadata(video_tree / "test_clip.mp4")
        assert meta.fps is not None
        assert meta.fps > 0

    def test_video_codec(self, video_tree: Path):
        from vlmctx.video import extract_video_metadata
        meta = extract_video_metadata(video_tree / "test_clip.mp4")
        assert meta.video_codec is not None
        assert meta.video_codec == "h264"

    def test_video_has_audio(self, video_tree: Path):
        from vlmctx.video import extract_video_metadata
        meta = extract_video_metadata(video_tree / "test_clip.mp4")
        assert meta.has_audio is True
        assert meta.audio_codec is not None

    def test_video_bitrate(self, video_tree: Path):
        from vlmctx.video import extract_video_metadata
        meta = extract_video_metadata(video_tree / "test_clip.mp4")
        assert meta.bitrate is not None and meta.bitrate > 0

    def test_video_pixel_format(self, video_tree: Path):
        from vlmctx.video import extract_video_metadata
        meta = extract_video_metadata(video_tree / "test_clip.mp4")
        assert meta.pixel_format == "yuv420p"

    def test_cat_level1_video(self, video_tree: Path):
        result = runner.invoke(app, [
            "cat", str(video_tree / "test_clip.mp4"), "--level", "1",
        ])
        assert result.exit_code == 0
        assert "320x240" in result.output
        assert "h264" in result.output

    def test_cat_level1_video_json(self, video_tree: Path):
        result = runner.invoke(app, [
            "cat", str(video_tree / "test_clip.mp4"), "--level", "1", "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        content = data[0]["content"]
        assert "320x240" in content
        assert "h264" in content


# ── Video module edge cases ───────────────────────────────────────────


class TestVideoModule:
    """Test the video.py module directly."""

    def test_nonexistent_file(self):
        from vlmctx.video import extract_video_metadata
        meta = extract_video_metadata("/nonexistent/file.mp4")
        assert meta.width is None
        assert meta.duration_s is None

    def test_invalid_file(self, tmp_path: Path):
        (tmp_path / "garbage.mp4").write_bytes(b"\x00" * 100)
        from vlmctx.video import extract_video_metadata
        meta = extract_video_metadata(tmp_path / "garbage.mp4")
        # ffprobe might partially parse or fail; either way no crash
        assert isinstance(meta.has_audio, bool)

    def test_ffprobe_available_check(self):
        from vlmctx.video import ffprobe_available
        result = ffprobe_available()
        assert isinstance(result, bool)

    def test_parse_fraction(self):
        from vlmctx.video import _parse_fraction
        assert _parse_fraction("30000/1001") == pytest.approx(29.97, abs=0.01)
        assert _parse_fraction("24/1") == 24.0
        assert _parse_fraction("0/0") is None
        assert _parse_fraction("30.0") == 30.0
        assert _parse_fraction("") is None


# ── Cross-level consistency ───────────────────────────────────────────


class TestCrossLevelConsistency:
    """Verify L0 and L1 data agree."""

    def test_l0_dimensions_match_l1(self, image_tree: Path):
        ctx = Context(image_tree)
        df = ctx.to_polars()

        row = df.filter(df["name"] == "small.png")
        l0_w, l0_h = row["width"][0], row["height"][0]

        result = ctx._scanner.extract_l1("small.png")
        l1_dims = result.dimensions
        assert l1_dims == f"{l0_w}x{l0_h}"

    def test_image_kind_has_l0_dims(self, image_tree: Path):
        """PNG images always have dims; JPEG only if Pillow is available."""
        ctx = Context(image_tree)
        df = ctx.to_polars()
        pngs = df.filter(df["name"].str.ends_with(".png"))
        for name in pngs["name"].to_list():
            row = df.filter(df["name"] == name)
            assert row["width"][0] is not None, f"{name} missing width"
            assert row["height"][0] is not None, f"{name} missing height"

    def test_l1_hash_changes_with_content(self, code_tree: Path):
        ctx = Context(code_tree)
        h1 = ctx._scanner.extract_l1("hello.py").content_hash

        (code_tree / "hello.py").write_text("changed content\n")
        ctx2 = Context(code_tree)
        h2 = ctx2._scanner.extract_l1("hello.py").content_hash
        assert h1 != h2


# ── CLI head/tail L1 ─────────────────────────────────────────────────


class TestHeadTailL1:

    def test_head_code_file(self, code_tree: Path):
        result = runner.invoke(app, [
            "cat", str(code_tree / "hello.py"), "-n", "2",
        ])
        assert result.exit_code == 0

    def test_tail_code_file(self, code_tree: Path):
        result = runner.invoke(app, [
            "cat", str(code_tree / "hello.py"), "-n", "-2",
        ])
        assert result.exit_code == 0

    def test_grep_finds_pattern_in_code(self, code_tree: Path):
        result = runner.invoke(app, [
            "grep", "greet", str(code_tree),
        ])
        assert result.exit_code == 0
        assert "greet" in result.output
