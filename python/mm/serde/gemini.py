"""Gemini passthrough strategies: pass files directly as Gemini Parts."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Iterable

from mm.serde import Message, register


def _gemini_inline_data_part(data: bytes, mime: str) -> dict[str, Any]:
    """Construct a Gemini inline_data Part."""
    b64 = base64.b64encode(data).decode()
    return {"inline_data": {"mime_type": mime, "data": b64}}


def _mime_for(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
        ".avi": "video/x-msvideo",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }.get(ext, "application/octet-stream")


def _to_gemini_message(parts: list[dict[str, Any]]) -> Message:
    return {"role": "user", "content": parts}


class GeminiVideo:
    """Pass video file directly as a Gemini inline_data Part."""

    name = "gemini_video"
    media_types = ("video",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        try:
            from mm._mm import gemini_video_parts

            json_strs = gemini_video_parts(str(path))
            parts = [json.loads(s) for s in json_strs]
        except (ImportError, RuntimeError):
            data = path.read_bytes()
            mime = _mime_for(path)
            parts = [_gemini_inline_data_part(data, mime)]

        yield _to_gemini_message(parts)


class GeminiVideoChunked:
    """Chunk video and pass each chunk as a Gemini Part.

    Uses ffmpeg to extract time-based segments, then encodes each
    segment as a Gemini inline_data Part.
    """

    name = "gemini_video_chunked"
    media_types = ("video",)

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

        duration = probe_duration(path)
        if duration <= max_seconds:
            # Short video — pass as single part
            data = path.read_bytes()
            mime = _mime_for(path)
            yield _to_gemini_message([_gemini_inline_data_part(data, mime)])
            return

        # Chunk the video
        import tempfile

        step = max_seconds - overlap
        start = 0.0
        while start < duration:
            end = min(start + max_seconds, duration)
            with tempfile.NamedTemporaryFile(suffix=path.suffix, delete=False) as tmp:
                seg_path = Path(tmp.name)
            extract_segment(str(path), str(seg_path), start, end)
            data = seg_path.read_bytes()
            mime = _mime_for(path)
            seg_path.unlink(missing_ok=True)
            yield _to_gemini_message([_gemini_inline_data_part(data, mime)])
            start += step


class GeminiDocument:
    """Pass document file directly as a Gemini inline_data Part."""

    name = "gemini_doc"
    media_types = ("document",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        try:
            from mm._mm import gemini_document_part

            json_str = gemini_document_part(str(path))
            part = json.loads(json_str)
        except (ImportError, RuntimeError):
            data = path.read_bytes()
            mime = _mime_for(path)
            part = _gemini_inline_data_part(data, mime)

        yield _to_gemini_message([part])


register(GeminiVideo())
register(GeminiVideoChunked())
register(GeminiDocument())
