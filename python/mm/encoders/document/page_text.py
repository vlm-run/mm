"""Document page-text encoder: structured text extraction per page.

Extracts text from PDF pages via pypdfium2 (or DOCX/PPTX via
python-docx/python-pptx) and yields it as structured text messages.
No rasterization — much lighter than ``rasterize`` or ``rasterize-text``.

This is the default document encoder for fast mode.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable, Optional

from mm.encoders import Message, register

logger = logging.getLogger(__name__)


def _to_message(parts: list[dict[str, Any]]) -> Message:
    return {"role": "user", "content": parts}


class DocumentPageText:
    """Extract text per page from PDF/DOCX/PPTX, yield as text messages.

    For PDFs, uses pypdfium2 to extract text page by page, batching
    ``pages_per_message`` pages into each Message.  For DOCX/PPTX,
    uses python-docx/python-pptx and yields the full text.

    Kwargs:
        pages_per_message: Pages per Message for PDFs (default 4).
        max_pages: Maximum pages to extract (default unlimited).
    """

    name: str = "page-text"
    media_types: tuple[str, ...] = ("document",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        pages_per_message: int = kwargs.get("pages_per_message", 128)
        max_pages: Optional[int] = kwargs.get("max_pages", None)

        ext = path.suffix.lower()

        if ext == ".pdf":
            yield from self._encode_pdf(path, pages_per_message, max_pages)
        elif ext == ".docx":
            yield from self._encode_docx(path)
        elif ext == ".pptx":
            yield from self._encode_pptx(path)
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
        try:
            import pypdfium2 as pdfium
        except ImportError:
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": "[pypdfium2 not installed — pip install pypdfium2]",
                    }
                ]
            )
            return

        pdf = pdfium.PdfDocument(str(path))
        try:
            total = len(pdf)
            if max_pages is not None:
                total = min(total, max_pages)

            if total == 0:
                yield _to_message(
                    [
                        {
                            "type": "text",
                            "text": f"[No pages in {path.name}]",
                        }
                    ]
                )
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

    def _encode_docx(self, path: Path) -> Iterable[Message]:
        try:
            from mm.docs_extract import extract_docx

            text = extract_docx(str(path))
        except ImportError:
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": "[python-docx not installed — pip install python-docx]",
                    }
                ]
            )
            return
        except Exception as e:
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": f"[DOCX extraction failed for {path.name}: {e}]",
                    }
                ]
            )
            return

        yield _to_message(
            [
                {
                    "type": "text",
                    "text": f"Document {path.name}:\n\n{text}",
                }
            ]
        )

    def _encode_pptx(self, path: Path) -> Iterable[Message]:
        try:
            from mm.docs_extract import extract_pptx

            text = extract_pptx(str(path))
        except ImportError:
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": "[python-pptx not installed — pip install python-pptx]",
                    }
                ]
            )
            return
        except Exception as e:
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": f"[PPTX extraction failed for {path.name}: {e}]",
                    }
                ]
            )
            return

        yield _to_message(
            [
                {
                    "type": "text",
                    "text": f"Document {path.name}:\n\n{text}",
                }
            ]
        )


register(DocumentPageText())
