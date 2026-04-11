"""Document encoding strategies: rasterize and rasterize+text."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any, Iterable

from mm.serde import Message, _resolve_provider, register
from mm.serde.image import _image_part, _to_message


class DocumentRasterize:
    """Render PDF pages as images at max_width, group into Messages.

    Each Message contains a batch of page images (default 4 pages per Message).
    """

    name = "rasterize"
    media_types = ("document",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        max_width: int = kwargs.get("max_width", 1024)
        pages_per_message: int = kwargs.get("pages_per_message", 4)
        max_pages: int | None = kwargs.get("max_pages", None)
        provider = _resolve_provider()

        page_images = _rasterize_pages(path, max_width, max_pages)
        if not page_images:
            yield _to_message([{
                "type": "text",
                "text": f"[No pages could be rasterized from {path.name}]",
            }])
            return

        # Batch pages into messages
        for i in range(0, len(page_images), pages_per_message):
            batch = page_images[i : i + pages_per_message]
            parts: list[dict[str, Any]] = []
            parts.append({
                "type": "text",
                "text": f"Document pages {i + 1}-{i + len(batch)} of {path.name}:",
            })
            for b64, mime in batch:
                parts.append(_image_part(b64, mime, provider))
            yield _to_message(parts)


class DocumentRasterizeText:
    """Render PDF pages as images AND extract text, interleaved.

    Each Message contains page images and the corresponding extracted text.
    """

    name = "rasterize-text"
    media_types = ("document",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        max_width: int = kwargs.get("max_width", 1024)
        pages_per_message: int = kwargs.get("pages_per_message", 4)
        max_pages: int | None = kwargs.get("max_pages", None)
        provider = _resolve_provider()

        page_images = _rasterize_pages(path, max_width, max_pages)
        page_texts = _extract_page_texts(path, max_pages)

        if not page_images:
            yield _to_message([{
                "type": "text",
                "text": f"[No pages could be rasterized from {path.name}]",
            }])
            return

        for i in range(0, len(page_images), pages_per_message):
            batch_imgs = page_images[i : i + pages_per_message]
            batch_texts = page_texts[i : i + pages_per_message] if page_texts else []
            parts: list[dict[str, Any]] = []
            parts.append({
                "type": "text",
                "text": f"Document pages {i + 1}-{i + len(batch_imgs)} of {path.name}:",
            })
            for j, (b64, mime) in enumerate(batch_imgs):
                parts.append(_image_part(b64, mime, provider))
                if j < len(batch_texts) and batch_texts[j].strip():
                    parts.append({
                        "type": "text",
                        "text": f"[Page {i + j + 1} text]: {batch_texts[j].strip()}",
                    })
            yield _to_message(parts)


def _rasterize_pages(
    path: Path, max_width: int, max_pages: int | None
) -> list[tuple[str, str]]:
    """Rasterize PDF pages to ``(base64, mime)`` tuples.

    Args:
        path: Path to PDF file.
        max_width: Target render width in pixels.
        max_pages: Maximum number of pages to render.

    Returns:
        List of ``(base64_str, mime_str)`` pairs, one per page.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return []

    pdf = pdfium.PdfDocument(str(path))
    try:
        total = len(pdf)
        if max_pages is not None:
            total = min(total, max_pages)

        results = []
        for i in range(total):
            page = pdf[i]
            try:
                page_width = page.get_width()
                scale = max_width / page_width if page_width > 0 else 1.0
                bitmap = page.render(scale=scale)
                pil_img = bitmap.to_pil()
                buf = io.BytesIO()
                pil_img.save(buf, "JPEG", quality=85)
                b64 = base64.b64encode(buf.getvalue()).decode()
                results.append((b64, "image/jpeg"))
            finally:
                page.close()
    finally:
        pdf.close()
    return results


def _extract_page_texts(path: Path, max_pages: int | None) -> list[str]:
    """Extract text from each page of a PDF.

    Args:
        path: Path to PDF file.
        max_pages: Maximum number of pages to extract.

    Returns:
        List of text strings, one per page.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return []

    pdf = pdfium.PdfDocument(str(path))
    try:
        total = len(pdf)
        if max_pages is not None:
            total = min(total, max_pages)

        texts = []
        for i in range(total):
            page = pdf[i]
            try:
                textpage = page.get_textpage()
                try:
                    texts.append(textpage.get_text_range())
                finally:
                    textpage.close()
            finally:
                page.close()
    finally:
        pdf.close()
    return texts


register(DocumentRasterize())
register(DocumentRasterizeText())
