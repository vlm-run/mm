"""Image encoding strategies: resize and tile.

Provides ``ImageResize`` and ``ImageTile`` strategies that transform image
files into OpenAI-compatible Message dicts.  Both use a Rust fast-path
(``mm._mm.resize_image`` / ``tile_image``) with an automatic Pillow fallback
when the native extension is unavailable.

Typical usage::

    from mm.encoders import process_image, process_image_tiled

    msg = process_image(Path("photo.jpg"), max_width=1024)
    tiles = list(process_image_tiled(Path("scan.tiff"), tile_size=1024))
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Union

from mm.constants import IMAGE_EXTS
from mm.encoders import Message, _resolve_provider, register

if TYPE_CHECKING:
    from PIL import Image

logger = logging.getLogger(__name__)

# Default JPEG quality — matches the Rust side (serde/image.rs).
_JPEG_QUALITY: int = 85


def _open_image_with_exif(path: Union[Path, str]) -> "Image.Image":
    """Open an image and apply EXIF orientation if present.

    Args:
        path: Path to the image file.

    Returns:
        PIL Image with EXIF orientation applied.
    """
    from PIL import Image as PILImage  # noqa: N811
    from PIL import ImageOps

    img = PILImage.open(str(path))
    try:
        transposed = ImageOps.exif_transpose(img)
        if transposed is not None:
            img = transposed  # type: ignore[assignment]
    except Exception:
        pass
    return img


def _validate_image_path(path: Path) -> None:
    """Raise early if *path* is not a readable image file.

    Args:
        path: Path to validate.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the extension is not a recognised image type.
    """
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    if path.suffix.lower() not in IMAGE_EXTS:
        raise ValueError(
            f"Unsupported image type: {path.suffix}. "
            f"Supported: {', '.join(sorted(IMAGE_EXTS))}"
        )


def _openai_image_part(b64: str, mime: str) -> dict[str, Any]:
    """Build an OpenAI ``image_url`` content part."""
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{b64}"},
    }


def _gemini_image_part(b64: str, mime: str) -> dict[str, Any]:
    """Build a Gemini ``inline_data`` content part."""
    return {"inline_data": {"mime_type": mime, "data": b64}}


def _image_part(b64: str, mime: str, provider: str) -> dict[str, Any]:
    """Build a provider-appropriate image content part.

    Args:
        b64: Base64-encoded image bytes.
        mime: MIME type string.
        provider: ``"openai"`` or ``"gemini"``.
    """
    if provider == "gemini":
        return _gemini_image_part(b64, mime)
    return _openai_image_part(b64, mime)


def _to_message(parts: list[dict[str, Any]]) -> Message:
    """Wrap content parts in a complete Message dict."""
    return {"role": "user", "content": parts}


def _encode_pil_image(
    img: "Image.Image",
    source_path: Path,
    *,
    quality: int = _JPEG_QUALITY,
) -> tuple[str, str]:
    """Encode a PIL Image to base64.

    Chooses PNG for images with alpha or ``.png`` sources; JPEG otherwise.
    For JPEG, uses ``subsampling=0`` (4:4:4 chroma) for maximum fidelity.

    Args:
        img: PIL Image to encode.
        source_path: Original file path (used for format heuristics).
        quality: JPEG quality 1–100.

    Returns:
        ``(base64_str, mime_str)`` tuple.
    """
    has_alpha = img.mode in ("RGBA", "LA", "PA")
    fmt = "PNG" if has_alpha or source_path.suffix.lower() == ".png" else "JPEG"
    mime = "image/png" if fmt == "PNG" else "image/jpeg"

    if fmt == "JPEG" and img.mode != "RGB":
        img = img.convert("RGB")

    buf = io.BytesIO()
    save_kwargs: dict[str, Any] = {"format": fmt}
    if fmt == "JPEG":
        save_kwargs["quality"] = quality
        save_kwargs["subsampling"] = 0  # 4:4:4 — no chroma subsampling
    img.save(buf, **save_kwargs)

    b64 = base64.b64encode(buf.getvalue()).decode()
    return b64, mime


def _pillow_resize(path: Path, max_width: int) -> dict[str, Any]:
    """Pillow fallback for image resize.

    Fits the image into a ``max_width x max_width`` bounding box while
    preserving aspect ratio.  Applies EXIF orientation before resizing.

    Args:
        path: Path to the source image.
        max_width: Maximum dimension (width or height) in pixels.

    Returns:
        Dict with keys ``base64``, ``mime``, ``width``, ``height``.
    """
    img = _open_image_with_exif(path)
    orig_w, orig_h = img.size

    if orig_w > max_width or orig_h > max_width:
        scale: float = min(max_width / orig_w, max_width / orig_h)
        new_w = round(orig_w * scale)
        new_h = round(orig_h * scale)
        from PIL import Image as _PILImage

        img = img.resize((new_w, new_h), _PILImage.Resampling.LANCZOS)

    w, h = img.size
    b64, mime = _encode_pil_image(img, path)
    logger.debug(
        "pillow_resize [path=%s, %dx%d -> %dx%d, mime=%s, b64_len=%d]",
        path.name, orig_w, orig_h, w, h, mime, len(b64),
    )
    return {"base64": b64, "mime": mime, "width": w, "height": h}


def _pillow_tile(path: Path, tile_size: int) -> list[dict[str, Any]]:
    """Pillow fallback for image tiling.

    Splits the image into ``tile_size x tile_size`` crops and encodes
    each as base64.  Returns a single-element list when the image fits
    within one tile.

    Args:
        path: Path to the source image.
        tile_size: Maximum tile dimension in pixels.

    Returns:
        List of dicts with ``base64``, ``mime``, ``col``, ``row``,
        ``total_cols``, ``total_rows``, ``width``, ``height``.
    """
    img = _open_image_with_exif(path)
    w, h = img.size

    if w <= tile_size and h <= tile_size:
        b64, mime = _encode_pil_image(img, path)
        return [{"base64": b64, "mime": mime, "col": 0, "row": 0,
                 "total_cols": 1, "total_rows": 1, "width": w, "height": h}]

    cols: int = (w + tile_size - 1) // tile_size
    rows: int = (h + tile_size - 1) // tile_size
    tiles: list[dict[str, Any]] = []

    for row_idx in range(rows):
        for col_idx in range(cols):
            x: int = col_idx * tile_size
            y: int = row_idx * tile_size
            tw: int = min(tile_size, w - x)
            th: int = min(tile_size, h - y)
            tile_img = img.crop((x, y, x + tw, y + th))
            b64, mime = _encode_pil_image(tile_img, path)
            tiles.append({
                "base64": b64, "mime": mime,
                "col": col_idx, "row": row_idx,
                "total_cols": cols, "total_rows": rows,
                "width": tw, "height": th,
            })

    logger.debug(
        "pillow_tile [path=%s, %dx%d, tile_size=%d, tiles=%d]",
        path.name, w, h, tile_size, len(tiles),
    )
    return tiles


class ImageResize:
    """Resize an image to fit a bounding box, then base64 encode.

    The default strategy.  Fits the image into a ``max_width x max_width``
    bounding box (default 1024 px) while preserving aspect ratio and EXIF
    orientation.  Uses the Rust fast-path when available.

    Kwargs:
        max_width: Maximum dimension in pixels (default 1024).
    """

    name: str = "resize"
    media_types: tuple[str, ...] = ("image",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        max_width: int = kwargs.get("max_width", 1024)
        provider: str = _resolve_provider()

        try:
            from mm._mm import resize_image

            result: dict[str, Any] = resize_image(str(path), max_width)
        except (ImportError, RuntimeError):
            result = _pillow_resize(path, max_width)

        part = _image_part(result["base64"], result["mime"], provider)
        yield _to_message([part])


class ImageTile:
    """Tile a large image into squares, yielding one Message per tile.

    Falls back to a single tile (resize) when the image is smaller than
    ``tile_size`` in both dimensions.

    Kwargs:
        tile_size: Tile dimension in pixels (default 1024).
    """

    name: str = "tile"
    media_types: tuple[str, ...] = ("image",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        tile_size: int = kwargs.get("tile_size", 1024)
        provider: str = _resolve_provider()

        try:
            from mm._mm import tile_image

            tiles: list[dict[str, Any]] = tile_image(str(path), tile_size)
        except (ImportError, RuntimeError):
            tiles = _pillow_tile(path, tile_size)

        for tile in tiles:
            part = _image_part(tile["base64"], tile["mime"], provider)
            yield _to_message([part])


register(ImageResize())
register(ImageTile())
