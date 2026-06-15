from __future__ import annotations

import hashlib
import time
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mm.constants import DOCUMENT_EXTS, IMAGE_EXTS

if TYPE_CHECKING:
    from mm._mm import Scanner
    from mm.store.db import MmDatabase


@cache
def shared_db() -> MmDatabase:
    """Process-wide :class:`MmDatabase` instance."""
    from mm.store.db import MmDatabase

    return MmDatabase()


def get_content_hash(path: Path) -> str | None:
    """Get a cache-suitable hash for a file.

    Uses perceptual hash for images (resize-invariant) and xxh3 content
    hash for everything else.

    Args:
        path: Absolute path to the file.

    Returns:
        Hex hash string prefixed with ``phash:`` for images, or a plain
        16-char hex xxh3 digest.  ``None`` on failure.
    """
    try:
        from mm._mm import content_hash, perceptual_hash

        if path.suffix.lower() in IMAGE_EXTS:
            if phash := perceptual_hash(str(path)):
                return f"phash:{phash:016x}"
        return content_hash(str(path))
    except Exception:
        return None


def now_us() -> int:
    return int(time.time() * 1_000_000)


def get_extraction_id(
    content_hash: str,
    profile: str,
    model: str,
    mode: str | None,
    detail: bool,
    *,
    extra: str = "",
) -> str:
    """Build a deterministic key from extraction parameters."""
    raw = f"{content_hash}:{profile}:{model}:{mode or ''}:{detail}:{extra}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def prune_missing(
    *,
    prefix: str | None = None,
    uris: list[str] | None = None,
    disk_uris: set[str] | None = None,
    db: MmDatabase | None = None,
) -> int:
    """Delete ``files`` rows whose paths no longer exist on disk.

    Pass *prefix* to scope by URI prefix (``uri LIKE '<prefix>/%'``), or
    *uris* to target a specific list. If *disk_uris* is provided, only
    rows absent from that set are stat-checked — this avoids false
    positives when the caller's scan excluded on-disk files (gitignored,
    kind/ext filtered, etc.). With no *disk_uris* hint, every candidate
    is stat-checked.

    Strictly one-way: prunes DB → disk parity. Files on disk that are
    not in the DB are untouched (that's the normal "unindexed" state).

    Returns the number of rows deleted.
    """
    if prefix is None and uris is None:
        raise ValueError("prune_missing requires either prefix or uris")

    from mm.store.db import MmDatabase

    if db is None:
        db = MmDatabase()

    if uris is not None:
        candidates = list(uris)
    else:
        assert prefix is not None
        rows = db._connect.execute(
            "SELECT uri FROM files WHERE uri LIKE ?", (f"{prefix}/%",)
        ).fetchall()
        candidates = [r[0] for r in rows]

    if disk_uris is not None:
        candidates = [u for u in candidates if u not in disk_uris]

    missing = [u for u in candidates if not Path(u).exists()]
    return db.delete_files(missing)


def fill_metadata(
    db: MmDatabase,
    uri: str,
    p: Path,
    scanner: Scanner,
    *,
    rel_path: str | None = None,
    commit: bool = False,
) -> None:
    """Run the Rust per-kind extractor and write every populated column."""
    from mm.store.schema import FileCol

    lookup = rel_path if rel_path is not None else p.name
    try:
        r = scanner.extract_metadata(lookup)
    except Exception:
        return

    data: dict[str, Any] = {}
    metadata_map = {
        "content_hash": FileCol.CONTENT_HASH,
        "line_count": FileCol.LINE_COUNT,
        "word_count": FileCol.WORD_COUNT,
        "language": FileCol.LANGUAGE,
        "dimensions": FileCol.DIMENSIONS,
        "pages": FileCol.PAGES,
        "duration_s": FileCol.DURATION_S,
        "fps": FileCol.FPS,
        "magic_mime": FileCol.MAGIC_MIME,
        "exif_camera": FileCol.EXIF_CAMERA,
        "exif_date": FileCol.EXIF_DATE,
        "exif_gps": FileCol.EXIF_GPS,
        "exif_orientation": FileCol.EXIF_ORIENTATION,
        "video_codec": FileCol.VIDEO_CODEC,
        "audio_codec": FileCol.AUDIO_CODEC,
    }
    for attr, col in metadata_map.items():
        if (val := getattr(r, attr, None)) is not None:
            data[col] = val

    if r.has_audio is not None:
        data[FileCol.HAS_AUDIO] = int(r.has_audio)
    if r.phash is not None:
        data[FileCol.PHASH] = f"{r.phash:016x}"

    if r.pages is None and p.suffix.lower() in DOCUMENT_EXTS:
        from mm.peek import _doc_props

        props = _doc_props(p)
        if props.get("pages") is not None:
            data[FileCol.PAGES] = props["pages"]

    if data:
        sets = ", ".join(f"{k} = ?" for k in data)
        db._connect.execute(f"UPDATE files SET {sets} WHERE uri = ?", (*data.values(), uri))
        if commit:
            db._connect.commit()
