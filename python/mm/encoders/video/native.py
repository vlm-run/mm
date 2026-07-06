"""Native base64 video passthrough encoder.

Sends the entire video file as a base64-encoded ``video_url`` part — the
OpenAI-compatible counterpart to the Gemini ``inline_data`` passthrough
(``gemini-native``). No frame extraction, probing, or chunking: the raw
file is sent as-is for models with native video input support.
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


class NativeVideo(Encoder):
    """Pass a video file directly as a base64 ``video_url`` part.

    The OpenAI-compatible counterpart to ``gemini-native``: yields a single
    Message containing the entire video, base64-encoded as a ``data:`` URL.
    Useful for models with native video input support.
    """

    name = "native"
    kind = "video"

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        data = path.read_bytes()
        mime = guess_mime(path.name)
        size_mb = len(data) / (1024 * 1024)
        logger.debug("native_video [path=%s, size=%.1fMB]", path.name, size_mb)
        yield _to_message(
            [
                {
                    "type": "video_url",
                    "video_url": {"url": f"data:{mime};base64,{get_b64(data)}"},
                }
            ]
        )


register(NativeVideo())
