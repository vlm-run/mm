"""Tests for ``mm peek`` and the :class:`FileMetadata` shape."""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import pytest
from mm.cli import app
from mm.peek import FileMetadata
from typer.testing import CliRunner

runner = CliRunner()


# ── Fixtures ──────────────────────────────────────────────────────────


def _write_png(path: Path, width: int, height: int) -> None:
    """Minimal valid PNG used in fixtures and `_write_minimal_mp4`'s sibling."""
    raw = b""
    for _ in range(height):
        raw += b"\x00" + b"\x80\x00\x40" * width
    compressed = zlib.compress(raw)

    def _chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", compressed)
    png += _chunk(b"IEND", b"")
    path.write_bytes(png)


@pytest.fixture
def tiny_png(tmp_path: Path) -> Path:
    p = tmp_path / "photo.png"
    _write_png(p, 64, 48)
    return p


@pytest.fixture
def tiny_txt(tmp_path: Path) -> Path:
    p = tmp_path / "main.py"
    p.write_text("import sys\n\ndef hello() -> int:\n    return 42\n")
    return p


# ── FileMetadata shape ────────────────────────────────────────────────


class TestFileMetadataShape:
    """Flat dataclass with every kind-specific field nullable."""

    def test_required_identity_fields(self, tiny_png: Path):
        fm = FileMetadata.from_path(tiny_png)
        assert fm.path == str(tiny_png.resolve())
        assert fm.name == "photo.png"
        assert fm.size > 0
        assert fm.mime == "image/png"
        assert fm.kind == "image"

    def test_image_populates_visual_fields(self, tiny_png: Path):
        fm = FileMetadata.from_path(tiny_png)
        assert fm.dimensions == "64x48"
        # phash is 64-bit; non-None for a real image.
        assert fm.phash is not None
        # Audio/video fields are not applicable → None.
        assert fm.duration_s is None
        assert fm.video_codec is None
        assert fm.audio_codec is None
        assert fm.pages is None

    def test_text_kind_leaves_av_visual_fields_null(self, tiny_txt: Path):
        fm = FileMetadata.from_path(tiny_txt)
        assert fm.kind == "text"
        assert fm.dimensions is None
        assert fm.phash is None
        assert fm.duration_s is None
        assert fm.fps is None
        assert fm.video_codec is None
        assert fm.audio_codec is None
        assert fm.has_audio is None
        assert fm.pages is None
        assert fm.exif_camera is None

    def test_to_dict_preserves_none_fields(self, tiny_txt: Path):
        """``to_dict`` keeps ``None`` fields so JSON shape is stable across kinds."""
        d = FileMetadata.from_path(tiny_txt).to_dict()
        # Same set of keys regardless of kind — downstream parsers don't fork.
        expected_keys = {
            "path",
            "name",
            "size",
            "mime",
            "kind",
            "dimensions",
            "phash",
            "exif_camera",
            "exif_date",
            "exif_gps",
            "exif_orientation",
            "duration_s",
            "fps",
            "video_codec",
            "audio_codec",
            "has_audio",
            "pages",
            "content_hash",
            "magic_mime",
            "extra",
        }
        assert set(d.keys()) == expected_keys

    def test_extra_field_present_in_shape(self, tiny_png: Path):
        """``extra`` is part of the shape; populated by magika or ``None``."""
        fm = FileMetadata.from_path(tiny_png)
        assert fm.extra is None or isinstance(fm.extra, dict)


# ── magika integration ───────────────────────────────────────────────


class TestMagikaExtra:
    """``FileMetadata.extra`` carries ``magika.identify_path(...).output.__dict__``."""

    EXPECTED_KEYS = {
        "label",
        "mime_type",
        "group",
        "description",
        "extensions",
        "is_text",
        "confidence",
    }

    def test_python_source_classified_as_python(self, tiny_txt: Path):
        fm = FileMetadata.from_path(tiny_txt)
        assert fm.extra is not None
        assert set(fm.extra.keys()) == self.EXPECTED_KEYS
        assert fm.extra["label"] == "python"
        assert fm.extra["group"] == "code"
        assert fm.extra["is_text"] is True
        assert fm.extra["mime_type"] == "text/x-python"
        assert "py" in fm.extra["extensions"]

    def test_png_classified_as_image(self, tiny_png: Path):
        fm = FileMetadata.from_path(tiny_png)
        assert fm.extra is not None
        assert set(fm.extra.keys()) == self.EXPECTED_KEYS
        assert fm.extra["mime_type"].startswith("image/")
        assert fm.extra["is_text"] is False

    def test_extensions_is_list_of_str(self, tiny_txt: Path):
        fm = FileMetadata.from_path(tiny_txt)
        assert fm.extra is not None
        exts = fm.extra["extensions"]
        assert isinstance(exts, list)
        assert all(isinstance(e, str) for e in exts)

    def test_pdf_classified_as_pdf(self, tmp_path: Path):
        """Real PDF magic bytes should classify as the ``pdf`` label."""
        pdf = tmp_path / "tiny.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%fake content\n%%EOF\n")
        fm = FileMetadata.from_path(pdf)
        assert fm.extra is not None
        assert fm.extra["label"] == "pdf"
        assert fm.extra["mime_type"] == "application/pdf"

    def test_extra_is_json_serializable(self, tiny_txt: Path):
        """``extra`` must round-trip through ``json.dumps`` cleanly.

        ``label`` is a magika ``ContentTypeLabel`` (str-enum); JSON
        resolves it to its string value automatically.
        """
        fm = FileMetadata.from_path(tiny_txt)
        assert fm.extra is not None
        encoded = json.dumps(fm.extra)
        decoded = json.loads(encoded)
        assert decoded["label"] == "python"
        assert decoded["is_text"] is True

    def test_extra_appears_in_peek_json_output(self, tiny_txt: Path):
        """``mm peek --format json`` round-trip exposes ``extra`` to consumers."""
        r = runner.invoke(app, ["peek", str(tiny_txt), "--format", "json"])
        assert r.exit_code == 0
        rows = json.loads(r.stdout.splitlines()[0])
        assert rows[0]["extra"] is not None
        assert rows[0]["extra"]["label"] == "python"


