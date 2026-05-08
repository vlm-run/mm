"""Tests for ``mm peek`` and the :class:`FileMetadata` shape."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mm.cli import app
from mm.constants import OFFICE_EXTS
from mm.peek import FileMetadata
from typer.testing import CliRunner

from .test_utils import write_png

runner = CliRunner()


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def tiny_png(tmp_path: Path) -> Path:
    p = tmp_path / "photo.png"
    write_png(p, 64, 48)
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
            "doc_author",
            "doc_title",
            "doc_subject",
            "doc_keywords",
            "doc_creator",
            "doc_producer",
            "content_hash",
            "magic_mime",
            "aimeta",
        }
        assert set(d.keys()) == expected_keys

    def test_aimeta_field_present_in_shape(self, tiny_png: Path):
        """``aimeta`` is part of the shape; populated by magika or ``None``."""
        fm = FileMetadata.from_path(tiny_png)
        assert fm.aimeta is None or isinstance(fm.aimeta, dict)


# ── Document properties (PDF / DOCX / PPTX) ───────────────────────────


def _build_pdf(path: Path, *, author: str, title: str, subject: str, pages: int = 1) -> None:
    """Hand-craft a minimal valid PDF with N pages and an `/Info` dict.

    pypdfium2 has no public metadata writer, so we emit one by hand. The
    layout is fixed (catalog → pages → N page objects → info), and offsets
    are computed on the fly so the xref table stays in sync.
    """
    objects: list[bytes] = []
    kids = " ".join(f"{i + 3} 0 R" for i in range(pages))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode())
    for _ in range(pages):
        objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>")
    info_obj = f"<< /Author ({author}) /Title ({title}) /Subject ({subject}) >>".encode()
    objects.append(info_obj)
    info_obj_num = len(objects)

    body = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(body))
        body += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_off = len(body)
    body += f"xref\n0 {len(objects) + 1}\n".encode()
    body += b"0000000000 65535 f \n"
    for off in offsets:
        body += f"{off:010d} 00000 n \n".encode()
    body += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info {info_obj_num} 0 R >>\n"
        f"startxref\n{xref_off}\n%%EOF\n"
    ).encode()
    path.write_bytes(bytes(body))


class _StubOfficeMetadata:
    __slots__ = (
        "author",
        "title",
        "subject",
        "description",
        "keywords",
        "created",
        "modified",
        "pages",
    )

    def __init__(self, *, author: str, title: str, subject: str, pages: int | None) -> None:
        self.author = author
        self.title = title
        self.subject = subject
        self.description = ""
        self.keywords: list[str] = []
        self.created = ""
        self.modified = ""
        self.pages = pages


_OFFICE_FIXTURES: dict[str, _StubOfficeMetadata] = {}


def _build_office_doc(
    path: Path,
    *,
    author: str,
    title: str,
    subject: str,
    pages: int | None = None,
) -> None:
    ext = path.suffix.lower()
    if ext not in OFFICE_EXTS:
        raise ValueError(f"unsupported office extension: {ext}")
    path.write_bytes(b"")
    _OFFICE_FIXTURES[str(path.resolve())] = _StubOfficeMetadata(
        author=author, title=title, subject=subject, pages=pages
    )


def _stub_office_metadata(path: str) -> _StubOfficeMetadata:
    key = str(Path(path).resolve())
    try:
        return _OFFICE_FIXTURES[key]
    except KeyError:
        raise RuntimeError(f"no fixture registered for {path}") from None


class TestDocumentProperties:
    """``mm peek`` surfaces author/title/subject + pages for PDF and office docs."""

    @pytest.fixture(autouse=True)
    def _patch_office_metadata(self, monkeypatch):
        from mm import _mm

        _OFFICE_FIXTURES.clear()
        monkeypatch.setattr(_mm, "office_metadata", _stub_office_metadata)

    def test_pdf_props_and_pages(self, tmp_path: Path):
        pdf = tmp_path / "paper.pdf"
        _build_pdf(pdf, author="Alice", title="A Paper", subject="physics", pages=3)
        fm = FileMetadata.from_path(pdf, full=True)
        assert fm.kind == "document"
        assert fm.doc_author == "Alice"
        assert fm.doc_title == "A Paper"
        assert fm.doc_subject == "physics"
        # The fixture omits /Creator and /Producer, so they stay null.
        assert fm.doc_creator is None
        assert fm.doc_producer is None
        assert fm.pages == 3

    def test_pdf_props_and_pages_needs_full_flag(self, tmp_path: Path):
        pdf = tmp_path / "paper.pdf"
        _build_pdf(pdf, author="Alice", title="A Paper", subject="physics", pages=3)
        fm = FileMetadata.from_path(pdf)
        assert fm.kind == "document"

        assert fm.doc_author is None
        assert fm.doc_title is None
        assert fm.doc_subject is None
        assert fm.pages is None

    @pytest.mark.parametrize(
        "ext, pages",
        [
            (".docx", None),
            (".odt", None),
            (".pptx", 4),
            (".odp", 5),
            (".xlsx", 3),
            (".ods", 2),
        ],
    )
    def test_office_doc_props(self, tmp_path: Path, ext: str, pages: int | None):
        path = tmp_path / f"sample{ext}"
        _build_office_doc(path, author="Bob", title="Spec", subject="research", pages=pages)
        fm = FileMetadata.from_path(path, full=True)
        assert fm.kind == "document"
        assert fm.doc_author == "Bob"
        assert fm.doc_title == "Spec"
        assert fm.doc_subject == "research"
        assert fm.pages == pages
        assert fm.doc_creator is None
        assert fm.doc_producer is None

    def test_office_props_needs_full_flag(self, tmp_path: Path):
        docx = tmp_path / "spec.docx"
        _build_office_doc(docx, author="Bob", title="Spec", subject="research")
        fm = FileMetadata.from_path(docx)
        assert fm.kind == "document"
        assert fm.doc_author is None
        assert fm.doc_title is None
        assert fm.doc_subject is None
        assert fm.pages is None

    def test_non_document_kind_has_null_doc_fields(self, tiny_png: Path):
        fm = FileMetadata.from_path(tiny_png)
        assert fm.doc_author is None
        assert fm.doc_title is None
        assert fm.doc_subject is None
        assert fm.doc_creator is None
        assert fm.doc_producer is None

    def test_pdf_doc_fields_in_peek_json(self, tmp_path: Path):
        pdf = tmp_path / "paper.pdf"
        _build_pdf(pdf, author="Dee", title="JSON OK", subject="serialization")
        r = runner.invoke(app, ["peek", str(pdf), "--format", "json", "--full"])
        assert r.exit_code == 0, r.output
        rows = json.loads(r.stdout)
        assert rows[0]["doc_author"] == "Dee"
        assert rows[0]["doc_title"] == "JSON OK"
        assert rows[0]["pages"] == 1

    def test_corrupt_pdf_falls_back_silently(self, tmp_path: Path):
        """A non-PDF byte blob with a .pdf suffix must not crash ``peek``."""
        pdf = tmp_path / "bad.pdf"
        pdf.write_bytes(b"not a pdf at all")
        fm = FileMetadata.from_path(pdf)
        assert fm.doc_author is None
        assert fm.pages is None


# ── magika integration ───────────────────────────────────────────────


class _FakeMagikaOutput:
    def __init__(self, label, mime_type, group, description, extensions, is_text):
        self.label = label
        self.mime_type = mime_type
        self.group = group
        self.description = description
        self.extensions = extensions
        self.is_text = is_text


class _FakeMagikaResult:
    def __init__(self, output, score):
        self.output = output
        self.score = score


class _FakeMagika:
    """Deterministic stand-in keyed by extension + PDF magic bytes."""

    _BY_EXT = {
        ".py": ("python", "text/x-python", "code", "Python source", ["py"], True),
        ".png": ("png", "image/png", "image", "PNG image", ["png"], False),
        ".pdf": ("pdf", "application/pdf", "document", "PDF document", ["pdf"], False),
    }

    def identify_path(self, path):
        from pathlib import Path as _P

        p = _P(path)
        try:
            head = p.open("rb").read(4)
        except Exception:
            head = b""
        if head == b"%PDF":
            row = self._BY_EXT[".pdf"]
        else:
            row = self._BY_EXT.get(
                p.suffix.lower(),
                ("unknown", "application/octet-stream", "unknown", "Unknown", [], False),
            )
        return _FakeMagikaResult(_FakeMagikaOutput(*row), 0.99)


class TestMagikaExtra:
    """``FileMetadata.aimeta`` carries ``magika.identify_path(...).output.__dict__``."""

    EXPECTED_KEYS = {
        "label",
        "mime_type",
        "group",
        "description",
        "extensions",
        "is_text",
        "confidence",
    }

    @pytest.fixture(autouse=True)
    def _mock_magika(self, monkeypatch):
        """Stub out the real magika model so CI doesn't depend on its weights."""
        from mm import peek

        monkeypatch.setattr(peek, "_magika", lambda: _FakeMagika())

    def test_python_source_classified_as_python(self, tiny_txt: Path):
        fm = FileMetadata.from_path(tiny_txt)
        assert fm.aimeta is not None
        assert set(fm.aimeta.keys()) == self.EXPECTED_KEYS
        assert fm.aimeta["label"] == "python"
        assert fm.aimeta["group"] == "code"
        assert fm.aimeta["is_text"] is True
        assert fm.aimeta["mime_type"] == "text/x-python"
        assert "py" in fm.aimeta["extensions"]

    def test_png_classified_as_image(self, tiny_png: Path):
        fm = FileMetadata.from_path(tiny_png)
        assert fm.aimeta is not None
        assert set(fm.aimeta.keys()) == self.EXPECTED_KEYS
        assert fm.aimeta["mime_type"].startswith("image/")
        assert fm.aimeta["is_text"] is False

    def test_extensions_is_list_of_str(self, tiny_txt: Path):
        fm = FileMetadata.from_path(tiny_txt)
        assert fm.aimeta is not None
        exts = fm.aimeta["extensions"]
        assert isinstance(exts, list)
        assert all(isinstance(e, str) for e in exts)

    def test_pdf_classified_as_pdf(self, tmp_path: Path):
        """Real PDF magic bytes should classify as the ``pdf`` label."""
        pdf = tmp_path / "tiny.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%fake content\n%%EOF\n")
        fm = FileMetadata.from_path(pdf)
        assert fm.aimeta is not None
        assert fm.aimeta["label"] == "pdf"
        assert fm.aimeta["mime_type"] == "application/pdf"

    def test_aimeta_is_json_serializable(self, tiny_txt: Path):
        """``aimeta`` must round-trip through ``json.dumps`` cleanly."""
        fm = FileMetadata.from_path(tiny_txt)
        assert fm.aimeta is not None
        encoded = json.dumps(fm.aimeta)
        decoded = json.loads(encoded)
        assert decoded["label"] == "python"
        assert decoded["is_text"] is True

    def test_aimeta_appears_in_peek_json_output(self, tiny_txt: Path):
        """``mm peek --format json`` round-trip exposes ``aimeta`` to consumers."""
        r = runner.invoke(app, ["peek", str(tiny_txt), "--format", "json"])
        assert r.exit_code == 0
        rows = json.loads(r.stdout.splitlines()[0])
        assert rows[0]["aimeta"] is not None
        assert rows[0]["aimeta"]["label"] == "python"


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
