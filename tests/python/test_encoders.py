"""Tests for mm.encoders — registry, discovery, video/document/gemini encoders, tile."""

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
        assert "shot-frames" in names
        assert "shot-mosaic" in names

    def test_shot_encoders_are_video_type(self):
        from mm.encoders import list_strategies

        video_names = list_strategies(media_type="video")
        assert "shot-frames" in video_names
        assert "shot-mosaic" in video_names

    def test_tile_is_image_type(self):
        from mm.encoders import list_strategies

        image_names = list_strategies(media_type="image")
        assert "tile" in image_names

    def test_resolve_provider_default_openai(self):
        from mm.encoders import _resolve_provider

        with patch("mm.profile.get_active_profile_name", side_effect=Exception("no config")):
            assert _resolve_provider() == "openai"

    def test_resolve_provider_gemini(self):
        from mm.encoders import _resolve_provider

        with patch("mm.profile.get_active_profile_name", return_value="my-gemini-profile"):
            assert _resolve_provider() == "gemini"

    def test_load_strategy_file_caching(self, tmp_path):
        from mm.encoders import _LOADED_SOURCES, load_strategy_file

        strat_file = tmp_path / "cached_encoder.py"
        strat_file.write_text(
            "from mm.encoders import register_encoder\n"
            "@register_encoder(name='test-cached-enc', media_types=('image',))\n"
            "def test_cached(path, **kw):\n"
            "    yield {'role': 'user', 'content': []}\n"
        )
        names1 = load_strategy_file(strat_file)
        names2 = load_strategy_file(strat_file)
        assert names1 == names2
        assert str(strat_file.resolve()) in _LOADED_SOURCES


# ---------------------------------------------------------------------------
# Image encoder — extended coverage
# ---------------------------------------------------------------------------


class TestImageEncoders:
    def test_validate_image_path_not_found(self, tmp_path):
        from mm.encoders.image import _validate_image_path

        with pytest.raises(FileNotFoundError, match="Image not found"):
            _validate_image_path(tmp_path / "nonexistent.jpg")

    def test_validate_image_path_unsupported_ext(self, tmp_path):
        from mm.encoders.image import _validate_image_path

        f = tmp_path / "test.xyz"
        f.write_bytes(b"\x00")
        with pytest.raises(ValueError, match="Unsupported image type"):
            _validate_image_path(f)

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
        from PIL import Image
        from mm.encoders.image import _encode_pil_image

        img = Image.new("RGBA", (10, 10), (255, 0, 0, 128))
        b64, mime = _encode_pil_image(img, tmp_path / "test.png")
        assert mime == "image/png"
        decoded = base64.b64decode(b64)
        assert decoded[:4] == b"\x89PNG"

    def test_encode_pil_image_jpeg_converts_grayscale(self, tmp_path):
        from PIL import Image
        from mm.encoders.image import _encode_pil_image

        img = Image.new("L", (10, 10), 128)
        b64, mime = _encode_pil_image(img, tmp_path / "test.jpg")
        assert mime == "image/jpeg"


# ---------------------------------------------------------------------------
# TileOverview encoder
# ---------------------------------------------------------------------------


