"""Tests for --mode fast/accurate pipeline-driven extraction in cat command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from mm.cat_utils.base_utils import CatOpts, RunResult
from mm.commands.cat import _extract, _run_fast
from mm.utils import DOCUMENT_EXTS, file_kind


def _make_opts(mode: str = "fast", **overrides: object) -> CatOpts:
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
    return CatOpts(**defaults)


def _mock_cache_miss():
    """Context manager stack that mocks the extractions cache to always miss."""
    mock_db = MagicMock()
    mock_db.get_extraction.return_value = None
    mock_profile = MagicMock()
    mock_profile.name = "test"
    mock_profile.model = "test-model"
    return (
        patch("mm.store.utils.get_content_hash", return_value="fakehash"),
        patch("mm.store.db.MmDatabase", return_value=mock_db),
        patch("mm.profile.get_profile", return_value=mock_profile),
        patch("mm.store.utils.get_extraction_id", return_value="fake_extraction_id"),
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
    """Test that CatOpts carries the mode parameter."""

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
            mock.return_value = RunResult(content="mocked fast result")
            opts = _make_opts("fast")
            result = _extract(f, opts)
            mock.assert_called_once_with(f, "image", opts)
            assert result == "mocked fast result"

    def test_accurate_image_dispatch(self, tmp_path):
        f = tmp_path / "test.jpg"
        f.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)
        cm1, cm2, cm3, cm4 = _mock_cache_miss()
        with cm1, cm2, cm3, cm4, patch("mm.commands.cat._run_accurate") as mock:
            mock.return_value = RunResult(content="mocked accurate result")
            opts = _make_opts("accurate")
            result = _extract(f, opts)
            mock.assert_called_once_with(f, "image", opts)
            assert result == "mocked accurate result"

    def test_accurate_document_dispatch(self, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_bytes(b"%PDF-1.4 fake")
        cm1, cm2, cm3, cm4 = _mock_cache_miss()
        with cm1, cm2, cm3, cm4, patch("mm.commands.cat._run_accurate") as mock:
            mock.return_value = RunResult(content="summary of document")
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
        assert "hello world" in result.content


class TestVerboseCacheReplay:
    """The headline fix for PR #100: ``--verbose`` no longer invalidates the cache.

    On a cache miss, the rendered verbose suffix is persisted alongside the
    extraction. On a subsequent cached run with ``verbose=True``, the suffix
    is read back and appended without re-invoking the underlying pipeline.
    """

    def _isolated_db(self, tmp_path: Path, monkeypatch):
        from mm.store.db import MmDatabase

        db_path = tmp_path / "mm.db"
        monkeypatch.setattr(MmDatabase, "DB_PATH", db_path)
        monkeypatch.setattr(MmDatabase, "DB_DIR", tmp_path)
        return db_path

    def test_cached_verbose_replays_suffix_without_rerun(self, tmp_path, monkeypatch):
        self._isolated_db(tmp_path, monkeypatch)

        f = tmp_path / "photo.jpg"
        f.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        suffix = "[dim]generate: ollama • 1.2s • 100→50 tokens[/dim]"
        run_call_count = {"n": 0}

        def fake_run_fast(_path, _kind, _opts):
            run_call_count["n"] += 1
            return RunResult(content="cached body", verbose_suffix=suffix)

        # Cold run with verbose=False → populates cache + metadata.
        with patch("mm.commands.cat._run_fast", side_effect=fake_run_fast):
            cold = _extract(f, _make_opts("fast", verbose=False))
        assert cold == "cached body"
        assert run_call_count["n"] == 1

        # Warm run with verbose=True → cache hit, suffix replayed, no re-run.
        with patch(
            "mm.commands.cat._run_fast",
            side_effect=AssertionError("should not be called on cache hit"),
        ):
            warm = _extract(f, _make_opts("fast", verbose=True))
        assert warm == f"cached body\n\n{suffix}"
        assert run_call_count["n"] == 1

    def test_cached_non_verbose_omits_suffix(self, tmp_path, monkeypatch):
        self._isolated_db(tmp_path, monkeypatch)

        f = tmp_path / "photo.jpg"
        f.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        suffix = "[dim]generate: ollama • 0.5s • 10→5 tokens[/dim]"

        def fake_run_fast(_path, _kind, _opts):
            return RunResult(content="cached body", verbose_suffix=suffix)

        with patch("mm.commands.cat._run_fast", side_effect=fake_run_fast):
            _extract(f, _make_opts("fast", verbose=True))

        # Even though metadata was stored, a verbose=False reader gets only content.
        with patch(
            "mm.commands.cat._run_fast",
            side_effect=AssertionError("should not be called on cache hit"),
        ):
            warm = _extract(f, _make_opts("fast", verbose=False))
        assert warm == "cached body"
