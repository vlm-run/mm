from __future__ import annotations

import hashlib
import time
from pathlib import Path

from mm.constants import IMAGE_EXTS


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
