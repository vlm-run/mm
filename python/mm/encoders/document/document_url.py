"""document-url encoder: pass a whole document as a ``document_url`` part.

Emits a single OpenAI-compatible ``document_url`` content part carrying a
base64 ``data:`` URI of the source document (PDF or office file). The VLM Run
gateway routes such parts to a document-OCR model (e.g. ``glm-ocr``) that
renders and reads every page server-side — no client-side rasterization or
per-page text extraction required.

This is the default accurate-mode document encoder. Paired with the
``glm-ocr`` model pinned in ``pipelines/document/accurate.yaml``, it turns
``mm cat paper.pdf -m accurate`` into a single gateway OCR call that returns
clean markdown.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from mm.constants import guess_mime
from mm.encoders import register
from mm.encoders.base import Encoder, Message
from mm.utils import get_b64

logger = logging.getLogger(__name__)


class DocumentUrl(Encoder):
    """Send a document to the LLM as a single ``document_url`` content part.

    The part mirrors OpenAI's ``image_url`` shape::

        {"type": "document_url", "document_url": {"url": "data:application/pdf;base64,..."}}

    The whole file is base64-encoded once; page rendering and OCR happen on the
    server (VLM Run gateway with ``glm-ocr``). Unlike ``page-text`` (local
    pypdfium2 extraction) this works on scanned/image-only PDFs.
    """

    name = "document-url"
    kind = "document"

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        mime = guess_mime(path.name, fallback="application/pdf")
        url = f"data:{mime};base64,{get_b64(path)}"
        logger.debug("document_url [path=%s, mime=%s]", path.name, mime)
        yield {
            "role": "user",
            "content": [{"type": "document_url", "document_url": {"url": url}}],
        }


register(DocumentUrl())
