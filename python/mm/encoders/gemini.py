"""Gemini passthrough strategies for native multimodal input.

Encodes video and document files as Gemini ``inline_data`` Part dicts,
suitable for Gemini API. Supports both single-shot passthrough and
duration-based chunking for long videos.
"""

from __future__ import annotations

import base64
import json
import logging
from concurrent.futures import ThreadPoolExecutor
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
    return {
        "inline_data": {
            "mime_type": mime,
            "data": base64.b64encode(data).decode(),
        }
    }


def _to_gemini_message(parts: list[dict[str, Any]]) -> Message:
    """Wrap content parts in a Message dict."""
    return {"role": "user", "content": parts}


class GeminiVideo:
    """Pass a video file directly as a Gemini ``inline_data`` Part.

    Uses the Rust fast-path (``mm._mm.gemini_video_parts``) when
    available, falling back to a pure-Python base64 encoding.

    Yields a single Message containing the entire video.
    """

    name: str = "video-gemini"
    media_types: tuple[str, ...] = ("video",)

    def encode(self, path: Path, **kwargs) -> Iterable[Message]:
        try:
            from mm._mm import gemini_video_parts

            json_strs = gemini_video_parts(str(path))
            parts: list[dict[str, Any]] = [json.loads(s) for s in json_strs]
        except (ImportError, RuntimeError):
            data = path.read_bytes()
            mime = guess_mime(path.name)
            parts = [_gemini_inline_data_part(data, mime)]

        logger.debug("gemini_video [path=%s, parts=%d]", path.name, len(parts))
        yield _to_gemini_message(parts)


class GeminiVideoChunked:
    """Chunk a video by duration and yield one Gemini Part per chunk.

    Uses ``ffmpeg`` to extract time-based segments. For videos shorter
    than ``max_seconds`` the entire file is sent as a single Part.

    Kwargs:
        max_seconds: Maximum chunk length in seconds (default 120).
        overlap: Overlap between chunks in seconds (default 10).
    """

    name: str = "video-gemini-chunked"
    media_types: tuple[str, ...] = ("video",)

    def encode(self, path: Path, **kwargs) -> Iterable[Message]:
        max_seconds: int = int(kwargs.get("max_seconds", 120))
        overlap: int = int(kwargs.get("overlap", 10))

        from mm.video import extract_segment, probe, pyav_runnable

        if not pyav_runnable():
            yield _to_gemini_message(
                [
                    {
                        "type": "text",
                        "text": f"[PyAV not runnable for {path.name}]",
                    }
                ]
            )
            return

        info = probe(path)
        if info.duration <= max_seconds:
            data = path.read_bytes()
            mime = guess_mime(path.name)
            yield _to_gemini_message([_gemini_inline_data_part(data, mime)])
            return

        import tempfile

        mime = guess_mime(path.name)
        step: float = max(max_seconds - overlap, 1)
        segments: list[tuple[float, float]] = []
        start: float = 0.0
        while start < info.duration:
            end = min(start + max_seconds, info.duration)
            segments.append((start, end))
            start += step

        logger.debug(
            "gemini_video_chunked [path=%s, duration=%.1fs, chunk=%ds, segment_len=%ds]",
            path.name,
            info.duration,
            max_seconds,
            len(segments),
        )

        def _process(varg: tuple[float, float]):
            start, end = varg
            with tempfile.NamedTemporaryFile(suffix=path.suffix, delete=False) as tmp:
                seg_path = Path(tmp.name)
            try:
                extract_segment(path, seg_path, start, end)
                data = seg_path.read_bytes()
            finally:
                seg_path.unlink(missing_ok=True)
            return _to_gemini_message([_gemini_inline_data_part(data, mime)])

        with ThreadPoolExecutor(max_workers=min(4, len(segments))) as pool:
            yield from pool.map(_process, segments)


class GeminiDocument:
    """Pass a document file directly as a Gemini ``inline_data`` Part.

    Uses the Rust fast-path when available. Yields a single Message.
    """

    name: str = "document-gemini"
    media_types: tuple[str, ...] = ("document",)

    def encode(self, path: Path, **kwargs) -> Iterable[Message]:
        try:
            from mm._mm import gemini_document_part

            json_str: str = gemini_document_part(str(path))
            part: dict[str, Any] = json.loads(json_str)
        except (ImportError, RuntimeError):
            data = path.read_bytes()
            mime = guess_mime(path.name)
            part = _gemini_inline_data_part(data, mime)

        logger.debug("gemini_doc [path=%s]", path.name)
        yield _to_gemini_message([part])


register(GeminiVideo())
register(GeminiVideoChunked())
register(GeminiDocument())
