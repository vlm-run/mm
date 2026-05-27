"""Tests for mm.encoders.auto_strategy.auto_strategy().

All cases mock FileMetadata.from_path and file_kind so no real media files
are needed and tests run in milliseconds.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest
from mm.encoders.auto_strategy import auto_strategy

_MB = 1024 * 1024


# ---------------------------------------------------------------------------
# Minimal FileMetadata stand-in
# ---------------------------------------------------------------------------


@dataclass
class _Meta:
    size: int = 0
    duration_s: float | None = None
    has_audio: bool | None = None
    audio_codec: str | None = None
    dimensions: str | None = None
    pages: int | None = None
    doc_creator: str | None = None
    doc_producer: str | None = None
    # satisfy FileMetadata interface for any attribute access
    path: str = ""
    name: str = ""
    mime: str = ""
    kind: str = ""


def _run(path: Path, kind: str, meta: _Meta) -> str:
    with (
        patch("mm.utils.file_kind", return_value=kind),
        patch("mm.peek.FileMetadata.from_path", return_value=meta),
    ):
        return auto_strategy(path)


# ---------------------------------------------------------------------------
# VIDEO
# ---------------------------------------------------------------------------


class TestVideo:
    def _path(self, name: str = "clip.mp4") -> Path:
        return Path(f"/fake/{name}")

    def test_short_no_audio_gives_mosaic(self):
        meta = _Meta(size=10 * _MB, duration_s=300.0, has_audio=False)
        assert _run(self._path(), "video", meta) == "mosaic"

    def test_short_with_audio_gives_mosaic_w_transcript(self):
        meta = _Meta(size=10 * _MB, duration_s=300.0, has_audio=True, audio_codec="aac")
        assert _run(self._path(), "video", meta) == "mosaic-w-transcript"

    def test_medium_no_audio_gives_keyframes(self):
        # 20 min, 50 MB — exceeds short (10 min / 25 MB) but within medium
        meta = _Meta(size=50 * _MB, duration_s=1200.0, has_audio=False)
        assert _run(self._path(), "video", meta) == "keyframes"

    def test_medium_with_audio_gives_keyframes_w_transcript(self):
        meta = _Meta(size=50 * _MB, duration_s=1200.0, has_audio=True, audio_codec="mp3")
        assert _run(self._path(), "video", meta) == "keyframes-w-transcript"

    def test_long_gives_summary(self):
        # 40 min, 110 MB — exceeds both medium thresholds
        meta = _Meta(size=110 * _MB, duration_s=2400.0, has_audio=False)
        assert _run(self._path(), "video", meta) == "summary"

    def test_long_with_audio_gives_summary_w_transcript(self):
        meta = _Meta(size=110 * _MB, duration_s=2400.0, has_audio=True, audio_codec="aac")
        assert _run(self._path(), "video", meta) == "summary-w-transcript"

    def test_short_but_large_file_escapes_mosaic(self):
        # Duration fits short tier but size exceeds 25 MB → medium → keyframes
        meta = _Meta(size=30 * _MB, duration_s=300.0, has_audio=False)
        assert _run(self._path(), "video", meta) == "keyframes"

    def test_has_audio_none_treated_as_no_transcript(self):
        meta = _Meta(size=5 * _MB, duration_s=60.0, has_audio=None, audio_codec=None)
        assert _run(self._path(), "video", meta) == "mosaic"


# ---------------------------------------------------------------------------
# AUDIO
# ---------------------------------------------------------------------------


class TestAudio:
    def _path(self, name: str = "track.mp3") -> Path:
        return Path(f"/fake/{name}")

    def test_short_small_mp3_gives_transcribe(self):
        # ≤300s and ≤10 MB → transcribe
        meta = _Meta(size=2 * _MB, duration_s=60.0)
        assert _run(self._path("track.mp3"), "audio", meta) == "transcribe"

    def test_long_mp3_gives_base64(self):
        # >300s → base64
        meta = _Meta(size=6 * _MB, duration_s=700.0)
        assert _run(self._path("track.mp3"), "audio", meta) == "base64"

    def test_at_duration_boundary_gives_transcribe(self):
        # Exactly 300s, 6 MB → both conditions met → transcribe
        meta = _Meta(size=6 * _MB, duration_s=300.0)
        assert _run(self._path("track.mp3"), "audio", meta) == "transcribe"

    def test_short_small_wav_gives_transcribe(self):
        # ≤300s and ≤10 MB → transcribe (lossless has no special threshold)
        meta = _Meta(size=5 * _MB, duration_s=60.0)
        assert _run(self._path("clip.wav"), "audio", meta) == "transcribe"

    def test_oversize_wav_gives_base64(self):
        # >10 MB → base64 regardless of duration
        meta = _Meta(size=11 * _MB, duration_s=200.0)
        assert _run(self._path("clip.wav"), "audio", meta) == "base64"

    def test_short_flac_gives_transcribe(self):
        meta = _Meta(size=4 * _MB, duration_s=100.0)
        assert _run(self._path("song.flac"), "audio", meta) == "transcribe"

    def test_short_m4a_gives_transcribe(self):
        # m4a ≤300s and ≤10 MB → transcribe
        meta = _Meta(size=3 * _MB, duration_s=200.0)
        assert _run(self._path("audio.m4a"), "audio", meta) == "transcribe"


# ---------------------------------------------------------------------------
# IMAGE
# ---------------------------------------------------------------------------


class TestImage:
    def _path(self, name: str = "photo.jpg") -> Path:
        return Path(f"/fake/{name}")

    def test_standard_jpeg_gives_resize(self):
        meta = _Meta(size=2 * _MB, dimensions="1920x1080")
        assert _run(self._path("photo.jpg"), "image", meta) == "resize"

    def test_over_4k_width_gives_tile(self):
        meta = _Meta(size=5 * _MB, dimensions="5000x3000")
        assert _run(self._path("wide.jpg"), "image", meta) == "tile"

    def test_over_4k_height_gives_tile(self):
        meta = _Meta(size=5 * _MB, dimensions="2000x2500")
        assert _run(self._path("tall.jpg"), "image", meta) == "tile"

    def test_large_file_gives_tile(self):
        meta = _Meta(size=15 * _MB, dimensions="1920x1080")
        assert _run(self._path("large.jpg"), "image", meta) == "tile"

    def test_heic_gives_tile(self):
        meta = _Meta(size=4 * _MB, dimensions="4032x3024")
        assert _run(self._path("iphone.heic"), "image", meta) == "tile"

    def test_heif_gives_tile(self):
        meta = _Meta(size=4 * _MB, dimensions="4032x3024")
        assert _run(self._path("iphone.heif"), "image", meta) == "tile"

    def test_png_below_1080p_gives_resize(self):
        meta = _Meta(size=1 * _MB, dimensions="800x600")
        assert _run(self._path("icon.png"), "image", meta) == "resize"

    def test_png_above_1080p_gives_tile(self):
        meta = _Meta(size=3 * _MB, dimensions="2560x1440")
        assert _run(self._path("screenshot.png"), "image", meta) == "tile"

    def test_extreme_aspect_ratio_wide_gives_tile(self):
        # 6000x100 → ratio = 60 > 3
        meta = _Meta(size=1 * _MB, dimensions="6000x100")
        assert _run(self._path("panorama.jpg"), "image", meta) == "tile"

    def test_extreme_aspect_ratio_tall_gives_tile(self):
        meta = _Meta(size=1 * _MB, dimensions="100x6000")
        assert _run(self._path("scroll.jpg"), "image", meta) == "tile"

    def test_normal_aspect_ratio_not_flagged(self):
        # 1920x1080 → ratio 1.78 < 3 → resize
        meta = _Meta(size=2 * _MB, dimensions="1920x1080")
        assert _run(self._path("photo.jpg"), "image", meta) == "resize"

    def test_no_dimensions_falls_back_to_size_heuristic(self):
        # No dimension string, small file → resize
        meta = _Meta(size=1 * _MB, dimensions=None)
        assert _run(self._path("photo.jpg"), "image", meta) == "resize"


# ---------------------------------------------------------------------------
# DOCUMENT
# ---------------------------------------------------------------------------


class TestDocument:
    def _path(self, name: str = "doc.pdf") -> Path:
        return Path(f"/fake/{name}")

    def test_non_pdf_always_gives_page_text(self):
        meta = _Meta(size=500_000)
        assert _run(Path("/fake/report.docx"), "document", meta) == "page-text"

    def test_pptx_gives_page_text(self):
        meta = _Meta(size=2 * _MB)
        assert _run(Path("/fake/slides.pptx"), "document", meta) == "page-text"

    def test_pdf_over_100_pages_gives_page_text(self):
        meta = _Meta(size=20 * _MB, pages=150)
        assert _run(self._path(), "document", meta) == "page-text"

    def test_pdf_exactly_100_pages_text_light_gives_page_text(self):
        # 100 pages, 2 MB → 20 KB/page < 500 KB threshold → text-light
        meta = _Meta(size=2 * _MB, pages=100)
        assert _run(self._path(), "document", meta) == "page-text"

    def test_pdf_image_heavy_non_scanner_gives_rasterize_text(self):
        # 10 pages, 8 MB → 800 KB/page > 500 KB → image-heavy, no scanner
        meta = _Meta(size=8 * _MB, pages=10, doc_creator="Adobe Acrobat")
        assert _run(self._path(), "document", meta) == "rasterize-text"

    def test_pdf_image_heavy_scanner_creator_gives_rasterize(self):
        meta = _Meta(size=8 * _MB, pages=10, doc_creator="ScanSnap Manager")
        assert _run(self._path(), "document", meta) == "rasterize"

    def test_pdf_image_heavy_scanner_in_producer_gives_rasterize(self):
        meta = _Meta(size=8 * _MB, pages=10, doc_creator="", doc_producer="HP ScanJet")
        assert _run(self._path(), "document", meta) == "rasterize"

    def test_pdf_unknown_pages_large_file_gives_rasterize_text(self):
        # pages=None, size > 5 MB → treated as image-heavy, no scanner
        meta = _Meta(size=6 * _MB, pages=None, doc_creator=None)
        assert _run(self._path(), "document", meta) == "rasterize-text"

    def test_pdf_unknown_pages_small_file_gives_page_text(self):
        # pages=None, size ≤ 5 MB → text-light assumed
        meta = _Meta(size=3 * _MB, pages=None)
        assert _run(self._path(), "document", meta) == "page-text"


# ---------------------------------------------------------------------------
# INVALID KIND
# ---------------------------------------------------------------------------


class TestInvalidKind:
    def test_text_kind_raises(self):
        meta = _Meta(size=1000)
        with pytest.raises(ValueError, match="auto_strategy only handles binary"):
            _run(Path("/fake/notes.txt"), "text", meta)

    def test_code_kind_raises(self):
        meta = _Meta(size=2000)
        with pytest.raises(ValueError, match="auto_strategy only handles binary"):
            _run(Path("/fake/main.py"), "code", meta)
