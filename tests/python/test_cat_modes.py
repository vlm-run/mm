"""Tests for --mode fast/accurate dispatch in the cat command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from mm.cat_utils.base_utils import CatMode, CatOpts, RunResult
from mm.commands.cat import _extract
from mm.utils import DOCUMENT_EXTS, file_kind


def _make_opts(mode: CatMode, **overrides: object) -> CatOpts:
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
        dry_run=False,
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

    def test_text_short_circuits_pipeline(self, tmp_path, isolated_db):
        """``cat`` on ``kind=text`` never resolves a pipeline."""
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        with (
            patch("mm.commands.cat._run_fast") as fast_mock,
            patch("mm.commands.cat._run_accurate") as accurate_mock,
        ):
            for mode in ("fast", "accurate"):
                result = _extract(f, _make_opts(mode))
                assert "hello world" in result
        fast_mock.assert_not_called()
        accurate_mock.assert_not_called()

    def test_non_pdf_document_fast_short_circuits_pipeline(
        self, tmp_path, isolated_db, monkeypatch
    ):
        """In fast mode, non-PDF office docs follow the ``extract_text`` flow."""
        f = tmp_path / "notes.docx"
        f.write_bytes(b"PK\x03\x04 not-a-real-docx")  # zip magic + garbage
        with (
            patch(
                "mm.cat_utils.extract_meta.extract_meta",
                return_value="docx body text",
            ),
            patch("mm.commands.cat._run_fast") as fast_mock,
            patch("mm.commands.cat._run_accurate") as accurate_mock,
        ):
            result = _extract(f, _make_opts("fast"))
            assert result == "docx body text"
        fast_mock.assert_not_called()
        accurate_mock.assert_not_called()

    def test_non_pdf_document_accurate_routes_through_pdf(self, tmp_path, isolated_db, monkeypatch):
        """In accurate mode, non-PDF office docs convert to a temp PDF and run
        through the pipeline.
        """
        f = tmp_path / "notes.docx"
        f.write_bytes(b"PK\x03\x04 not-a-real-docx")
        seen_paths: list[Path] = []

        def _fake_to_pdf(src: str, dst: str) -> str:
            Path(dst).write_bytes(b"%PDF-1.4 stub\n%%EOF\n")
            return dst

        def _capture_run(path, kind, spec, opts, *, meta_path=None):
            seen_paths.append(path)
            assert path != f, "accurate must receive the temp PDF, not the docx"
            assert path.suffix == ".pdf"
            assert path.exists(), "temp PDF must exist while run_accurate runs"
            assert meta_path == f
            return RunResult(content="structured markdown")

        cm1, cm2, cm3, cm4 = _mock_cache_miss()
        with (
            cm1,
            cm2,
            cm3,
            cm4,
            patch("mm._mm.office_to_pdf", side_effect=_fake_to_pdf),
            patch("mm.commands.cat._run_accurate", side_effect=_capture_run) as accurate_mock,
            patch("mm.commands.cat._run_fast") as fast_mock,
        ):
            result = _extract(f, _make_opts("accurate"))
            assert result == "structured markdown"
        fast_mock.assert_not_called()
        accurate_mock.assert_called_once()
        # Temp PDF cleaned up after _extract returns.
        assert not seen_paths[0].exists(), f"temp PDF leaked: {seen_paths[0]}"
        assert not seen_paths[0].parent.exists(), f"temp dir leaked: {seen_paths[0].parent}"

    def test_fast_image_dispatch(self, tmp_path):
        from mm.pipelines.schema import PipelineSpec

        f = tmp_path / "test.jpg"
        f.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)
        cm1, cm2, cm3, cm4 = _mock_cache_miss()
        with cm1, cm2, cm3, cm4, patch("mm.commands.cat._run_fast") as mock:
            mock.return_value = RunResult(content="mocked fast result")
            opts = _make_opts("fast")
            result = _extract(f, opts)
            # _extract now resolves+merges the pipeline once and forwards it.
            assert mock.call_count == 1
            args, kwargs = mock.call_args
            assert args[0] == f
            assert args[1] == "image"
            assert isinstance(args[2], PipelineSpec)
            assert args[3] is opts
            assert result == "mocked fast result"

    def test_accurate_image_dispatch(self, tmp_path):
        from mm.pipelines.schema import PipelineSpec

        f = tmp_path / "test.jpg"
        f.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)
        cm1, cm2, cm3, cm4 = _mock_cache_miss()
        with cm1, cm2, cm3, cm4, patch("mm.commands.cat._run_accurate") as mock:
            mock.return_value = RunResult(content="mocked accurate result")
            opts = _make_opts("accurate")
            result = _extract(f, opts)
            assert mock.call_count == 1
            args, _ = mock.call_args
            assert args[0] == f
            assert args[1] == "image"
            assert isinstance(args[2], PipelineSpec)
            assert args[3] is opts
            assert result == "mocked accurate result"

    def test_accurate_document_dispatch(self, tmp_path):
        from mm.pipelines.schema import PipelineSpec

        f = tmp_path / "test.pdf"
        f.write_bytes(b"%PDF-1.4 fake")
        cm1, cm2, cm3, cm4 = _mock_cache_miss()
        with cm1, cm2, cm3, cm4, patch("mm.commands.cat._run_accurate") as mock:
            mock.return_value = RunResult(content="summary of document")
            opts = _make_opts("accurate")
            result = _extract(f, opts)
            assert mock.call_count == 1
            args, _ = mock.call_args
            assert args[0] == f
            assert args[1] == "document"
            assert isinstance(args[2], PipelineSpec)
            assert args[3] is opts
            assert result == "summary of document"


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

        def fake_run_fast(_path, _kind, _spec, _opts):
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

        def fake_run_fast(_path, _kind, _spec, _opts):
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
