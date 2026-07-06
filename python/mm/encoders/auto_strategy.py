"""
Reads locally-available metadata (no LLM call, no full decode) and maps
file characteristics to the best-fit registered encoder name.

## Characteristics considered

### 1. File kind
Dispatches on image / audio / video / document.  Non-binary kinds
(text, code) are not handled here; callers should guard with
``file_kind(path)``.

### 2. Size × duration thresholds

**Video**
- *Short*  : duration ≤ 10 min **and** size ≤ 25 MB  → ``mosaic``
- *Medium* : duration ≤ 35 min **and** size ≤ 100 MB → ``keyframes``
- *Long*   : > 35 min **or** > 100 MB                → ``summary``
When an audio track is present, the ``-w-transcript`` variant is chosen
for all three tiers.

**Audio**
- *Short compressed* : duration ≤ 5 min **and** size ≤ 10 MB   → ``transcript``
- *All other cases*   : ``native``

**Image**
- *Standard* : size ≤ 10 MB, ≤ 1080p, normal aspect ratio → ``resize``
- *Large/HD* : size > 10 MB **or** any dimension > 4 K    → ``tile``
- *1080p–4 K lossless* (PNG/TIFF/BMP)                     → ``tile``

**Document (PDF)**
- > 100 pages → ``page-text`` (rasterising too many pages is prohibitive)
- ≤ 100 pages, image-heavy (> 500 KB/page):
    - Scanner creator signature → ``rasterize``
    - Otherwise                → ``rasterize-text``
- ≤ 100 pages, text-light                                  → ``page-text``
Non-PDF documents (.docx/.pptx/…) always return ``page-text`` because
they have an extractable text layer.

### 3. Format / losslessness

**Video containers**: MKV, WebM, AVI, WMV, FLV, OGV often carry codecs
(VP8/9, AV1, H.265) that some VLMs reject as raw bytes.  The ``clips``
encoder passes raw video bytes; ``mosaic`` / ``keyframes`` / ``summary``
extract still images instead and are universally safe.  This function
never returns ``clips`` — callers that need clip-based delivery must
request it explicitly.

**Lossless images** (PNG, TIFF, BMP) preserve full bit-depth and are
often larger than equivalent JPEGs at the same resolution.  At 1080p–4 K
lossless images benefit from tiling to stay within VLM token limits.

**HEIC/HEIF** (iPhone photos, typically 4032 × 3024 ≈ 12 MP) exceed
1080p and are treated as high-resolution images; ``tile`` is selected.

### 4. Additional characteristics (not in the original spec)

**Video audio-track absence**: ``has_audio=False`` means transcription
produces nothing.  The ``-w-transcript`` suffix is omitted even when the
size/duration would otherwise qualify.

**Extreme aspect ratios**: Panoramas and tall screenshots (max ÷ min
dimension > 3) are poorly served by ``resize``, which uniformly
downsamples and discards horizontal / vertical detail.  ``tile`` is
chosen regardless of absolute pixel count.

**PDF bytes-per-page as diagram proxy**: A PDF with > 500 KB/page
almost certainly embeds high-resolution rasters (scans, figures).
Byte density is a reliable proxy when the text layer alone cannot reveal
diagram presence.

**PDF creator fingerprint**: Creator strings that match known scanner
software (ScanSnap, TWAIN, HP, AdobeScan, ExactScan) indicate a
scanned document with no meaningful text layer; ``rasterize`` is used
instead of ``rasterize-text`` to avoid wasted text-extraction attempts.
"""

import dataclasses
from pathlib import Path

from mm.cache import memoize_file
from mm.cat_utils.base_utils import CatOpts
from mm.pipelines.schema import PipelineSpec

_MB = 1024 * 1024
_LOSSLESS_EXTS = frozenset({".png", ".tiff", ".tif", ".bmp"})
_HIGH_RES_EXTS = frozenset({".heic", ".heif"})
# Image-heavy PDF: check creator for scanner fingerprints.
_SCANNER_TOKENS = frozenset(
    {
        "scansnap",
        "twain",
        "hp",
        "adobescan",
        "exactscan",
        "scanner",
        "camscanner",
        "scanbot",
        "readiris",
        "epson scan",
    }
)


