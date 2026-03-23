"""Docling wrapper for document-to-markdown conversion.

Converts PDF, DOCX, and PPTX files to clean markdown using the
docling library. Falls back to pypdfium2 for PDFs when docling
is not installed.

Install: pip install vlmctx[extract]
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DoclingResult:
    """Result of document conversion."""

    markdown: str
    pages: int = 0
    elapsed_ms: float = 0.0


SUPPORTED_EXTS = frozenset((".pdf", ".docx", ".pptx"))


def docling_available() -> bool:
    """Check if docling is installed."""
    try:
        import docling  # noqa: F401
        return True
    except ImportError:
        return False


def convert_to_markdown(doc_path: str | Path) -> DoclingResult:
    """Convert a document to markdown via docling.

    Args:
        doc_path: Path to PDF, DOCX, or PPTX file.

    Returns:
        DoclingResult with markdown text, page count, and timing.
    """
    doc_path = Path(doc_path)
    ext = doc_path.suffix.lower()

    if ext not in SUPPORTED_EXTS:
        return DoclingResult(
            markdown=f"[Unsupported document type: {ext}]",
        )

    if not docling_available():
        # Fall back to pypdfium2 for PDFs
        if ext == ".pdf":
            return _fallback_pdf(doc_path)
        return DoclingResult(
            markdown=f"[docling not installed — pip install vlmctx[extract] for {ext} support]",
        )

    t0 = time.monotonic()

    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(str(doc_path))
    markdown = result.document.export_to_markdown()

    # Estimate page count from the result
    pages = 0
    if hasattr(result.document, "pages") and result.document.pages:
        pages = len(result.document.pages)

    elapsed = (time.monotonic() - t0) * 1000

    return DoclingResult(
        markdown=markdown,
        pages=pages,
        elapsed_ms=round(elapsed, 1),
    )


def _fallback_pdf(path: Path) -> DoclingResult:
    """Fall back to pypdfium2 for PDF text extraction."""
    t0 = time.monotonic()
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        pages_text: list[str] = []
        for i in range(len(pdf)):
            page = pdf[i]
            textpage = page.get_textpage()
            pages_text.append(textpage.get_text_range())
            textpage.close()
            page.close()
        num_pages = len(pdf)
        pdf.close()

        text = "\n\n".join(pages_text).strip()
        elapsed = (time.monotonic() - t0) * 1000

        if not text:
            return DoclingResult(
                markdown="[No extractable text — scanned/image-only PDF]",
                pages=num_pages,
                elapsed_ms=round(elapsed, 1),
            )
        return DoclingResult(
            markdown=text,
            pages=num_pages,
            elapsed_ms=round(elapsed, 1),
        )
    except Exception as e:
        return DoclingResult(markdown=f"[PDF extraction failed: {e}]")
