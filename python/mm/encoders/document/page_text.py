"""document-page-text encoder: structured text extraction per page.

Extracts text from PDF pages via pypdfium2, and from office documents
(docx/odt/pptx/odp/xlsx/ods) via the libreoffice-pure-backed
``mm._mm.office_content`` surface. Yields structured text messages.
No rasterization — much lighter than ``rasterize`` or ``rasterize-text``.

This is the default document encoder for fast mode.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable, Optional

from mm.constants import OFFICE_EXTS
from mm.encoders import Message, register
from mm.pipelines.schema import Generate

logger = logging.getLogger(__name__)


def _to_message(parts: list[dict[str, Any]]) -> Message:
    return {"role": "user", "content": parts}


class DocumentPageText:
    """Extract text from PDF / office docs, yield as text messages.

    For PDFs, uses pypdfium2 to extract text page by page, batching
    ``pages_per_message`` pages into each Message. For office docs
    (docx/odt/pptx/odp/xlsx/ods), uses the libreoffice-pure–backed
    ``office_content`` and yields the full text in one Message.

    Kwargs:
        pages_per_message: Pages per Message for PDFs (default 4).
        max_pages: Maximum pages to extract (default unlimited).
    """

    name: str = "document-page-text"
    media_types: tuple[str, ...] = ("document",)
    fast: Generate | None = None
    accurate: Generate | None = None

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        if kwargs.get("generate_overrides", None):
            from mm.display import console

            console.print(
                "[yellow]warning: --generate.* flags ignored (encoder is passthrough)[/yellow]"
            )

        pages_per_message: int = kwargs.get("pages_per_message", 128)
        max_pages: Optional[int] = kwargs.get("max_pages", None)
        ext = path.suffix.lower()

        if ext == ".pdf":
            yield from self._encode_pdf(path, pages_per_message, max_pages)
        elif ext in OFFICE_EXTS:
            yield from self._encode_office(path)
        else:
            try:
                text = path.read_text(errors="replace")
                yield _to_message(
                    [
                        {
                            "type": "text",
                            "text": f"Document {path.name}:\n\n{text}",
                        }
                    ]
                )
            except Exception as e:
                yield _to_message(
                    [
                        {
                            "type": "text",
                            "text": f"[Failed to read {path.name}: {e}]",
                        }
                    ]
                )

    def _encode_pdf(
        self,
        path: Path,
        pages_per_message: int,
        max_pages: Optional[int],
    ) -> Iterable[Message]:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        try:
            total = len(pdf)
            if max_pages is not None:
                total = min(total, max_pages)

            if total == 0:
                yield _to_message([{"type": "text", "text": f"[No pages in {path.name}]"}])
                return

            logger.debug("page_text [path=%s, pages=%d]", path.name, total)

            for i in range(0, total, pages_per_message):
                batch_end = min(i + pages_per_message, total)
                page_texts: list[str] = []

                for j in range(i, batch_end):
                    page = pdf[j]
                    try:
                        textpage = page.get_textpage()
                        try:
                            text = textpage.get_text_range().strip()
                            page_texts.append(
                                f"--- Page {j + 1} ---\n{text}"
                                if text
                                else f"--- Page {j + 1} ---\n[No extractable text]"
                            )
                        finally:
                            textpage.close()
                    finally:
                        page.close()

                yield _to_message(
                    [
                        {
                            "type": "text",
                            "text": (
                                f"{path.name} — pages {i + 1}-{batch_end} of {total}:\n\n"
                                + "\n\n".join(page_texts)
                            ),
                        }
                    ]
                )
        finally:
            pdf.close()

    def _encode_office(self, path: Path) -> Iterable[Message]:
        try:
            from mm._mm import office_content

            text = office_content(str(path))
        except Exception as e:
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": f"[Office Doc extraction failed for {path.name}: {e}]",
                    }
                ]
            )
            return

        yield _to_message([{"type": "text", "text": f"Document {path.name}:\n\n{text}"}])


register(DocumentPageText())
