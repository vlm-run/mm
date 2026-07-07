"""Tests for mm.encoders — registry, discovery, video/document/audio encoders, tile."""

from __future__ import annotations

import base64
import struct
import zlib
from pathlib import Path
from unittest.mock import patch

import pytest


def _make_png(path: Path, w: int, h: int) -> Path:
    """Create a minimal valid PNG file."""
    png_sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
    raw_data = b""
    for _ in range(h):
        raw_data += b"\x00" + b"\x00" * (w * 3)
    compressed = zlib.compress(raw_data)
    idat_crc = zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF
    idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc)
    iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
    path.write_bytes(png_sig + ihdr + idat + iend)
    return path


def _make_jpeg(path: Path, w: int, h: int) -> Path:
    from PIL import Image

    img = Image.new("RGB", (w, h), color=(128, 64, 32))
    img.save(path, "JPEG", quality=80)
    return path


# ---------------------------------------------------------------------------
# Registry — additional coverage
# ---------------------------------------------------------------------------


class TestRegistryExtended:
    def test_custom_encoders_discovered(self):
        from mm.encoders import list_strategies

        names = list_strategies()
        assert "tile" in names
        # ``shots`` + ``shot-mosaic`` are the current shot-aware
        # encoders (formerly ``shot-frames`` / ``shot-mosaic``).
        assert "shots" in names
        assert "shot-mosaic" in names

    def test_shot_encoders_are_video_type(self):
        from mm.encoders import list_strategies

        video_names = list_strategies(kind="video")
        assert "shots" in video_names
        assert "shot-mosaic" in video_names

    def test_tile_is_image_type(self):
        from mm.encoders import list_strategies

        image_names = list_strategies(kind="image")
        assert "tile" in image_names

    def test_resolve_provider_default_openai(self):
        from mm.encoders import resolve_provider

        with patch("mm.profile.get_active_profile_name", side_effect=Exception("no config")):
            assert resolve_provider() == "openai"

    def test_resolve_provider_gemini(self):
        from mm.encoders import resolve_provider

        with (
            patch("mm.profile.get_active_profile_name", return_value="my-gemini-profile"),
            patch("mm.profile.get_profile_by_name", return_value={"model": "some-model"}),
        ):
            assert resolve_provider() == "gemini"

    def test_resolve_provider_model_override_gemini(self):
        """generate_model containing 'gemini' forces gemini provider regardless of profile name."""
        from mm.encoders import resolve_provider

        with (
            patch("mm.profile.get_active_profile_name", return_value="default"),
            patch("mm.profile.get_profile_by_name", return_value={"model": "gpt-4o"}),
        ):
            assert resolve_provider("gemini-2.0-flash") == "gemini"

    def test_resolve_provider_model_override_non_gemini(self):
        """Non-gemini model with non-gemini profile → openai."""
        from mm.encoders import resolve_provider

        with (
            patch("mm.profile.get_active_profile_name", return_value="default"),
            patch("mm.profile.get_profile_by_name", return_value={"model": "gpt-4o"}),
        ):
            assert resolve_provider("gpt-4o") == "openai"

    def test_load_strategy_file_caching(self, tmp_path):
        from mm.encoders import _LOADED_SOURCES, load_strategy_file

        strat_file = tmp_path / "cached_encoder.py"
        strat_file.write_text(
            "from mm.encoders import register_encoder\n"
            "@register_encoder(name='test-cached-enc', kind='image')\n"
            "def test_cached(path, **kw):\n"
            "    yield {'role': 'user', 'content': []}\n"
        )
        names1 = load_strategy_file(strat_file)
        names2 = load_strategy_file(strat_file)
        assert names1 == names2
        assert str(strat_file.resolve()) in _LOADED_SOURCES

    def test_openai_default_encoders_resolve(self):
        from mm.encoders import get
        from mm.refs_messages import OPENAI_DEFAULT_ENCODERS

        resolved = {
            kind: (name, get(name, kind) is not None)
            for kind, name in OPENAI_DEFAULT_ENCODERS.items()
        }
        assert resolved == {
            "image": ("resize", True),
            "video": ("mosaic", True),
            "document": ("rasterize", True),
            "audio": ("base64", True),
        }


# ---------------------------------------------------------------------------
# Image encoder — extended coverage
# ---------------------------------------------------------------------------


