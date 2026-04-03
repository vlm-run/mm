"""Tests for --mode basic|fast|accurate extraction in cat command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from mm.commands.cat import (
    DOCUMENT_EXTS,
    _CatOpts,
    _file_kind,
    _l2_modal,
)


class TestFileKind:
    """Test file kind detection including document types."""

    def test_pdf(self):
        assert _file_kind(Path("test.pdf")) == "document"

    def test_docx(self):
        assert _file_kind(Path("test.docx")) == "document"

    def test_pptx(self):
        assert _file_kind(Path("test.pptx")) == "document"

    def test_image(self):
        assert _file_kind(Path("photo.jpg")) == "image"

    def test_video(self):
        assert _file_kind(Path("clip.mp4")) == "video"

    def test_audio(self):
        assert _file_kind(Path("song.mp3")) == "audio"

    def test_text(self):
        assert _file_kind(Path("readme.txt")) == "text"

    def test_code(self):
        assert _file_kind(Path("main.py")) == "text"


class TestDocumentExts:
    def test_includes_pdf(self):
        assert ".pdf" in DOCUMENT_EXTS

    def test_includes_docx(self):
        assert ".docx" in DOCUMENT_EXTS

    def test_includes_pptx(self):
        assert ".pptx" in DOCUMENT_EXTS


class TestCatOptsMode:
    """Test that _CatOpts carries the mode parameter."""

    def test_mode_none(self):
        opts = _CatOpts(
            level=2,
            n=None,
            detail=False,
            output_dir=None,
            max_pages=None,
            mosaic_tile="4x4",
            mosaic_image_width=160,
            video_mosaic_count=1,
            video_mosaic_strategy="uniform",
            audio_speed=2.0,
            audio_sample_rate=16000,
            mode=None,
            format="rich",
        )
        assert opts.mode is None

    def test_mode_fast(self):
        opts = _CatOpts(
            level=2,
            n=None,
            detail=False,
            output_dir=None,
            max_pages=None,
            mosaic_tile="4x4",
            mosaic_image_width=160,
            video_mosaic_count=1,
            video_mosaic_strategy="uniform",
            audio_speed=2.0,
            audio_sample_rate=16000,
            mode="fast",
            format="rich",
        )
        assert opts.mode == "fast"

    def test_mode_accurate(self):
        opts = _CatOpts(
            level=2,
            n=None,
            detail=False,
            output_dir=None,
            max_pages=None,
            mosaic_tile="4x4",
            mosaic_image_width=160,
            video_mosaic_count=1,
            video_mosaic_strategy="uniform",
            audio_speed=2.0,
            audio_sample_rate=16000,
            mode="accurate",
            format="rich",
        )
        assert opts.mode == "accurate"


class TestL2ModalDispatch:
    """Test that _l2_modal dispatches correctly by kind."""

    def _make_opts(self, mode: str = "fast") -> _CatOpts:
        return _CatOpts(
            level=2,
            n=None,
            detail=False,
            output_dir=None,
            max_pages=None,
            mosaic_tile="4x4",
            mosaic_image_width=160,
            video_mosaic_count=1,
            video_mosaic_strategy="uniform",
            audio_speed=2.0,
            audio_sample_rate=16000,
            mode=mode,
            format="rich",
        )

    def test_unknown_mode(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        result = _l2_modal(f, "text", self._make_opts("unknown"))
        assert "Unknown mode" in result

    def test_image_dispatch(self, tmp_path):
        f = tmp_path / "test.jpg"
        f.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)
        with patch("mm.commands.cat._l2_image_modal") as mock:
            mock.return_value = "mocked image result"
            result = _l2_modal(f, "image", self._make_opts("fast"))
            mock.assert_called_once_with(f, "fast")
            assert result == "mocked image result"

    def test_video_dispatch(self, tmp_path):
        f = tmp_path / "test.mp4"
        f.write_bytes(b"\x00" * 100)
        with patch("mm.commands.cat._l2_video_modal") as mock:
            mock.return_value = "mocked video result"
            opts = self._make_opts("fast")
            result = _l2_modal(f, "video", opts)
            mock.assert_called_once_with(f, opts, "fast")
            assert result == "mocked video result"

    def test_audio_dispatch(self, tmp_path):
        f = tmp_path / "test.mp3"
        f.write_bytes(b"\x00" * 100)
        with patch("mm.commands.cat._l2_audio_modal") as mock:
            mock.return_value = "mocked audio result"
            opts = self._make_opts("accurate")
            result = _l2_modal(f, "audio", opts)
            mock.assert_called_once_with(f, opts, "accurate")
            assert result == "mocked audio result"

    def test_document_dispatch(self, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_bytes(b"%PDF-1.4 fake")
        with (
            patch("mm.commands.cat._l1") as mock_l1,
            patch("mm.llm.LlmBackend") as mock_llm_cls,
        ):
            mock_l1.return_value = "extracted text"
            mock_llm = MagicMock()
            mock_llm.describe.return_value = "summary of document"
            mock_llm_cls.return_value = mock_llm

            result = _l2_modal(f, "document", self._make_opts("fast"))
            assert result == "summary of document"
