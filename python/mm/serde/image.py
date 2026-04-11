"""Image encoding strategies: resize and tile.

Provides ``ImageResize`` and ``ImageTile`` strategies that transform image
files into OpenAI-compatible Message dicts.  Both use a Rust fast-path
(``mm._mm.resize_image`` / ``tile_image``) with an automatic Pillow fallback
when the native extension is unavailable.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any, Iterable

from mm.constants import guess_mime
from mm.serde import Message, _resolve_provider, register


def _openai_image_part(b64: str, mime: str) -> dict[str, Any]:
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{b64}"},
    }


def _gemini_image_part(b64: str, mime: str) -> dict[str, Any]:
    return {
        "inline_data": {"mime_type": mime, "data": b64},
    }


def _image_part(b64: str, mime: str, provider: str) -> dict[str, Any]:
    if provider == "gemini":
        return _gemini_image_part(b64, mime)
    return _openai_image_part(b64, mime)


def _to_message(parts: list[dict[str, Any]]) -> Message:
    return {"role": "user", "content": parts}


def _pillow_resize(path: Path, max_width: int) -> dict[str, Any]:
    """Pillow fallback for image resize.

    Resizes when either dimension exceeds *max_width*, fitting the image
    into a ``max_width x max_width`` bounding box while preserving
    aspect ratio.
    """
    from PIL import Image

    img = Image.open(path)
    orig_w, orig_h = img.size

    if orig_w > max_width or orig_h > max_width:
        scale = min(max_width / orig_w, max_width / orig_h)
        new_w = round(orig_w * scale)
        new_h = round(orig_h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    w, h = img.size
    has_alpha = img.mode in ("RGBA", "LA", "PA")
    fmt = "PNG" if has_alpha or path.suffix.lower() == ".png" else "JPEG"
    mime = "image/png" if fmt == "PNG" else "image/jpeg"

    if fmt == "JPEG" and img.mode != "RGB":
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, fmt, quality=90)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return {"base64": b64, "mime": mime, "width": w, "height": h}


def _pillow_tile(path: Path, tile_size: int) -> list[dict[str, Any]]:
    """Pillow fallback for image tiling."""
    from PIL import Image

    img = Image.open(path)
    w, h = img.size

    if w <= tile_size and h <= tile_size:
        buf = io.BytesIO()
        fmt = "PNG" if img.mode in ("RGBA", "LA", "PA") else "JPEG"
        mime = "image/png" if fmt == "PNG" else "image/jpeg"
        if fmt == "JPEG" and img.mode != "RGB":
            img = img.convert("RGB")
        img.save(buf, fmt, quality=90)
        b64 = base64.b64encode(buf.getvalue()).decode()
        return [{"base64": b64, "mime": mime, "col": 0, "row": 0,
                 "total_cols": 1, "total_rows": 1, "width": w, "height": h}]

    cols = (w + tile_size - 1) // tile_size
    rows = (h + tile_size - 1) // tile_size
    tiles = []
    for row in range(rows):
        for col in range(cols):
            x = col * tile_size
            y = row * tile_size
            tw = min(tile_size, w - x)
            th = min(tile_size, h - y)
            tile_img = img.crop((x, y, x + tw, y + th))
            buf = io.BytesIO()
            fmt = "PNG" if tile_img.mode in ("RGBA", "LA", "PA") else "JPEG"
            mime = "image/png" if fmt == "PNG" else "image/jpeg"
            if fmt == "JPEG" and tile_img.mode != "RGB":
                tile_img = tile_img.convert("RGB")
            tile_img.save(buf, fmt, quality=90)
            b64 = base64.b64encode(buf.getvalue()).decode()
            tiles.append({
                "base64": b64, "mime": mime, "col": col, "row": row,
                "total_cols": cols, "total_rows": rows,
                "width": tw, "height": th,
            })
    return tiles


class ImageResize:
    """Resize image to max_width (keeping aspect ratio), base64 encode."""

    name = "resize"
    media_types = ("image",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        max_width: int = kwargs.get("max_width", 1024)
        provider = _resolve_provider()

        try:
            from mm._mm import resize_image

            result = resize_image(str(path), max_width)
        except (ImportError, RuntimeError):
            result = _pillow_resize(path, max_width)

        part = _image_part(result["base64"], result["mime"], provider)
        yield _to_message([part])


class ImageTile:
    """Tile large image into squares, one Message per tile.

    Falls back to single-tile resize if image is smaller than tile_size.
    """

    name = "tile"
    media_types = ("image",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        tile_size: int = kwargs.get("tile_size", 1024)
        provider = _resolve_provider()

        try:
            from mm._mm import tile_image

            tiles = tile_image(str(path), tile_size)
        except (ImportError, RuntimeError):
            tiles = _pillow_tile(path, tile_size)

        for tile in tiles:
            part = _image_part(tile["base64"], tile["mime"], provider)
            yield _to_message([part])


# Register built-in strategies
register(ImageResize())
register(ImageTile())
