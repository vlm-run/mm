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
        path.name,
        orig_w,
        orig_h,
        w,
        h,
        mime,
        len(b64),
    )
    return {"base64": b64, "mime": mime, "width": w, "height": h}


class ImageResize:
    """Resize an image to fit a bounding box, then base64 encode.

    The default strategy. Fits the image into a ``max_width x max_width``
    bounding box (default 1024 px) while preserving aspect ratio and EXIF
    orientation. Uses the Rust fast-path when available.

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

        part = _image_part(str(result["base64"]), str(result["mime"]), provider)
        yield _to_message([part])


class ImageTile:
    """Resize the full image + tile it, yielding overview and tiles in one Message.

    The Message contains:
      1. A text header describing the layout.
      2. The full image resized to ``max_width`` (overview for global context).
      3. Each ``max_width x max_width`` tile crop from the original (fine detail).

    If the image already fits within a single tile, only the resized
    overview is returned (no redundant duplicate).

    Kwargs:
        max_width: Pixel size for both tile dimension and overview
            bounding box (default 1024).
    """

    name: str = "tile"
    media_types: tuple[str, ...] = ("image",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        max_width: int = kwargs.get("max_width", 1024)
        provider: str = _resolve_provider()

        img = _open_image_with_exif(path)
        w, h = img.size

        from PIL import Image as PILImage

        if w > max_width or h > max_width:
            scale = min(max_width / w, max_width / h)
            overview = img.resize(
                (round(w * scale), round(h * scale)),
                PILImage.Resampling.LANCZOS,
            )
        else:
            overview = img

        overview_b64, overview_mime = _encode_pil_image(overview, path)

        cols = (w + max_width - 1) // max_width
        rows = (h + max_width - 1) // max_width
        single_tile = cols == 1 and rows == 1

        if single_tile:
            parts: list[dict[str, Any]] = [
                _image_part(overview_b64, overview_mime, provider),
            ]
            logger.debug(
                "tile [path=%s, %dx%d, fits in one tile]",
                path.name,
                w,
                h,
            )
            yield _to_message(parts)
            return

        parts = [
            {
                "type": "text",
                "text": (
                    f"{path.name} ({w}x{h}) — overview + {cols}x{rows} "
                    f"tiles ({cols * rows} crops at {max_width}px):"
                ),
            },
            _image_part(overview_b64, overview_mime, provider),
        ]

        for row_idx in range(rows):
            for col_idx in range(cols):
                x = col_idx * max_width
                y = row_idx * max_width
                tw = min(max_width, w - x)
                th = min(max_width, h - y)
                tile_img = img.crop((x, y, x + tw, y + th))
                tile_b64, tile_mime = _encode_pil_image(tile_img, path)
                parts.append(_image_part(tile_b64, tile_mime, provider))

        logger.debug(
            "tile [path=%s, %dx%d, grid=%dx%d, parts=%d]",
            path.name,
            w,
            h,
            cols,
            rows,
            len(parts),
        )
        yield _to_message(parts)


register(ImageResize())
register(ImageTile())
