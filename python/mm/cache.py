"""L2 result cache for mm.

Caches LLM-generated results (captions, descriptions, transcriptions) keyed by
content hash + provider profile + model + extraction parameters.  This avoids
redundant LLM calls when the file content and provider config haven't changed.

Cache location: ~/.cache/mm/l2/
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

_CACHE_DIR = Path.home() / ".cache" / "mm" / "l2"


def _cache_key(
    content_hash: str,
    profile: str,
    model: str,
    mode: str | None,
    detail: bool,
) -> str:
    """Build a deterministic cache key from extraction parameters."""
    raw = f"{content_hash}:{profile}:{model}:{mode or ''}:{detail}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def get(
    content_hash: str,
    profile: str,
    model: str,
    mode: str | None = None,
    detail: bool = False,
) -> str | None:
    """Return cached L2 result, or None if not cached."""
    key = _cache_key(content_hash, profile, model, mode, detail)
    path = _CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("content")
    except Exception:
        return None


def put(
    content_hash: str,
    profile: str,
    model: str,
    content: str,
    mode: str | None = None,
    detail: bool = False,
) -> None:
    """Store an L2 result in the cache."""
    key = _cache_key(content_hash, profile, model, mode, detail)
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


def get_content_hash(path: Path) -> str | None:
    """Get a cache-suitable hash for a file via the Rust scanner.

    Images: uses phash (perceptual hash) so visually identical files with
    different encodings/metadata share cache entries.
    Other types: uses xxh3 content hash.
    """
    try:
        from mm._mm import Scanner

        scanner = Scanner(str(path.parent))
        scanner.scan()
        r = scanner.extract_l1(path.name)
        if path.suffix.lower() in _IMAGE_EXTS and r.phash is not None:
            return f"phash:{r.phash:016x}"
        return r.content_hash
    except Exception:
        return None
