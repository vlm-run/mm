"""Document encoding strategies: rasterize and rasterize+text.

Renders PDF pages as images using ``pypdfium2`` and encodes them as
OpenAI-compatible Message dicts.  The ``rasterize-text`` variant also
interleaves extracted page text alongside each page image.
"""

from __future__ import annotations

import base64
import io
import logging
from itertools import islice
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from mm.encoders import register, resolve_provider
from mm.encoders.base import Encoder, Message
from mm.encoders.image import _image_part, _to_message

logger = logging.getLogger(__name__)

_JPEG_QUALITY: int = 85


class DocumentRasterize(Encoder):
    """Render PDF pages as images and batch them into Messages.

    Each Message contains up to ``pages_per_message`` page images
    (default 4) with a text header indicating the page range.

    Kwargs:
        max_width: Render width in pixels (default 1024).
        pages_per_message: Pages per Message (default 4).
        max_pages: Total page cap (default unlimited).
        mode: fast | accurate.
        generate_model: --generate.model CLI flag.
    """

    name = "rasterize"
    kind = "document"

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        if kwargs.get("mode", "fast") == "fast":
            from mm.encoders.document.page_text import DocumentPageText

            yield from DocumentPageText().encode(path, **kwargs)
            return

        max_width: int = kwargs.get("max_width", 1024)
        pages_per_message: int = kwargs.get("pages_per_message", 4)
        max_pages: Optional[int] = kwargs.get("max_pages", None)
        generate_model = kwargs.get("generate_model", None)
        provider: str = resolve_provider(generate_model)

        page_iter = _rasterize_pages(path, max_width, max_pages)
        page_idx = 0
        any_pages = False

        while True:
            batch = list(islice(page_iter, pages_per_message))
            if not batch:
                break
            any_pages = True
            parts: list[dict[str, Any]] = [
                {
                    "type": "text",
                    "text": f"Document pages {page_idx + 1}-{page_idx + len(batch)} of {path.name}:",
                }
            ]
            for b64, mime in batch:
                parts.append(_image_part(b64, mime, provider))
            yield _to_message(parts)
            page_idx += len(batch)

        if not any_pages:
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": f"[No pages could be rasterized from {path.name}]",
                    }
                ]
            )


class DocumentRasterizeText(Encoder):
    """Render PDF pages as images *and* extract text, interleaved.

    Each Message contains page images with extracted text appended
    after each image.  Useful when the VLM benefits from OCR fallback.

    Kwargs:
        max_width: Render width in pixels (default 1024).
        pages_per_message: Pages per Message (default 4).
        max_pages: Total page cap (default unlimited).
        mode: fast | accurate.
        generate_model: --generate.model CLI flag.
    """

    name = "rasterize-text"
    kind = "document"

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        if kwargs.get("mode", "fast") == "fast":
            from mm.encoders.document.page_text import DocumentPageText

            yield from DocumentPageText().encode(path, **kwargs)
            return

        max_width: int = kwargs.get("max_width", 1024)
        pages_per_message: int = kwargs.get("pages_per_message", 4)
        max_pages: Optional[int] = kwargs.get("max_pages", None)
        generate_model = kwargs.get("generate_model", None)
        provider: str = resolve_provider(generate_model)

        page_texts: list[str] = _extract_page_texts(path, max_pages)
        page_iter = _rasterize_pages(path, max_width, max_pages)
        page_idx = 0
        any_pages = False

        while True:
            batch_imgs = list(islice(page_iter, pages_per_message))
            if not batch_imgs:
                break
            any_pages = True
            batch_texts = page_texts[page_idx : page_idx + len(batch_imgs)] if page_texts else []
            parts: list[dict[str, Any]] = [
                {
                    "type": "text",
                    "text": f"Document pages {page_idx + 1}-{page_idx + len(batch_imgs)} of {path.name}:",
                }
            ]
            for j, (b64, mime) in enumerate(batch_imgs):
                parts.append(_image_part(b64, mime, provider))
                if j < len(batch_texts) and batch_texts[j].strip():
                    parts.append(
                        {
                            "type": "text",
                            "text": f"[Page {page_idx + j + 1} text]: {batch_texts[j].strip()}",
                        }
                    )
            yield _to_message(parts)
            page_idx += len(batch_imgs)

        if not any_pages:
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": f"[No pages could be rasterized from {path.name}]",
                    }
                ]
            )


def _rasterize_pages(
    path: Path,
    max_width: int,
    max_pages: Optional[int],
) -> Iterator[tuple[str, str]]:
    """Yield PDF pages as ``(base64, mime)`` tuples one at a time.

    Uses ``pypdfium2`` for rendering. Each page is scaled so that its
    width matches *max_width* while preserving aspect ratio, then JPEG-
    encoded at quality 85. Pages are yielded lazily so that only one
    rendered page is held in memory at a time.

    Args:
        path: Path to the PDF file.
        max_width: Target render width in pixels.
        max_pages: Maximum number of pages to render, or ``None``.

    Yields:
        ``(base64_str, mime_str)`` pairs, one per page.
    """
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        total: int = len(pdf)
        if max_pages is not None:
            total = min(total, max_pages)

        logger.debug(
            "rasterize_pages [path=%s, pages=%d, max_width=%d]",
            path.name,
            total,
            max_width,
        )

        for i in range(total):
            page = pdf[i]
            try:
                page_width: float = page.get_width()
                scale: float = max_width / page_width if page_width > 0 else 1.0
                bitmap = page.render(scale=scale)
                pil_img = bitmap.to_pil()
                buf = io.BytesIO()
                pil_img.save(buf, "JPEG", quality=_JPEG_QUALITY, subsampling=0)
                b64: str = base64.b64encode(buf.getvalue()).decode()
                yield (b64, "image/jpeg")
            finally:
                page.close()
    finally:
        pdf.close()


def _extract_page_texts(path: Path, max_pages: Optional[int]) -> list[str]:
    """Extract text from each page of a PDF.

    Args:
        path: Path to the PDF file.
        max_pages: Maximum number of pages to extract, or ``None``.

    Returns:
        List of text strings, one per page.
        Returns an empty list if ``pypdfium2`` is not installed.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return []

    pdf = pdfium.PdfDocument(str(path))
    try:
        total: int = len(pdf)
        if max_pages is not None:
            total = min(total, max_pages)

        texts: list[str] = []
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
