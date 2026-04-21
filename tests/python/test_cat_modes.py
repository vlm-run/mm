"""Tests for --mode fast/accurate pipeline-driven extraction in cat command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from mm.commands.cat import (
    _CatOpts,
    _extract,
    _run_fast,
)
from mm.utils import DOCUMENT_EXTS, file_kind


def _make_opts(mode: str = "fast", **overrides: object) -> _CatOpts:
    defaults: dict[str, object] = dict(
        n=None,
        output_dir=None,
        mode=mode,
        no_cache=False,
        format="rich",
        encode_overrides={},
        generate_overrides={},
        pipelines={},
        verbose=False,
    )
    defaults.update(overrides)
    return _CatOpts(**defaults)


def _mock_cache_miss():
    """Context manager stack that mocks the L2 cache infrastructure to always miss."""
    mock_db = MagicMock()
    mock_db.get_l2.return_value = None
    mock_profile = MagicMock()
    mock_profile.name = "test"
    mock_profile.model = "test-model"
    return (
        patch("mm.store.utils.get_content_hash", return_value="fakehash"),
        patch("mm.store.db.MmDatabase", return_value=mock_db),
        patch("mm.profile.get_profile", return_value=mock_profile),
        patch("mm.store.utils.get_l2_id", return_value="fake_l2_id"),
    )


class TestFileKind:
    """Test file kind detection including document types."""

    def test_pdf(self):
        assert file_kind(Path("test.pdf")) == "document"

    def test_docx(self):
        assert file_kind(Path("test.docx")) == "document"

    def test_pptx(self):
        assert file_kind(Path("test.pptx")) == "document"

    def test_image(self):
        assert file_kind(Path("photo.jpg")) == "image"

    def test_video(self):
        assert file_kind(Path("clip.mp4")) == "video"

    def test_audio(self):
        assert file_kind(Path("song.mp3")) == "audio"

    def test_text(self):
        assert file_kind(Path("readme.txt")) == "text"

    def test_code(self):
        assert file_kind(Path("main.py")) == "text"


class TestDocumentExts:
    def test_includes_pdf(self):
        assert ".pdf" in DOCUMENT_EXTS

    def test_includes_docx(self):
        assert ".docx" in DOCUMENT_EXTS

    def test_includes_pptx(self):
        assert ".pptx" in DOCUMENT_EXTS


class TestCatOptsMode:
    """Test that _CatOpts carries the mode parameter."""

    def test_mode_fast(self):
        assert _make_opts(mode="fast").mode == "fast"

    def test_mode_accurate(self):
        assert _make_opts(mode="accurate").mode == "accurate"


class TestExtractDispatch:
    """Test that _extract dispatches correctly by kind and mode."""

    def test_fast_text(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        result = _extract(f, _make_opts("fast"))
        assert "hello world" in result

    def test_fast_image_dispatch(self, tmp_path):
        f = tmp_path / "test.jpg"
        f.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)
        cm1, cm2, cm3, cm4 = _mock_cache_miss()
        with cm1, cm2, cm3, cm4, patch("mm.commands.cat._run_fast") as mock:
            mock.return_value = "mocked fast result"
            opts = _make_opts("fast")
            result = _extract(f, opts)
            mock.assert_called_once_with(f, "image", opts)
            assert result == "mocked fast result"

    def test_accurate_image_dispatch(self, tmp_path):
        f = tmp_path / "test.jpg"
        f.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)
        cm1, cm2, cm3, cm4 = _mock_cache_miss()
        with cm1, cm2, cm3, cm4, patch("mm.commands.cat._run_accurate") as mock:
            mock.return_value = "mocked accurate result"
            opts = _make_opts("accurate")
            result = _extract(f, opts)
            mock.assert_called_once_with(f, "image", opts)
            assert result == "mocked accurate result"

    def test_accurate_document_dispatch(self, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_bytes(b"%PDF-1.4 fake")
        cm1, cm2, cm3, cm4 = _mock_cache_miss()
        with cm1, cm2, cm3, cm4, patch("mm.commands.cat._run_accurate") as mock:
            mock.return_value = "summary of document"
            opts = _make_opts("accurate")
            result = _extract(f, opts)
            mock.assert_called_once_with(f, "document", opts)
            assert result == "summary of document"


class TestRunFastTextPassthrough:
    """Code/text/config files have no pipeline — fast mode reads raw content."""

    def test_text_passthrough(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        result = _run_fast(f, "text", _make_opts("fast"))
        assert "hello world" in result
