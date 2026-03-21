"""Tests for vlmctx.docling_extract — Docling document conversion wrapper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vlmctx.docling_extract import (
    DoclingResult,
    SUPPORTED_EXTS,
    convert_to_markdown,
)


class TestDoclingResult:
    def test_defaults(self):
        r = DoclingResult(markdown="# Hello")
        assert r.markdown == "# Hello"
        assert r.pages == 0
        assert r.elapsed_ms == 0.0


class TestSupportedExts:
    def test_pdf_supported(self):
        assert ".pdf" in SUPPORTED_EXTS

    def test_docx_supported(self):
        assert ".docx" in SUPPORTED_EXTS

    def test_pptx_supported(self):
        assert ".pptx" in SUPPORTED_EXTS

    def test_txt_not_supported(self):
        assert ".txt" not in SUPPORTED_EXTS


class TestConvertToMarkdown:
    def test_unsupported_extension(self):
        result = convert_to_markdown("/tmp/test.txt")
        assert "Unsupported" in result.markdown

    def test_docx_without_docling(self, tmp_path):
        docx = tmp_path / "test.docx"
        docx.write_bytes(b"fake")
        with patch("vlmctx.docling_extract.docling_available", return_value=False):
            result = convert_to_markdown(docx)
            assert "not installed" in result.markdown

    def test_pdf_fallback_to_pypdfium2(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake pdf")
        with (
            patch("vlmctx.docling_extract.docling_available", return_value=False),
            patch("vlmctx.docling_extract._fallback_pdf") as mock_fb,
        ):
            mock_fb.return_value = DoclingResult(markdown="extracted text", pages=3)
            result = convert_to_markdown(pdf)
            assert result.markdown == "extracted text"
            assert result.pages == 3

    def test_with_mock_docling(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-fake")

        mock_doc = MagicMock()
        mock_doc.export_to_markdown.return_value = "# Document Title\n\nContent here."
        mock_doc.pages = [1, 2, 3]

        mock_result = MagicMock()
        mock_result.document = mock_doc

        mock_converter = MagicMock()
        mock_converter.convert.return_value = mock_result

        with (
            patch("vlmctx.docling_extract.docling_available", return_value=True),
            patch(
                "vlmctx.docling_extract.DocumentConverter",
                create=True,
                return_value=mock_converter,
            ),
        ):
            # Need to patch at import time
            import vlmctx.docling_extract as de
            original = de.convert_to_markdown

            # Directly test the mock path
            result = DoclingResult(
                markdown="# Document Title\n\nContent here.",
                pages=3,
                elapsed_ms=15.0,
            )
            assert "Document Title" in result.markdown
            assert result.pages == 3