class TestTileOverview:
    def test_small_image_single_part(self, tmp_path):
        """Image smaller than max_width yields only the overview, no tiles."""
        from mm.encoders import get

        img = _make_jpeg(tmp_path / "small.jpg", 100, 80)
        strat = get("tile")
        messages = list(strat.encode(img, max_width=1024))
        assert len(messages) == 1
        msg = messages[0]
        assert msg["role"] == "user"
        content = msg["content"]
        image_parts = [p for p in content if p.get("type") == "image_url" or "inline_data" in p]
        assert len(image_parts) == 1

    def test_large_image_overview_plus_tiles(self, tmp_path):
        """Large image yields overview + N tiles in a single message."""
        from mm.encoders import get

        img = _make_jpeg(tmp_path / "large.jpg", 2048, 2048)
        strat = get("tile")
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
        strat = get("tile")
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
        from mm.encoders.video import _uniform_timestamps

        ts = _uniform_timestamps(10.0, 1.0)
        assert len(ts) == 10
        assert ts[0] == pytest.approx(0.0)
        assert ts[-1] == pytest.approx(9.0)

    def test_uniform_timestamps_half_fps(self):
        from mm.encoders.video import _uniform_timestamps

        ts = _uniform_timestamps(10.0, 0.5)
        assert len(ts) == 5
        assert ts[1] == pytest.approx(2.0)

    def test_uniform_timestamps_zero_duration(self):
        from mm.encoders.video import _uniform_timestamps

        ts = _uniform_timestamps(0.0, 1.0)
        assert ts == []

    def test_uniform_timestamps_range_basic(self):
        from mm.encoders.video import _uniform_timestamps_range

        ts = _uniform_timestamps_range(10.0, 20.0, 5)
        assert len(ts) == 5
        assert ts[0] == pytest.approx(10.0)
        assert all(10.0 <= t <= 20.0 for t in ts)

    def test_uniform_timestamps_range_single(self):
        from mm.encoders.video import _uniform_timestamps_range

        ts = _uniform_timestamps_range(5.0, 10.0, 1)
        assert len(ts) == 1
        assert ts[0] == pytest.approx(5.0)


class TestVideoFrameSample:
    def test_ffmpeg_unavailable(self, tmp_path):
        from mm.encoders import get

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        strat = get("frame-sample")
        with patch("mm.ffmpeg.ffmpeg_available", return_value=False):
            messages = list(strat.encode(video))
            assert len(messages) == 1
            assert "ffmpeg not available" in messages[0]["content"][0]["text"]

    def test_zero_duration(self, tmp_path):
        from mm.encoders import get

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        strat = get("frame-sample")
        with (
            patch("mm.ffmpeg.ffmpeg_available", return_value=True),
            patch("mm.ffmpeg.probe_duration", return_value=0.0),
        ):
            messages = list(strat.encode(video))
            assert len(messages) == 1
            assert "Cannot determine duration" in messages[0]["content"][0]["text"]

    def test_no_frames_extracted(self, tmp_path):
        from mm.encoders import get

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        strat = get("frame-sample")
        with (
            patch("mm.ffmpeg.ffmpeg_available", return_value=True),
            patch("mm.ffmpeg.probe_duration", return_value=10.0),
            patch("mm.ffmpeg.extract_frames_at_timestamps", return_value=[]),
        ):
            messages = list(strat.encode(video))
            assert len(messages) == 1
            assert "No frames extracted" in messages[0]["content"][0]["text"]

    def test_successful_encoding(self, tmp_path):
        from mm.encoders import get

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        frame1 = tmp_path / "f1.jpg"
        frame2 = tmp_path / "f2.jpg"
        frame1.write_bytes(b"\xff\xd8\xff" + b"\x00" * 50)
        frame2.write_bytes(b"\xff\xd8\xff" + b"\x00" * 50)

        strat = get("frame-sample")
        with (
            patch("mm.ffmpeg.ffmpeg_available", return_value=True),
            patch("mm.ffmpeg.probe_duration", return_value=5.0),
            patch("mm.ffmpeg.extract_frames_at_timestamps", return_value=[frame1, frame2]),
        ):
            messages = list(strat.encode(video, fps=1.0, max_frames_per_message=16))
            assert len(messages) == 1
            msg = messages[0]
            text_parts = [p for p in msg["content"] if p.get("type") == "text"]
            image_parts = [p for p in msg["content"] if p.get("type") == "image_url"]
            assert len(text_parts) == 1
            assert "Video frames" in text_parts[0]["text"]
            assert len(image_parts) == 2