@memoize_file(maxsize=64)
def auto_strategy(path: Path) -> str:
    """Determine the optimal encoding strategy for a binary media file.

    Args:
        path: Path to the media file.  The file must exist.

    Returns:
        Registered encoder name suitable for passing to ``run_encoder``.

    Raises:
        ValueError: If the file kind is not one of image / audio / video /
            document, or if the file does not exist.
    """
    from mm.utils import file_kind

    kind = file_kind(path)
    if kind not in ("image", "audio", "video", "document"):
        raise ValueError(
            f"auto_strategy only handles binary media kinds; got kind={kind!r} for {path.name}"
        )

    from mm.peek import FileMetadata

    meta = FileMetadata.from_path(path, full=(kind == "document"))
    ext = path.suffix.lower()

    if kind == "video":
        duration = meta.duration_s or 0.0
        size = meta.size
        # Only use transcript variants when an audio track is confirmed present.
        with_tx = bool(meta.has_audio)

        if duration <= 600 and size <= 25 * _MB:
            base = "mosaic"
        elif duration <= 2100 and size <= 100 * _MB:
            base = "keyframes"
        else:
            base = "summary"

        return f"{base}-w-transcript" if with_tx else base

    if kind == "audio":
        duration = meta.duration_s or 0.0
        if duration <= 300 and meta.size <= 10 * _MB:
            return "transcript"
        return "native"

    if kind == "image":
        size = meta.size
        is_lossless = ext in _LOSSLESS_EXTS
        # Parse "WxH" dimensions string; fall back to size-only heuristic.
        width: int = 0
        height: int = 0
        if meta.dimensions:
            try:
                w_str, h_str = meta.dimensions.lower().split("x", 1)
                width, height = int(w_str.strip()), int(h_str.strip())
            except (ValueError, AttributeError):
                pass

        # Extreme aspect ratio → tile regardless of resolution.
        if width > 0 and height > 0:
            long_side = max(width, height)
            short_side = min(width, height)
            if short_side > 0 and long_side / short_side > 3:
                return "tile"

        # Over 4 K or large file size → tile.
        if width > 3840 or height > 2160 or size > 10 * _MB:
            return "tile"

        # HEIC/HEIF is typically 12 MP (≈ 4032×3024) — above 1080p.
        if ext in _HIGH_RES_EXTS:
            return "tile"

        # Lossless above 1080p → tile (full-fidelity files at HD+ sizes).
        if is_lossless and (width > 1920 or height > 1080):
            return "tile"

        return "resize"

    # kind == "document"
    if ext != ".pdf":
        # DOCX, PPTX, ODT, etc. — always have an extractable text layer.
        return "page-text"

    pages = meta.pages or 0
    size = meta.size
    if pages > 100:
        return "page-text"

    if pages > 0:
        bytes_per_page = size / pages
        is_image_heavy = bytes_per_page > 500 * 1024  # 500 KB/page threshold
    else:
        # Unknown page count: use size as a proxy (> 5 MB suggests embedded images).
        is_image_heavy = size > 5 * _MB

    if not is_image_heavy:
        return "page-text"

    creator = (meta.doc_creator or "").lower()
    producer = (meta.doc_producer or "").lower()
    creator_str = f"{creator} {producer}"
    is_scanned = any(tok in creator_str for tok in _SCANNER_TOKENS)

    return "rasterize" if is_scanned else "rasterize-text"


def _spec_replace_strategy(strategy: str, spec: PipelineSpec, opts: CatOpts) -> PipelineSpec:
    """Return a copy of *spec* with ``encode.strategy`` set to *strategy*."""
    from mm.pipelines.pipelines_utils import _apply_encoder_generate

    encode = dataclasses.replace(spec.encode, strategy=strategy)
    _spec = dataclasses.replace(spec, encode=encode)
    return _apply_encoder_generate(_spec, opts)


def resolve_auto_strategy(path: Path, spec: PipelineSpec, opts: CatOpts) -> PipelineSpec:
    """Resolve the encode strategy when it is unspecified or set to ``"auto"``."""
    should_resolve = spec.encode.strategy == "auto" or (
        spec.encode.strategy is None and spec.generate is not None
    )
    if should_resolve:
        return _spec_replace_strategy(auto_strategy(path), spec, opts)
    return spec