class TestImageEncoders:
    def test_gemini_image_part_format(self):
        from mm.encoders.image import _gemini_image_part

        part = _gemini_image_part("abc123", "image/jpeg")
        assert "inline_data" in part
        assert part["inline_data"]["mime_type"] == "image/jpeg"
        assert part["inline_data"]["data"] == "abc123"

    def test_image_part_openai(self):
        from mm.encoders.image import _image_part

        part = _image_part("abc", "image/jpeg", "openai")
        assert part["type"] == "image_url"
        assert "data:image/jpeg;base64,abc" in part["image_url"]["url"]

    def test_image_part_gemini(self):
        from mm.encoders.image import _image_part

        part = _image_part("abc", "image/jpeg", "gemini")
        assert "inline_data" in part
        assert part["inline_data"]["data"] == "abc"

    def test_encode_pil_image_png_alpha(self, tmp_path):
        from mm.encoders.image import _encode_pil_image
        from PIL import Image

        img = Image.new("RGBA", (10, 10), (255, 0, 0, 128))
        b64, mime = _encode_pil_image(img, tmp_path / "test.png")
        assert mime == "image/png"
        decoded = base64.b64decode(b64)
        assert decoded[:4] == b"\x89PNG"

    def test_encode_pil_image_jpeg_converts_grayscale(self, tmp_path):
        from mm.encoders.image import _encode_pil_image
        from PIL import Image

        img = Image.new("L", (10, 10), 128)
        b64, mime = _encode_pil_image(img, tmp_path / "test.jpg")
        assert mime == "image/jpeg"


class TestAudioEncoders:
    def test_audio_strategies_registered(self):
        from mm.encoders import list_strategies

        assert sorted(list_strategies(kind="audio")) == ["gemini-native", "native", "transcribe"]

    def test_audio_base64_and_gemini_native_emit_input_audio(self, tmp_path):
        from mm.encoders import get

        audio = tmp_path / "sample.mp3"
        audio.write_bytes(b"ID3" + b"\x00" * 32)

        for name in ("base64", "gemini-native"):
            strat = get(name, "audio")
            with patch("mm.video.pyav_runnable", return_value=False):
                messages = list(strat.encode(audio))
            assert len(messages) == 1
            content = messages[0]["content"]
            assert len(content) == 1
            part = content[0]
            assert part["type"] == "input_audio"
            assert part["input_audio"]["format"] == "mp3"


# ---------------------------------------------------------------------------
# TileOverview encoder
# ---------------------------------------------------------------------------


class TestTileOverview:
    def test_small_image_single_part(self, tmp_path):
        """Image smaller than max_width yields only the overview, no tiles."""
        from mm.encoders import get

        img = _make_jpeg(tmp_path / "small.jpg", 100, 80)
        strat = get("tile", "image")
        messages = list(strat.encode(img, max_width=1024))
        assert len(messages) == 1
        msg = messages[0]
        assert msg["role"] == "user"
        content = msg["content"]
        image_parts = [p for p in content if p.get("type") == "image_url" or "inline_data" in p]
        assert len(image_parts) == 1

    def test_generate_model_gemini_produces_inline_data(self, tmp_path):
        """generate_model='gemini-flash' routes image parts to inline_data format."""
        from mm.encoders import get

        img = _make_jpeg(tmp_path / "img.jpg", 100, 80)
        strat = get("tile", "image")
        messages = list(strat.encode(img, max_width=1024, generate_model="gemini-2.0-flash"))
        content = messages[0]["content"]
        image_parts = [p for p in content if "inline_data" in p]
        assert len(image_parts) == 1

    def test_generate_model_openai_produces_image_url(self, tmp_path):
        """generate_model='gpt-4o' routes image parts to image_url format."""
        from mm.encoders import get

        img = _make_jpeg(tmp_path / "img.jpg", 100, 80)
        strat = get("resize", "image")
        with (
            patch("mm.profile.get_active_profile_name", return_value="default"),
            patch("mm.profile.get_profile_by_name", return_value={"model": "gpt-4o"}),
        ):
            messages = list(strat.encode(img, max_width=1024, generate_model="gpt-4o"))
        content = messages[0]["content"]
        image_parts = [p for p in content if p.get("type") == "image_url"]
        assert len(image_parts) == 1

    def test_large_image_overview_plus_tiles(self, tmp_path):
        """Large image yields overview + N tiles in a single message."""
        from mm.encoders import get

        img = _make_jpeg(tmp_path / "large.jpg", 2048, 2048)
        strat = get("tile", "image")
        messages = list(strat.encode(img, max_width=1024))
        assert len(messages) == 1
        msg = messages[0]
        content = msg["content"]
        text_parts = [p for p in content if p.get("type") == "text"]
        image_parts = [p for p in content if p.get("type") == "image_url" or "inline_data" in p]
        assert len(text_parts) >= 1
        assert (
            "overview" in text_parts[0]["text"].lower() or "tile" in text_parts[0]["text"].lower()
        )
        assert len(image_parts) >= 5

    def test_exact_tile_count(self, tmp_path):
        """4096x4096 at max_width=1024 should give 1 overview + 16 tiles = 17 image parts."""
        from mm.encoders import get

        img = _make_jpeg(tmp_path / "huge.jpg", 4096, 4096)
        strat = get("tile", "image")
        messages = list(strat.encode(img, max_width=1024))
        assert len(messages) == 1
        content = messages[0]["content"]
        image_parts = [p for p in content if p.get("type") == "image_url" or "inline_data" in p]
        assert len(image_parts) == 17


