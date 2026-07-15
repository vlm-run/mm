"""document-url encoder: pass a whole document as a ``document_url`` part.

Emits a single OpenAI-compatible ``document_url`` content part carrying a
base64 ``data:`` URI of the source document (PDF or office file). The VLM Run
gateway routes such parts to a document model (OCR / VLM) that renders and
reads every page server-side — no client-side rasterization or per-page text
extraction required.

This is the low-level primitive; ``markdown`` builds on it to add a
model-parametrized OCR-to-markdown generate step (see ``markdown.py``).
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


def document_url_message(path: Path) -> Message:
    """Build a single-part user Message wrapping *path* as a ``document_url``.

    The part mirrors OpenAI's ``image_url`` shape::

        {"type": "document_url", "document_url": {"url": "data:application/pdf;base64,..."}}

    The whole file is base64-encoded once; page rendering and OCR happen on the
    server. Works on scanned/image-only PDFs that ``page-text`` cannot read.
    """
    mime = guess_mime(path.name, fallback="application/pdf")
    url = f"data:{mime};base64,{get_b64(path)}"
    logger.debug("document_url [path=%s, mime=%s]", path.name, mime)
    return {
        "role": "user",
        "content": [{"type": "document_url", "document_url": {"url": url}}],
    }


class DocumentUrl(Encoder):
    """Send a document to the LLM as a single ``document_url`` content part.

    Encode-only primitive: it does not pin a prompt or model, so it composes
    into custom pipeline YAMLs that supply their own ``generate`` block. For a
    ready-made OCR-to-markdown flow use the ``markdown`` encoder instead.
    """

    name = "document-url"
    kind = "document"

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        yield document_url_message(path)


register(DocumentUrl())
