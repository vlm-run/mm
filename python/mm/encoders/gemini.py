"""Gemini passthrough strategies for native multimodal input.

Encodes video and document files as Gemini ``inline_data`` Part dicts,
suitable for the Google Generative AI API.  Supports both single-shot
passthrough and duration-based chunking for long videos.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any, Iterable

from mm.constants import guess_mime
from mm.encoders import Message, register

logger = logging.getLogger(__name__)


def _gemini_inline_data_part(data: bytes, mime: str) -> dict[str, Any]:
    """Construct a Gemini ``inline_data`` Part dict.

    Args:
        data: Raw file bytes to encode.
        mime: MIME type string (e.g. ``"video/mp4"``).

    Returns:
        Dict matching the ``google.genai.types.Part`` schema.
    """
    b64: str = base64.b64encode(data).decode()
    return {"inline_data": {"mime_type": mime, "data": b64}}


def _to_gemini_message(parts: list[dict[str, Any]]) -> Message:
    """Wrap content parts in a Message dict."""
    return {"role": "user", "content": parts}


class GeminiVideo:
    """Pass a video file directly as a Gemini ``inline_data`` Part.

    Uses the Rust fast-path (``mm._mm.gemini_video_parts``) when
    available, falling back to a pure-Python base64 encoding.

    Yields a single Message containing the entire video.
    """

    name: str = "gemini-video"
    media_types: tuple[str, ...] = ("video",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        try:
            from mm._mm import gemini_video_parts

            json_strs: list[str] = gemini_video_parts(str(path))
            parts: list[dict[str, Any]] = [json.loads(s) for s in json_strs]
        except (ImportError, RuntimeError):
            data: bytes = path.read_bytes()
            mime: str = guess_mime(path.name)
            parts = [_gemini_inline_data_part(data, mime)]

        logger.debug("gemini_video [path=%s, parts=%d]", path.name, len(parts))
        yield _to_gemini_message(parts)


class GeminiVideoChunked:
    """Chunk a video by duration and yield one Gemini Part per chunk.

    Uses ``ffmpeg`` to extract time-based segments.  For videos shorter
    than ``max_seconds`` the entire file is sent as a single Part.

    Kwargs:
        max_seconds: Maximum chunk length in seconds (default 120).
        overlap: Overlap between chunks in seconds (default 10).
    """

    name: str = "gemini-video-chunked"
    media_types: tuple[str, ...] = ("video",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        max_seconds: int = kwargs.get("max_seconds", 120)
        overlap: int = kwargs.get("overlap", 10)

        from mm.ffmpeg import extract_segment, ffmpeg_available, probe_duration

        if not ffmpeg_available():
            yield _to_gemini_message([{
                "type": "text",
                "text": f"[ffmpeg not available for {path.name}]",
            }])
            return

        duration: float = probe_duration(path)
        if duration <= max_seconds:
            data: bytes = path.read_bytes()
            mime: str = guess_mime(path.name)
            yield _to_gemini_message([_gemini_inline_data_part(data, mime)])
            return

        import tempfile

        step: int = max(max_seconds - overlap, 1)
        start: float = 0.0
        chunk_idx: int = 0

        logger.debug(
            "gemini_video_chunked [path=%s, duration=%.1fs, chunk=%ds]",
            path.name, duration, max_seconds,
        )

        while start < duration:
            end: float = min(start + max_seconds, duration)
            with tempfile.NamedTemporaryFile(suffix=path.suffix, delete=False) as tmp:
                seg_path = Path(tmp.name)
            try:
                extract_segment(str(path), str(seg_path), start, end)
                data = seg_path.read_bytes()
            finally:
                seg_path.unlink(missing_ok=True)
            mime = guess_mime(path.name)
            yield _to_gemini_message([_gemini_inline_data_part(data, mime)])
            start += step
            chunk_idx += 1


class GeminiDocument:
    """Pass a document file directly as a Gemini ``inline_data`` Part.

    Uses the Rust fast-path when available.  Yields a single Message.
    """

    name: str = "gemini-doc"
    media_types: tuple[str, ...] = ("document",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        try:
            from mm._mm import gemini_document_part

            json_str: str = gemini_document_part(str(path))
            part: dict[str, Any] = json.loads(json_str)
        except (ImportError, RuntimeError):
            data: bytes = path.read_bytes()
            mime: str = guess_mime(path.name)
            part = _gemini_inline_data_part(data, mime)

        logger.debug("gemini_doc [path=%s]", path.name)
        yield _to_gemini_message([part])


register(GeminiVideo())
register(GeminiVideoChunked())
register(GeminiDocument())