# ── CLI: never touches the DB ─────────────────────────────────────────


class TestPeekNoDb:
    """``mm peek`` must never read or write the SQLite store."""

    def test_no_db_file_created(self, tmp_path: Path, tiny_png: Path, monkeypatch):
        """Point MmDatabase at a sandbox path; peek must not create it."""
        from mm.store.db import MmDatabase

        sandbox = tmp_path / "sandbox-mm.db"
        monkeypatch.setattr(MmDatabase, "DB_PATH", sandbox)
        monkeypatch.setattr(MmDatabase, "DB_DIR", tmp_path)

        r = runner.invoke(app, ["peek", str(tiny_png), "--format", "json"])
        assert r.exit_code == 0
        assert not sandbox.exists(), "peek must not touch the SQLite store"


# ── CLI: format conformance ───────────────────────────────────────────


class TestPeekFormats:
    def test_json(self, tiny_png: Path):
        r = runner.invoke(app, ["peek", str(tiny_png), "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.stdout)
        assert isinstance(data, list) and len(data) == 1
        assert data[0]["kind"] == "image"
        assert data[0]["dimensions"] == "64x48"

    def test_pretty_json_indents(self, tiny_png: Path):
        r = runner.invoke(app, ["peek", str(tiny_png), "--format", "pretty-json"])
        assert r.exit_code == 0
        # Same wire shape as ``json`` — same parsed result, just whitespace differs.
        compact = runner.invoke(app, ["peek", str(tiny_png), "--format", "json"])
        assert json.loads(r.stdout) == json.loads(compact.stdout)
        # And the serialised form has line breaks + 2-space indent.
        assert r.stdout.count("\n") >= 4
        assert "  " in r.stdout

    def test_tsv(self, tiny_png: Path):
        r = runner.invoke(app, ["peek", str(tiny_png), "--format", "tsv"])
        assert r.exit_code == 0
        # ``splitlines()`` rather than ``.strip().splitlines()`` so trailing
        # empty cells (None fields rendered as "") aren't lost when a row
        # ends in tabs.
        lines = [ln for ln in r.stdout.splitlines() if ln]
        assert len(lines) == 2  # header + one row
        header = lines[0].split("\t")
        row = lines[1].split("\t")
        assert "kind" in header
        assert len(header) == len(row)
        assert "image" in row

    def test_csv(self, tiny_png: Path):
        r = runner.invoke(app, ["peek", str(tiny_png), "--format", "csv"])
        assert r.exit_code == 0
        lines = [ln for ln in r.stdout.splitlines() if ln]
        assert len(lines) == 2
        header = lines[0].split(",")
        assert "kind" in header

    def test_default_rich_format(self, tiny_png: Path):
        """Without ``--format``, peek emits a Rich panel (kind label appears)."""
        r = runner.invoke(app, ["peek", str(tiny_png)])
        assert r.exit_code == 0
        assert "image" in r.stdout
        assert "photo.png" in r.stdout


# ── CLI: multiple files ───────────────────────────────────────────────


class TestPeekMultiFile:
    def test_multiple_files_emit_one_row_each(self, tiny_png: Path, tiny_txt: Path):
        r = runner.invoke(
            app,
            ["peek", str(tiny_png), str(tiny_txt), "--format", "json"],
        )
        assert r.exit_code == 0
        data = json.loads(r.stdout)
        assert len(data) == 2
        kinds = {row["kind"] for row in data}
        assert kinds == {"image", "text"}

    def test_tsv_consistent_columns_across_kinds(self, tiny_png: Path, tiny_txt: Path):
        """Flat shape means every row has the same column count, even when fields differ."""
        r = runner.invoke(
            app,
            ["peek", str(tiny_png), str(tiny_txt), "--format", "tsv"],
        )
        assert r.exit_code == 0
        # Don't ``.strip()`` — that would clip trailing empty cells (a
        # text-kind row ends in many ``None``s rendered as ``""``).
        lines = [ln for ln in r.stdout.splitlines() if ln]
        assert len(lines) == 3  # header + 2 data rows
        col_counts = {len(line.split("\t")) for line in lines}
        assert len(col_counts) == 1  # all rows same column count


# ── CLI: error handling ───────────────────────────────────────────────


class TestPeekErrors:
    def test_no_files_exits_nonzero(self):
        r = runner.invoke(app, ["peek"])
        assert r.exit_code != 0

    def test_nonexistent_file_exits_nonzero(self, tmp_path: Path):
        r = runner.invoke(app, ["peek", str(tmp_path / "nope.png")])
        combined = (r.output or "") + (getattr(r, "stderr", "") or "")
        assert "not found" in combined.lower()

    def test_directory_path_rejected(self, tmp_path: Path):
        """``peek`` is per-file; passing a directory should be flagged."""
        r = runner.invoke(app, ["peek", str(tmp_path)])
        combined = (r.output or "") + (getattr(r, "stderr", "") or "")
        assert "not a regular file" in combined.lower()
