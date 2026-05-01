"""Tests for `mm cat` auto-detection and dispatch.

Verifies that the CLI correctly auto-detects file types (image, video,
audio, pdf, text) and dispatches to the right handler based on extension
and the --mode flag (metadata/fast/accurate).
"""

from __future__ import annotations

import json
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


def _write_minimal_mp4(path: Path) -> None:
    """Encode a 1-frame, 16x16 mp4 PyAV can probe.

    The previous ``b"\\x00" * 200`` placeholder relied on ffprobe being
    forgiving; the new PyAV-based ``mm.video.probe`` is stricter, so the
    fixture must be a real (tiny) mp4 file.
    """
    import av
    import numpy as np

    container = av.open(str(path), mode="w")
    try:
        stream = container.add_stream("mpeg4", rate=24)
        stream.width = 16
        stream.height = 16
        stream.pix_fmt = "yuv420p"
        frame = av.VideoFrame.from_ndarray(
            np.zeros((16, 16, 3), dtype=np.uint8),
            format="rgb24",
        )
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    finally:
        container.close()


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
    _write_png(tmp_path / "photo.png", 64, 48)
    _write_minimal_mp4(tmp_path / "clip.mp4")
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


# ── Metadata mode (default) ─────────────────────────────────────────


class TestMetadataDefault:
    """The default `--mode metadata` returns local extraction with no LLM call."""

    def test_video_metadata_default(self, mixed_dir: Path):
        """No mode flag → metadata mode → native MP4 parse, no LLM."""
        r = runner.invoke(app, ["cat", str(mixed_dir / "clip.mp4")])
        assert r.exit_code == 0

    def test_explicit_metadata_mode(self, mixed_dir: Path):
        """Passing `-m metadata` is identical to omitting `-m`."""
        r_default = runner.invoke(app, ["cat", str(mixed_dir / "clip.mp4")])
        r_explicit = runner.invoke(app, ["cat", str(mixed_dir / "clip.mp4"), "-m", "metadata"])
        assert r_default.exit_code == 0
        assert r_explicit.exit_code == 0

    def test_text_passthrough_default(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "readme.md")])
        assert r.exit_code == 0
        assert "Title" in r.output

    def test_code_passthrough_default(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "main.py")])
        assert r.exit_code == 0
        assert "def run" in r.output

    def test_metadata_does_not_call_llm(self, monkeypatch, mixed_dir: Path):
        """Default `metadata` mode must never instantiate the LLM backend.

        The fast pipeline for images calls an LLM, but metadata mode short-
        circuits before resolving any pipeline. We assert this by replacing
        `LlmBackend` with a sentinel that raises if instantiated.
        """
        from mm import llm

        class _Sentinel:
            def __init__(self, *args, **kwargs):
                raise AssertionError(
                    "LlmBackend was constructed under --mode metadata; the "
                    "default mode must not invoke an LLM."
                )

        monkeypatch.setattr(llm, "LlmBackend", _Sentinel)

        r = runner.invoke(app, ["cat", str(mixed_dir / "photo.png")])
        assert r.exit_code == 0

    def test_metadata_mode_json_emits_mode_field(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "main.py"), "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert isinstance(data, list) and data
        assert data[0].get("mode") == "metadata"

    def test_metadata_image_json_emits_mode_field(self, mixed_dir: Path):
        r = runner.invoke(app, ["cat", str(mixed_dir / "photo.png"), "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data[0].get("mode") == "metadata"


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


class TestCatDocumentPdf:
    """CLI smoke: PDF metadata + fast paths both use pypdfium2 page text (not mocked)."""

    def test_pdf_metadata_json_extracts_text(self, tmp_path: Path):
        """Default mode (metadata) extracts PDF text via pypdfium2 — same path as fast."""
        pdf = tmp_path / "hello.pdf"
        _minimal_single_page_pdf(pdf)
        r = runner.invoke(app, ["cat", str(pdf), "--format", "json"])
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert len(data) == 1
        assert data[0].get("mode") == "metadata"
        assert "Hello" in data[0].get("content", "")

    def test_pdf_fast_json_extracts_text(self, tmp_path: Path):
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
        body = data[0].get("content", "")
        assert "Hello" in body


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
        # Error must enumerate all three valid modes so users discover the new
        # `metadata` default.
        for token in ("metadata", "fast", "accurate"):
            assert token in combined.lower()
