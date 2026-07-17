"""Document encoding strategies: ``native``.

Sends the entire document file as a base64-encoded ``file`` part — the
OpenAI-compatible counterpart to the Gemini ``inline_data`` (``gemini-native``).
No page extraction, rasterization, or text parsing: the raw file is sent as-is
for models with native document input support.
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


class DocumentNative(Encoder):
    """Pass a document file directly as a base64 ``file`` part.

    The OpenAI-compatible counterpart to ``gemini-native``: yields a single
    Message containing the entire document, base64-encoded as a ``data:`` URL.
    Useful for models with native document input support (e.g. PDF).
    """

    name = "native"
    kind = "document"

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        data = path.read_bytes()
        mime = guess_mime(path.name)
        size_mb = len(data) / (1024 * 1024)
        logger.debug("native_document [path=%s, size=%.1fMB]", path.name, size_mb)
        yield _to_message(
            [
                {
                    "type": "file",
                    "file": {
                        "filename": path.name,
                        "file_data": f"data:{mime};base64,{get_b64(data)}",
                    },
                }
            ]
        )


register(DocumentNative())
