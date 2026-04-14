"""Docling wrapper for document-to-markdown conversion.

Converts PDF, DOCX, and PPTX files to clean markdown using the
docling library. Falls back to pypdfium2 for PDFs when docling
is not installed.

Install: pip install mm[extract]
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from mm.constants import DOCUMENT_EXTS as SUPPORTED_EXTS


@contextlib.contextmanager
def _suppress_stderr():
    """Suppress both Python-level and C-level stderr output."""
    real_stderr = sys.stderr
    stderr_fd = os.dup(2)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull_fd, 2)
    os.close(devnull_fd)
    sys.stderr = io.StringIO()
    try:
        yield
    finally:
        os.dup2(stderr_fd, 2)
        os.close(stderr_fd)
        sys.stderr = real_stderr


@dataclass
class DoclingResult:
    """Result of document conversion."""

    markdown: str
    pages: int = 0
    elapsed_ms: float = 0.0


def docling_available() -> bool:
    """Check if docling is installed and its dependencies are functional."""
    try:
        with _suppress_stderr():
            from docling.document_converter import DocumentConverter  # noqa: F401

        return True
    except Exception:
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
            markdown=f"[docling not installed — pip install mm[extract] for {ext} support]",
        )

    t0 = time.monotonic()

    with _suppress_stderr():
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
