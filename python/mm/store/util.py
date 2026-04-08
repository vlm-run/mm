from __future__ import annotations

from pathlib import Path

_IMAGE_EXTS = frozenset((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"))


def get_content_hash(path: Path) -> str | None:
    """Get a cache-suitable hash for a file."""
    try:
        from mm._mm import content_hash, perceptual_hash

        if path.suffix.lower() in _IMAGE_EXTS:
            if phash := perceptual_hash(str(path)):
                return f"phash:{phash:016x}"
        return content_hash(str(path))
    except Exception:
        return None
