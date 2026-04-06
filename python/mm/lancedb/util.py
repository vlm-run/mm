"""This module provides the content hashing function (Rust, no DB dependency) and a shared
MmDatabase instance for callers that don't have one.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mm.lancedb.db import MmDatabase


_db: MmDatabase | None = None


_IMAGE_EXTS = frozenset((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"))


def get_db() -> MmDatabase:
    """Lazy-load a shared MmDatabase instance."""
    global _db
    if _db is None:
        from mm.lancedb.db import MmDatabase

        _db = MmDatabase()
    return _db


def get_content_hash(path: Path, *, use_phash: bool = True) -> str | None:
    """Get a cache-suitable hash for a file."""
    try:
        from mm._mm import content_hash, perceptual_hash

        if use_phash and path.suffix.lower() in _IMAGE_EXTS:
            if phash := perceptual_hash(str(path)):
                return f"phash:{phash:016x}"
        return content_hash(str(path))
    except Exception:
        return None
