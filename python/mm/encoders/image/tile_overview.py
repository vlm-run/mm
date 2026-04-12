"""Tile + overview image strategy.

Combines a resized overview of the full image with individual
max_width x max_width tile crops, all in a single Message.
This gives VLMs both global context and fine detail that naive
resize alone would lose.

Example: a 4096x4096 image with max_width=1024 produces
1 overview + 16 tiles = 17 image parts in one Message.

Pure Pillow — no extra dependencies beyond what mm already requires.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from mm.encoders import Message, _resolve_provider, register
from mm.encoders.image import (
    _encode_pil_image,
    _image_part,
    _open_image_with_exif,
    _to_message,
)

logger = logging.getLogger(__name__)


class TileOverview:
    """Resize the full image + tile it, yielding everything in one Message.

    The Message contains:
      1. A text header describing the layout.
      2. The full image resized to ``max_width`` (overview).
      3. Each ``max_width x max_width`` tile crop from the original.

    If the image already fits within a single tile, only the resized
    overview is returned (no redundant duplicate).

    Kwargs:
        max_width: Pixel size for both tile dimension and overview
            bounding box (default 1024).
    """

    name: str = "tile-overview"
    media_types: tuple[str, ...] = ("image",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        max_width: int = kwargs.get("max_width", 1024)
        provider: str = _resolve_provider()

        img = _open_image_with_exif(path)
        w, h = img.size

        from PIL import Image as PILImage

        # --- overview: fit full image into max_width bounding box ---
        if w > max_width or h > max_width:
            scale = min(max_width / w, max_width / h)
            overview = img.resize(
                (round(w * scale), round(h * scale)),
                PILImage.Resampling.LANCZOS,
            )
        else:
            overview = img

        overview_b64, overview_mime = _encode_pil_image(overview, path)

        # --- tiles: crop into max_width x max_width blocks ---
        cols = (w + max_width - 1) // max_width
        rows = (h + max_width - 1) // max_width
        single_tile = cols == 1 and rows == 1

        if single_tile:
            parts: list[dict[str, Any]] = [
                _image_part(overview_b64, overview_mime, provider),
            ]
            logger.debug(
                "tile_overview [path=%s, %dx%d, fits in one tile]",
                path.name, w, h,
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
            "tile_overview [path=%s, %dx%d, grid=%dx%d, parts=%d]",
            path.name, w, h, cols, rows, len(parts),
        )
        yield _to_message(parts)


register(TileOverview())
