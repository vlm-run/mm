"""Audio encoding strategies: transcription and Gemini passthrough.

``AudioTranscribe`` extracts audio (via ffmpeg) and runs Whisper
transcription, returning the transcript as a text Message.

``GeminiAudio`` passes audio files directly as Gemini ``inline_data``
Parts, with automatic chunking for long files.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any, Iterable

from mm.constants import guess_mime
from mm.encoders import Message, register

logger = logging.getLogger(__name__)


def _to_message(parts: list[dict[str, Any]]) -> Message:
    return {"role": "user", "content": parts}


class AudioTranscribe:
    """Transcribe audio via Whisper, return transcript as a text message.

    Extracts audio with ffmpeg (supports speed adjustment), then runs
    Whisper transcription.  Returns a single Message with the full
    transcript text plus per-segment timestamps.

    Kwargs:
        whisper_model: Whisper model size (default "medium").
        language: Language code or "auto" for detection (default "auto").
        audio_speed: Playback speed multiplier (default 1.0).
    """

    name: str = "transcribe"
    media_types: tuple[str, ...] = ("audio",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        whisper_model: str = kwargs.get("whisper_model", "medium")
        language: str = kwargs.get("language", "auto")
        audio_speed: float = kwargs.get("audio_speed", 1.0)

        from mm.ffmpeg import extract_audio, ffmpeg_available
        from mm.whisper import transcribe, whisper_available

        if not ffmpeg_available():
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": f"[ffmpeg not available for {path.name}]",
                    }
                ]
            )
            return

        if not whisper_available():
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": "[whisper not installed — pip install mm[audio]]",
                    }
                ]
            )
            return

        audio_result = extract_audio(path, speed=audio_speed)

        lang_kwarg: dict[str, str] = {}
        if language != "auto":
            lang_kwarg["language"] = language

        whisper_result = transcribe(
            audio_result.path,
            model_size=whisper_model,
            beam_size=5,
            audio_speed=audio_speed,
            **lang_kwarg,
        )

        try:
            audio_result.path.unlink(missing_ok=True)
        except Exception:
            pass

        transcript = whisper_result.text
        if not transcript or transcript.startswith("["):
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": transcript or "[No speech detected]",
                    }
                ]
            )
            return

        parts: list[dict[str, Any]] = []

        if whisper_result.segments:
            segment_lines = []
            for seg in whisper_result.segments:
                segment_lines.append(f"[{seg.start:.1f}s - {seg.end:.1f}s] {seg.text.strip()}")
            parts.append(
                {
                    "type": "text",
                    "text": (
                        f"Transcript of {path.name}"
                        f" (lang={whisper_result.language},"
                        f" model={whisper_model},"
                        f" {whisper_result.elapsed_ms:.0f}ms):\n\n" + "\n".join(segment_lines)
                    ),
                }
            )
        else:
            parts.append(
                {
                    "type": "text",
                    "text": f"Transcript of {path.name}:\n\n{transcript}",
                }
            )

        logger.debug(
            "audio_transcribe [path=%s, words=%d, model=%s, %.0fms]",
            path.name,
            len(transcript.split()),
            whisper_model,
            whisper_result.elapsed_ms,
        )
        yield _to_message(parts)


class GeminiAudio:
    """Pass an audio file directly as a Gemini ``inline_data`` Part.

    For files longer than ``max_seconds``, splits into overlapping
    chunks via ffmpeg and yields one Message per chunk.

    Kwargs:
        max_seconds: Maximum chunk length in seconds (default 120).
        overlap: Overlap between chunks in seconds (default 10).
    """

    name: str = "audio-gemini"
    media_types: tuple[str, ...] = ("audio",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        max_seconds: int = kwargs.get("max_seconds", 120)
        overlap: int = kwargs.get("overlap", 10)

        from mm.ffmpeg import ffmpeg_available, probe_duration

        if not ffmpeg_available():
            data: bytes = path.read_bytes()
            mime: str = guess_mime(path.name)
            b64 = base64.b64encode(data).decode()
            yield _to_message([{"inline_data": {"mime_type": mime, "data": b64}}])
            return

        duration: float = probe_duration(path)
        if duration <= max_seconds:
            data = path.read_bytes()
            mime = guess_mime(path.name)
            b64 = base64.b64encode(data).decode()
            logger.debug("gemini_audio [path=%s, duration=%.1fs, single]", path.name, duration)
            yield _to_message([{"inline_data": {"mime_type": mime, "data": b64}}])
            return

        import tempfile

        from mm.ffmpeg import extract_segment

        step: int = max(max_seconds - overlap, 1)
        start: float = 0.0
        chunk_idx: int = 0

        logger.debug(
            "gemini_audio_chunked [path=%s, duration=%.1fs, chunk=%ds]",
            path.name,
            duration,
            max_seconds,
        )

        while start < duration:
            end: float = min(start + max_seconds, duration)
            with tempfile.NamedTemporaryFile(suffix=path.suffix, delete=False) as tmp:
                seg_path = Path(tmp.name)
            try:
                extract_segment(str(path), str(seg_path), start, end)
                seg_data = seg_path.read_bytes()
            finally:
                seg_path.unlink(missing_ok=True)
            mime = guess_mime(path.name)
            b64 = base64.b64encode(seg_data).decode()
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": f"Audio chunk {chunk_idx + 1} ({start:.0f}s-{end:.0f}s):",
                    },
                    {"inline_data": {"mime_type": mime, "data": b64}},
                ]
            )
            start += step
            chunk_idx += 1


register(AudioTranscribe())
register(GeminiAudio())
