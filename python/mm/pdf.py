"""PDF page mosaic extraction via pypdfium2.

Renders selected pages as thumbnails and tiles them into mosaic grids,
reusing the same visual format as video keyframe mosaics.
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PdfMosaicResult:
    """Result of PDF mosaic extraction."""

    mosaic_paths: list[Path]
    page_count: int
    rendered_pages: int
    tile_cols: int
    tile_rows: int
    thumb_width: int
    elapsed_ms: float = 0.0
    text_preview: str = ""


def pypdfium2_available() -> bool:
    try:
        import pypdfium2  # noqa: F401

        return True
    except ImportError:
        return False


def extract_pdf_mosaics(
    pdf_path: str | Path,
    *,
    out_dir: str | Path | None = None,
    tile_cols: int = 4,
    tile_rows: int = 4,
    thumb_width: int = 200,
    max_pages: int | None = None,
    quality: int = 85,
) -> PdfMosaicResult:
    """Render PDF pages as thumbnails and tile into mosaic grids.

    Uses pypdfium2 for fast rendering (~10-30ms/page).
    16 pages per mosaic at 200px width by default.
    """
    import pypdfium2 as pdfium

    t0 = time.monotonic()
    pdf_path = Path(pdf_path)

    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="mm_pdf_"))
    else:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

    doc = pdfium.PdfDocument(str(pdf_path))
    total_pages = len(doc)

    if total_pages == 0:
        doc.close()
        return PdfMosaicResult(
            mosaic_paths=[],
            page_count=0,
            rendered_pages=0,
            tile_cols=tile_cols,
            tile_rows=tile_rows,
            thumb_width=thumb_width,
        )

    pages_per_mosaic = tile_cols * tile_rows
    limit = max_pages if max_pages else total_pages
    page_indices = list(range(min(limit, total_pages)))

    if len(page_indices) > pages_per_mosaic * 8:
        step = len(page_indices) / (pages_per_mosaic * 8)
        page_indices = [int(i * step) for i in range(pages_per_mosaic * 8)]

    from PIL import Image

    thumbnails: list[Image.Image] = []

    for idx in page_indices:
        page = doc[idx]
        pw, ph = page.get_size()
        scale = thumb_width / pw if pw > 0 else 1.0
        bitmap = page.render(scale=scale)
        pil_img = bitmap.to_pil()
        thumbnails.append(pil_img)

    doc.close()

    if not thumbnails:
        return PdfMosaicResult(
            mosaic_paths=[],
            page_count=total_pages,
            rendered_pages=0,
            tile_cols=tile_cols,
            tile_rows=tile_rows,
            thumb_width=thumb_width,
        )

    max_h = max(img.height for img in thumbnails)
    mosaic_paths: list[Path] = []
    stem = pdf_path.stem

    for mosaic_idx in range(0, len(thumbnails), pages_per_mosaic):
        batch = thumbnails[mosaic_idx : mosaic_idx + pages_per_mosaic]
        rows_needed = (len(batch) + tile_cols - 1) // tile_cols
        actual_rows = min(rows_needed, tile_rows)

        mosaic_w = thumb_width * tile_cols
        mosaic_h = max_h * actual_rows
        mosaic = Image.new("RGB", (mosaic_w, mosaic_h), (255, 255, 255))

        for i, thumb in enumerate(batch):
            col = i % tile_cols
            row = i // tile_cols
            if row >= actual_rows:
                break
            x = col * thumb_width
            y = row * max_h
            mosaic.paste(thumb, (x, y))

        out_path = out_dir / f"{stem}_pages_{mosaic_idx // pages_per_mosaic}.jpg"
        mosaic.save(str(out_path), "JPEG", quality=quality)
        mosaic_paths.append(out_path)

    elapsed = (time.monotonic() - t0) * 1000

    return PdfMosaicResult(
        mosaic_paths=mosaic_paths,
        page_count=total_pages,
        rendered_pages=len(thumbnails),
        tile_cols=tile_cols,
        tile_rows=tile_rows,
        thumb_width=thumb_width,
        elapsed_ms=elapsed,
    )


def extract_pdf_text(pdf_path: str | Path, *, max_pages: int | None = None) -> str:
    """Extract text from a PDF using pypdfium2."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf_path))
    total = len(doc)
    limit = max_pages if max_pages else total
    pages = min(limit, total)

    parts: list[str] = []
    for i in range(pages):
        page = doc[i]
        textpage = page.get_textpage()
        text = textpage.get_text_range()
        if text.strip():
            parts.append(text)
        textpage.close()
        page.close()

    doc.close()
    return "\n\n".join(parts)
