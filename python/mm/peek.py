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

from magika import Magika

from mm.utils import file_kind

PeekKind = Literal["image", "video", "audio", "document", "text"]
_magika_future = ThreadPoolExecutor(max_workers=1).submit(Magika)


@cache
def _magika():
    return _magika_future.result()


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
    def from_path(cls, path: Path | str) -> FileMetadata:
        """Build a :class:`FileMetadata` for *path* via the Rust scanner.

        Pure read used by ``mm peek`` as the metadata-tier provider.
        """
        from mm._mm import Scanner
        from mm.constants import guess_mime

        p = Path(path)
        scanner = Scanner(str(p.parent))
        scanner.scan()
        r = scanner.extract_metadata(p.name)
        size = p.stat().st_size

        try:
            result = _magika().identify_path(p)
            aimeta = {**result.output.__dict__, "confidence": result.score}
        except Exception:
            aimeta = None

        return cls(
            path=str(p.resolve()),
            name=p.name,
            size=size,
            mime=guess_mime(p.name, fallback="application/octet-stream"),
            kind=file_kind(p),  # type: ignore[arg-type]
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
            pages=r.pages,
            content_hash=r.content_hash,
            magic_mime=r.magic_mime,
            aimeta=aimeta,
        )