# ---------------------------------------------------------------------------
# Video encoder pure functions
# ---------------------------------------------------------------------------


class TestVideoTimestamps:
    def test_uniform_timestamps_basic(self):
        from mm.encoders.video import uniform_timestamps

        ts = uniform_timestamps(10.0, 1.0)
        assert len(ts) == 10
        assert ts[0] == pytest.approx(0.0)
        assert ts[-1] == pytest.approx(9.0)

    def test_uniform_timestamps_half_fps(self):
        from mm.encoders.video import uniform_timestamps

        ts = uniform_timestamps(10.0, 0.5)
        assert len(ts) == 5
        assert ts[1] == pytest.approx(2.0)

    def test_uniform_timestamps_zero_duration(self):
        from mm.encoders.video import uniform_timestamps

        ts = uniform_timestamps(0.0, 1.0)
        assert ts == []

    def test_uniform_timestamps_range_basic(self):
        from mm.encoders.video import uniform_timestamps_range

        ts = uniform_timestamps_range(10.0, 20.0, 5)
        assert len(ts) == 5
        assert ts[0] == pytest.approx(10.0)
        assert all(10.0 <= t <= 20.0 for t in ts)

    def test_uniform_timestamps_range_single(self):
        from mm.encoders.video import uniform_timestamps_range

        ts = uniform_timestamps_range(5.0, 10.0, 1)
        assert len(ts) == 1
        assert ts[0] == pytest.approx(5.0)


# NOTE: ``TestVideoFrameSample`` and ``TestVideoChunk`` were removed when the
# old ffmpeg-CLI-driven encoders ``frame-sample`` and ``video-chunk`` were
# replaced by the PyAV-based ``frames`` / ``chunked`` family.
# Equivalent behaviour is exercised end-to-end in ``test_video_p0.py`` and
# ``test_video_encoders.py`` against real video fixtures.


# ---------------------------------------------------------------------------
# Document encoders
# ---------------------------------------------------------------------------


class TestDocumentRasterize:
    def test_pypdfium_not_installed(self, tmp_path):
        from mm.encoders import get

        doc = tmp_path / "test.pdf"
        doc.write_bytes(b"%PDF-1.4 fake")
        strat = get("rasterize", "document")
        with patch("mm.encoders.document.rasterize.rasterize_pages", return_value=[]):
            messages = list(strat.encode(doc, mode="accurate"))
            assert len(messages) == 1
            assert "No pages" in messages[0]["content"][0]["text"]

    @pytest.mark.skip(reason="slow: rasterizes real PDF pages")
    def test_pages_batched(self, tmp_path):
        from mm.encoders import get

        doc = tmp_path / "test.pdf"
        doc.write_bytes(b"%PDF-1.4 fake")
        fake_pages = [(base64.b64encode(b"\xff").decode(), "image/jpeg")] * 10

        strat = get("rasterize", "document")
        with patch("mm.encoders.document.rasterize.rasterize_pages", return_value=iter(fake_pages)):
            messages = list(strat.encode(doc, pages_per_message=4))
            assert len(messages) == 3
            for msg in messages:
                text_parts = [p for p in msg["content"] if p.get("type") == "text"]
                assert "Document pages" in text_parts[0]["text"]


class TestDocumentRasterizeText:
    def test_interleaves_text(self, tmp_path):
        from mm.encoders import get

        doc = tmp_path / "test.pdf"
        doc.write_bytes(b"%PDF-1.4 fake")
        fake_pages = [(base64.b64encode(b"\xff").decode(), "image/jpeg")] * 2
        fake_texts = ["Page one text.", "Page two text."]

        strat = get("rasterize-text", "document")
        with (
            patch("mm.encoders.document.rasterize.rasterize_pages", return_value=iter(fake_pages)),
            patch("mm.encoders.document.rasterize.extract_page_texts", return_value=fake_texts),
        ):
            messages = list(strat.encode(doc, mode="accurate", pages_per_message=4))
            assert len(messages) == 1
            content = messages[0]["content"]
            text_contents = [p["text"] for p in content if p.get("type") == "text"]
            page_text_parts = [t for t in text_contents if "[Page" in t]
            assert len(page_text_parts) == 2
            assert "Page one text" in page_text_parts[0]


