"""File-metadata response shape and direct-extraction entry point.

``mm peek`` returns the locally-extracted file metadata
(dimensions / EXIF / codec / duration / mime / hash …) for one or
more files without touching the SQLite store. Output is the flat
:class:`FileMetadata` dataclass with all kind-specific fields nullable
— predictable JSON shape for piping through ``jq``/``awk`` and
Rich tables hide unset cells naturally.

Identification fields (``mime`` / ``magic_mime`` / ``content_hash``)
come from the Rust scanner. The ``aimeta`` field carries magika's
AI-classified content type plus a confidence score.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal

from mm.utils import file_kind

PeekKind = Literal["image", "video", "audio", "document", "text"]


def _preload_magika():
    try:
        from magika import Magika

        return ThreadPoolExecutor(max_workers=1).submit(Magika)
    except ImportError:
        return None


_magika_future = _preload_magika()


@cache
def _magika():
    if _magika_future is None:
        raise RuntimeError("magika is not installed")
    return _magika_future.result()


def _doc_props(path: Path) -> dict[str, Any]:
    """Pull author/title/subject/creator/producer/pages for a document."""
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            return _pdf_props(path)
        else:
            from mm._mm import office_metadata

            v = office_metadata(str(path))
            return {
                "doc_author": v.author or None,
                "doc_title": v.title or None,
                "doc_subject": v.subject or None,
                "doc_keywords": v.keywords or None,
                "doc_creator": None,
                "doc_producer": None,
                "pages": v.pages if v.pages is not None else None,
            }
    except Exception:
        return {}


def _pdf_props(path: Path) -> dict[str, Any]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        info = pdf.get_metadata_dict(skip_empty=True) or {}
        return {
            "doc_author": info.get("Author") or None,
            "doc_title": info.get("Title") or None,
            "doc_subject": info.get("Subject") or None,
            "doc_creator": info.get("Creator") or None,
            "doc_producer": info.get("Producer") or None,
            "pages": len(pdf),
        }
    finally:
        pdf.close()


@dataclass
class FileMetadata:
    """Locally-extracted file metadata, kind-agnostic flat shape."""

    # Identity (always populated)
    path: str
    name: str
    size: int
    mime: str
    kind: PeekKind

    # Visual (image / video)
    dimensions: str | None = None
    phash: int | None = None

    # EXIF (image)
    exif_camera: str | None = None
    exif_date: str | None = None
    exif_gps: str | None = None
    exif_orientation: str | None = None

    # Audio / video
    duration_s: float | None = None
    fps: float | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    has_audio: bool | None = None

    # Document
    pages: int | None = None
    doc_author: str | None = None
    doc_title: str | None = None
    doc_subject: str | None = None
    doc_keywords: list[str] | None = None
    doc_creator: str | None = None
    doc_producer: str | None = None

    # Identification
    content_hash: str | None = None
    magic_mime: str | None = None

    # AI-predicted metadata via magika (label, mime_type, group,
    # description, extensions, is_text, confidence)
    aimeta: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializable mapping; ``None`` fields are preserved."""
        return asdict(self)

    @classmethod
    def from_path(cls, path: Path | str, *, full: bool = False) -> FileMetadata:
        """Build a :class:`FileMetadata` for *path* via the Rust scanner.

        Pure read used by ``mm peek`` as the metadata-tier provider.
        """
        from mm._mm import extract_metadata_one
        from mm.constants import guess_mime

        p = Path(path)
        r = extract_metadata_one(p)
        size = p.stat().st_size

        try:
            result = _magika().identify_path(p)
            aimeta = {**result.output.__dict__, "confidence": result.score}
        except Exception:
            aimeta = None

        kind = file_kind(p)
        if full:
            doc = _doc_props(p) if kind == "document" else {}
        else:
            doc = {}

        return cls(
            path=str(p.resolve()),
            name=p.name,
            size=size,
            mime=guess_mime(p.name, fallback="application/octet-stream"),
            kind=kind,  # type: ignore[arg-type]
            dimensions=r.dimensions,
            phash=r.phash,
            exif_camera=r.exif_camera,
            exif_date=r.exif_date,
            exif_gps=r.exif_gps,
            exif_orientation=r.exif_orientation,
            duration_s=r.duration_s,
            fps=r.fps,
            video_codec=r.video_codec,
            audio_codec=r.audio_codec,
            has_audio=r.has_audio,
            pages=doc.get("pages", r.pages),
            doc_author=doc.get("doc_author"),
            doc_title=doc.get("doc_title"),
            doc_subject=doc.get("doc_subject"),
            doc_keywords=doc.get("doc_keywords"),
            doc_creator=doc.get("doc_creator"),
            doc_producer=doc.get("doc_producer"),
            content_hash=r.content_hash,
            magic_mime=r.magic_mime,
            aimeta=aimeta,
        )
