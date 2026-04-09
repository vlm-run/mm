from __future__ import annotations

import hashlib
import time
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


def now_us() -> int:
    return int(time.time() * 1_000_000)


def get_l2_id(
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