# ---------------------------------------------------------------------------
# Gemini encoders
# ---------------------------------------------------------------------------


class TestGeminiEncoders:
    def test_gemini_inline_data_part(self):
        from mm.encoders.gemini import _gemini_inline_data_part

        part = _gemini_inline_data_part(b"hello", "video/mp4")
        assert "inline_data" in part
        assert part["inline_data"]["mime_type"] == "video/mp4"
        decoded = base64.b64decode(part["inline_data"]["data"])
        assert decoded == b"hello"

    def test_gemini_video_python_fallback(self, tmp_path):
        """GeminiVideo falls back to pure-Python when Rust is unavailable."""
        from mm.encoders.gemini import GeminiVideo

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00\x00\x00\x18ftypmp4" + b"\x00" * 100)
        strat = GeminiVideo()
        messages = list(strat.encode(video))
        assert len(messages) == 1
        content = messages[0]["content"]
        assert any("inline_data" in p for p in content)

    def test_gemini_doc_python_fallback(self, tmp_path):
        """GeminiDocument falls back to pure-Python when Rust is unavailable."""
        from mm.encoders.gemini import GeminiDocument

        doc = tmp_path / "test.pdf"
        doc.write_bytes(b"%PDF-1.4 content here")
        strat = GeminiDocument()
        messages = list(strat.encode(doc, mode="accurate"))
        assert len(messages) == 1
        content = messages[0]["content"]
        assert any("inline_data" in p for p in content)

    def test_gemini_video_chunked_short_video(self, tmp_path):
        # ``gemini-chunked`` calls ``mm.video.probe()`` (PyAV) — not
        # ``mm.ffmpeg.probe_duration`` anymore.  Mock probe to short-circuit
        # to the single-Part fast path without parsing the (fake) bytes.
        from mm.encoders import get
        from mm.video import VideoInfo

        video = tmp_path / "short.mp4"
        video.write_bytes(b"\x00" * 100)
        info = VideoInfo(
            path=video,
            duration=30.0,
            fps=24.0,
            width=320,
            height=240,
            num_frames=720,
            codec="h264",
            has_audio=False,
        )
        strat = get("gemini-chunked", "video")
        with patch("mm.video.probe", return_value=info):
            messages = list(strat.encode(video, max_seconds=120))
            assert len(messages) == 1
            assert any("inline_data" in p for p in messages[0]["content"])

    def test_gemini_video_chunked_pyav_unavailable(self, tmp_path):
        # When PyAV is unavailable the encoder yields a graceful diagnostic
        # message rather than crashing.  Replaces the old
        # ``ffmpeg-unavailable`` test which targeted a code path the
        # PyAV-based encoder no longer has.
        from mm.encoders import get

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        strat = get("gemini-chunked", "video")
        with patch("mm.video.pyav_runnable", return_value=False):
            messages = list(strat.encode(video))
            assert len(messages) == 1
            assert "PyAV not runnable" in messages[0]["content"][0]["text"]


class TestNativeVideoEncoder:
    def test_native_video_passthrough(self, tmp_path):
        from mm.encoders import get

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00\x00\x00\x18ftypmp4" + b"\x00" * 64)
        strat = get("native", "video")
        messages = list(strat.encode(video))
        assert len(messages) == 1
        content = messages[0]["content"]
        assert len(content) == 1
        part = content[0]
        assert part["type"] == "video_url"
        url = part["video_url"]["url"]
        assert url.startswith("data:video/mp4;base64,")


# NOTE: ``TestShotTimestamps``, ``TestShotFrames`` and ``TestShotMosaic`` were
# removed when the ``mm.encoders.video.shot`` module was replaced by the
# unified PyAV-based shots/mosaic stack (``shots``, ``shots-w-
# transcript``, ``shot-mosaic``, ``shot-mosaic-w-transcript``).
# Replacement coverage:
#   * Shot detection / boundary sampling — ``mm.common.video.shot_detection``
#     is exercised by ``test_video_p0.py::TestSceneDetectCache``.
#   * Per-shot frame / mosaic encoding — covered end-to-end in
#     ``test_video_p0.py::TestBundledShots`` against real bakery.mp4.