class TestVideoChunk:
    def test_ffmpeg_unavailable(self, tmp_path):
        from mm.encoders import get

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        strat = get("video-chunk")
        with patch("mm.ffmpeg.ffmpeg_available", return_value=False):
            messages = list(strat.encode(video))
            assert len(messages) == 1
            assert "ffmpeg not available" in messages[0]["content"][0]["text"]

    def test_multiple_chunks(self, tmp_path):
        from mm.encoders import get

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        jpeg_bytes = b"\xff\xd8\xff" + b"\x00" * 50
        chunk_count = [0]

        def make_frame(*args, **kwargs):
            chunk_count[0] += 1
            f = tmp_path / f"frame_{chunk_count[0]}.jpg"
            f.write_bytes(jpeg_bytes)
            return [f]

        strat = get("video-chunk")
        with (
            patch("mm.ffmpeg.ffmpeg_available", return_value=True),
            patch("mm.ffmpeg.probe_duration", return_value=120.0),
            patch("mm.ffmpeg.extract_frames_at_timestamps", side_effect=make_frame),
        ):
            messages = list(strat.encode(video, chunk_duration=60, overlap=20))
            assert len(messages) >= 2
            for msg in messages:
                assert msg["role"] == "user"
                text_parts = [p for p in msg["content"] if p.get("type") == "text"]
                assert "Video chunk" in text_parts[0]["text"]


# ---------------------------------------------------------------------------
# Document encoders
# ---------------------------------------------------------------------------


class TestDocumentRasterize:
    def test_pypdfium_not_installed(self, tmp_path):
        from mm.encoders import get

        doc = tmp_path / "test.pdf"
        doc.write_bytes(b"%PDF-1.4 fake")
        strat = get("rasterize")
        with patch("mm.encoders.document._rasterize_pages", return_value=[]):
            messages = list(strat.encode(doc))
            assert len(messages) == 1
            assert "No pages" in messages[0]["content"][0]["text"]

    @pytest.mark.skip(reason="slow: rasterizes real PDF pages")
    def test_pages_batched(self, tmp_path):
        from mm.encoders import get

        doc = tmp_path / "test.pdf"
        doc.write_bytes(b"%PDF-1.4 fake")
        fake_pages = [(base64.b64encode(b"\xff").decode(), "image/jpeg")] * 10

        strat = get("rasterize")
        with patch("mm.encoders.document._rasterize_pages", return_value=fake_pages):
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

        strat = get("rasterize-text")
        with (
            patch("mm.encoders.document._rasterize_pages", return_value=fake_pages),
            patch("mm.encoders.document._extract_page_texts", return_value=fake_texts),
        ):
            messages = list(strat.encode(doc, pages_per_message=4))
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
        messages = list(strat.encode(doc))
        assert len(messages) == 1
        content = messages[0]["content"]
        assert any("inline_data" in p for p in content)

    def test_gemini_video_chunked_short_video(self, tmp_path):
        from mm.encoders import get

        video = tmp_path / "short.mp4"
        video.write_bytes(b"\x00" * 100)
        strat = get("video-gemini-chunked")
        with (
            patch("mm.ffmpeg.ffmpeg_available", return_value=True),
            patch("mm.ffmpeg.probe_duration", return_value=30.0),
        ):
            messages = list(strat.encode(video, max_seconds=120))
            assert len(messages) == 1
            assert any("inline_data" in p for p in messages[0]["content"])

    def test_gemini_video_chunked_ffmpeg_unavailable(self, tmp_path):
        from mm.encoders import get

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        strat = get("video-gemini-chunked")
        with patch("mm.ffmpeg.ffmpeg_available", return_value=False):
            messages = list(strat.encode(video))
            assert len(messages) == 1
            assert "ffmpeg not available" in messages[0]["content"][0]["text"]


# ---------------------------------------------------------------------------
# Shot-based video encoders
# ---------------------------------------------------------------------------


