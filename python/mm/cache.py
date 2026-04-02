"""Result cache for mm.

L1 cache: expensive content extractions (PDF text, document conversion) keyed
by content hash. Cache location: ~/.cache/mm/l1/

L2 cache: LLM-generated results (captions, descriptions, transcriptions) keyed
by content hash + profile name + model + extraction parameters.
Cache location: ~/.cache/mm/l2/
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

_L1_CACHE_DIR = Path.home() / ".cache" / "mm" / "l1"
_CACHE_DIR = Path.home() / ".cache" / "mm" / "l2"


# ---------------------------------------------------------------------------
# L1 cache — keyed by content hash only
# ---------------------------------------------------------------------------


def _l1_cache_key(content_hash: str) -> str:
    """Build a deterministic L1 cache key from content hash."""
    return hashlib.sha256(content_hash.encode()).hexdigest()[:24]


def get_l1(content_hash: str) -> str | None:
    """Return cached L1 result, or None if not cached."""
    key = _l1_cache_key(content_hash)
    path = _L1_CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("content")
    except Exception:
        return None


def put_l1(content_hash: str, content: str) -> None:
    """Store an L1 result in the cache."""
    key = _l1_cache_key(content_hash)
    _L1_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _L1_CACHE_DIR / f"{key}.json"
    data: dict[str, Any] = {
        "content_hash": content_hash,
        "content": content,
        "timestamp": time.time(),
    }
    path.write_text(json.dumps(data, ensure_ascii=False))


# ---------------------------------------------------------------------------
# L2 cache — keyed by content hash + profile + model + extraction params
# ---------------------------------------------------------------------------


def _cache_key(
    content_hash: str,
    profile: str,
    model: str,
    mode: str | None,
    detail: bool,
    *,
    extra: str = "",
) -> str:
    """Build a deterministic cache key from extraction parameters."""
    raw = f"{content_hash}:{profile}:{model}:{mode or ''}:{detail}:{extra}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def get(
    content_hash: str,
    profile: str,
    model: str,
    mode: str | None = None,
    detail: bool = False,
    extra: str = "",
) -> str | None:
    """Return cached L2 result, or None if not cached."""
    key = _cache_key(
        content_hash,
        profile,
        model,
        mode,
        detail,
        extra=extra,
    )
    path = _CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        content: str | None = data.get("content")
        return content
    except Exception:
        return None


def put(
    content_hash: str,
    profile: str,
    model: str,
    content: str,
    mode: str | None = None,
    detail: bool = False,
    *,
    extra: str = "",
) -> None:
    """Store an L2 result in the cache."""
    key = _cache_key(
        content_hash,
        profile,
        model,
        mode,
        detail,
        extra=extra,
    )
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _CACHE_DIR / f"{key}.json"
    data: dict[str, Any] = {
        "content_hash": content_hash,
        "profile": profile,
        "model": model,
        "mode": mode,
        "detail": detail,
        "content": content,
        "timestamp": time.time(),
    }
    path.write_text(json.dumps(data, ensure_ascii=False))


_IMAGE_EXTS = frozenset((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"))


def get_content_hash(path: Path, *, use_phash: bool = True) -> str | None:
    """Get a cache-suitable hash for a file.

    Uses the fast Rust xxh3 mmap hash directly (no Scanner overhead).

    Args:
        path: File to hash.
        use_phash: If True (default), images use perceptual hash so visually
            identical files share cache entries. Set False for L1 caching
            where results depend on exact file content.
    """
    try:
        from mm._mm import content_hash

        if use_phash and path.suffix.lower() in _IMAGE_EXTS:
            if phash := _phash_for_image(path):
                return phash
        return content_hash(str(path))
    except Exception:
        return None


def _phash_for_image(path: Path) -> str | None:
    """Get perceptual hash for an image directly via Rust."""
    try:
        from mm._mm import perceptual_hash

        phash = perceptual_hash(str(path))
        if phash is not None:
            return f"phash:{phash:016x}"
    except Exception:
        pass
    return None
