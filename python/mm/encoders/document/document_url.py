"""Gateway ``document_url`` passthrough encoder.

Sends the entire document file as a base64-encoded ``document_url`` part —
the native input shape accepted by the vlm.run gateway (and other
OpenAI-compatible backends with native PDF document input support). No
page extraction, rasterization, or text parsing: the raw file is sent
as-is for models with native document input support.

This is the gateway-focused counterpart to ``native`` (which uses the
OpenAI ``file`` part shape) and ``gemini-native`` (which uses Gemini's
``inline_data`` shape).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from mm.constants import guess_mime
from mm.encoders import register
from mm.encoders.base import Encoder, Message
from mm.encoders.image import _to_message
from mm.utils import get_b64

logger = logging.getLogger(__name__)


class DocumentUrl(Encoder):
    """Pass a document file directly as a gateway ``document_url`` part.

    Yields a single Message containing the entire document, base64-encoded
    as a ``data:`` URL inside a ``document_url`` part. Useful for gateway
    models with native document input support (e.g. PDF fan-out).
    """

    name = "document_url"
    kind = "document"

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        data = path.read_bytes()
        mime = guess_mime(path.name)
        size_mb = len(data) / (1024 * 1024)
        logger.debug("document_url [path=%s, size=%.1fMB]", path.name, size_mb)
        yield _to_message(
            [
                {
                    "type": "document_url",
                    "document_url": {
                        "url": f"data:{mime};base64,{get_b64(data)}",
                    },
                }
            ]
        )


register(DocumentUrl())