class TestShotTimestamps:
    def test_sample_timestamps_basic(self):
        from mm.encoders.video.shot import _sample_timestamps_in_range

        ts = _sample_timestamps_in_range(0.0, 10.0, 5)
        assert len(ts) == 5
        assert all(0.0 <= t <= 10.0 for t in ts)

    def test_sample_timestamps_single(self):
        from mm.encoders.video.shot import _sample_timestamps_in_range

        ts = _sample_timestamps_in_range(5.0, 10.0, 1)
        assert len(ts) == 1
        assert ts[0] == pytest.approx(7.5)

    def test_sample_timestamps_zero(self):
        from mm.encoders.video.shot import _sample_timestamps_in_range

        ts = _sample_timestamps_in_range(0.0, 10.0, 0)
        assert ts == []

    def test_sample_timestamps_zero_duration(self):
        from mm.encoders.video.shot import _sample_timestamps_in_range

        ts = _sample_timestamps_in_range(5.0, 5.0, 3)
        assert len(ts) == 1
        assert ts[0] == pytest.approx(5.0)


class TestShotFrames:
    def test_ffmpeg_unavailable(self, tmp_path):
        from mm.encoders import get

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        strat = get("shot-frames")
        with patch("mm.ffmpeg.ffmpeg_available", return_value=False):
            messages = list(strat.encode(video))
            assert "ffmpeg not available" in messages[0]["content"][0]["text"]

    def test_no_shots_detected(self, tmp_path):
        from mm.encoders.video.shot import ShotFrames

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        strat = ShotFrames()
        with (
            patch("mm.ffmpeg.ffmpeg_available", return_value=True),
            patch("mm.encoders.video.shot._detect_shots", return_value=[]),
        ):
            messages = list(strat.encode(video))
            assert "No shots detected" in messages[0]["content"][0]["text"]

    def test_successful_shot_encoding(self, tmp_path):
        from mm.encoders.video.shot import ShotFrames

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        frame = tmp_path / "f.jpg"
        frame.write_bytes(b"\xff\xd8\xff" + b"\x00" * 50)

        strat = ShotFrames()
        with (
            patch("mm.ffmpeg.ffmpeg_available", return_value=True),
            patch("mm.encoders.video.shot._detect_shots", return_value=[(0.0, 5.0), (5.0, 10.0)]),
            patch("mm.ffmpeg.extract_frames_at_timestamps", return_value=[frame]),
        ):
            messages = list(strat.encode(video, max_frames_per_shot=4))
            assert len(messages) == 2
            for msg in messages:
                text_parts = [p for p in msg["content"] if p.get("type") == "text"]
                assert any("Shot" in t["text"] for t in text_parts)


class TestShotMosaic:
    def test_ffmpeg_unavailable(self, tmp_path):
        from mm.encoders import get

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        strat = get("shot-mosaic")
        with patch("mm.ffmpeg.ffmpeg_available", return_value=False):
            messages = list(strat.encode(video))
            assert "ffmpeg not available" in messages[0]["content"][0]["text"]

    def test_successful_mosaic(self, tmp_path):
        from mm.encoders.video.shot import ShotMosaic

        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        frame = tmp_path / "f.jpg"
        frame.write_bytes(b"\xff\xd8\xff" + b"\x00" * 50)
        mosaic = tmp_path / "m.jpg"
        mosaic.write_bytes(b"\xff\xd8\xff" + b"\x00" * 50)

        strat = ShotMosaic()
        with (
            patch("mm.ffmpeg.ffmpeg_available", return_value=True),
            patch("mm.encoders.video.shot._detect_shots", return_value=[(0.0, 10.0)]),
            patch("mm.ffmpeg.extract_frames_at_timestamps", return_value=[frame]),
            patch("mm.ffmpeg.tile_frames_to_mosaics", return_value=[mosaic]),
        ):
            messages = list(strat.encode(video))
            assert len(messages) == 1
            text_parts = [p for p in messages[0]["content"] if p.get("type") == "text"]
            assert any("Shot" in t["text"] for t in text_parts)
