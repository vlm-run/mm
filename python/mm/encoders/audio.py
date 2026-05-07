"""Audio encoding strategies: base64 passthrough, transcription, and Gemini.

``AudioBase64`` reads the raw audio file, base64-encodes it, and yields
an OpenAI ``input_audio`` content part — the native way to send audio
to multimodal LLMs without any preprocessing.

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

_EXT_TO_OPENAI_FORMAT: dict[str, str] = {
    ".mp3": "mp3",
    ".wav": "wav",
    ".flac": "flac",
    ".ogg": "ogg",
    ".m4a": "m4a",
    ".aac": "aac",
    ".opus": "opus",
    ".webm": "webm",
}


def _to_message(parts: list[dict[str, Any]]) -> Message:
    return {"role": "user", "content": parts}


class AudioBase64:
    """Send the raw audio file as a base64-encoded ``input_audio`` part.

    This is the native way to pass audio to OpenAI-compatible models —
    no transcription, no preprocessing, just the raw waveform.  The
    model receives the actual audio and can understand speech, music,
    ambient sound, etc.

    Kwargs:
        format: Audio format hint (default: inferred from file extension).
            One of ``mp3``, ``wav``, ``flac``, ``ogg``, ``m4a``, ``aac``.
    """

    name: str = "audio-base64"
    media_types: tuple[str, ...] = ("audio",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        fmt: str = kwargs.get(
            "format",
            _EXT_TO_OPENAI_FORMAT.get(path.suffix.lower(), "mp3"),
        )
        data = path.read_bytes()
        b64 = base64.b64encode(data).decode()

        size_kb = len(data) / 1024
        logger.debug(
            "audio_base64 [path=%s, format=%s, size=%.1fKB]",
            path.name,
            fmt,
            size_kb,
        )

        yield _to_message(
            [
                {
                    "type": "input_audio",
                    "input_audio": {"data": b64, "format": fmt},
                }
            ]
        )


class AudioTranscribe:
    """Transcribe audio and return the transcript as a text message.

    Uses the modular transcription backend system.  By default, picks
    the best local backend (MLX > CTranslate2).  Set ``backend`` to
    ``"openai"`` + ``base_url`` to use a remote transcription service.

    Kwargs:
        whisper_model: Model name or size (default "medium").
        language: Language code or "auto" for detection (default "auto").
        audio_speed: Playback speed multiplier (default 1.0).
        backend: Transcription backend name (``"mlx"``, ``"ctranslate2"``,
            ``"openai"``).  ``None`` for auto-detect.
        base_url: Custom base URL for the ``openai`` backend.
        api_key: API key for the ``openai`` backend.
    """

    name: str = "audio-transcribe"
    media_types: tuple[str, ...] = ("audio",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        whisper_model: str = kwargs.get("whisper_model", "medium")
        language: str = kwargs.get("language", "auto")
        audio_speed: float = kwargs.get("audio_speed", 1.0)

        backend: str | None = kwargs.get("backend", None)
        base_url: str | None = kwargs.get("base_url", None)
        api_key: str | None = kwargs.get("api_key", None)

        from mm.video import extract_audio, ffmpeg_available
        from mm.common.audio import transcribe, transcribe_available

        if not ffmpeg_available() and backend != "openai":
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": "[ffmpeg not available — required for audio extraction]",
                    }
                ]
            )
            return

        if not transcribe_available() and backend is None:
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": "[no transcription backend available — check your mm installation]",
                    }
                ]
            )
            return

        audio_result = extract_audio(path, speed=audio_speed)

        lang_kwarg: dict[str, str | None] = {}
        if language != "auto":
            lang_kwarg["language"] = language

        whisper_result = transcribe(
            audio_result.path,
            model=whisper_model,
            beam_size=5,
            audio_speed=audio_speed,
            backend=backend,
            base_url=base_url,
            api_key=api_key,
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
                        f" {whisper_result.elapsed_ms / 1000:.1f}s):\n\n" + "\n".join(segment_lines)
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

        from mm.video import _pyav_available, extract_segment, probe

        if not _pyav_available():
            data: bytes = path.read_bytes()
            mime: str = guess_mime(path.name)
            b64 = base64.b64encode(data).decode()
            yield _to_message([{"inline_data": {"mime_type": mime, "data": b64}}])
            return

        duration: float = probe(path).duration
        if duration <= max_seconds:
            data = path.read_bytes()
            mime = guess_mime(path.name)
            b64 = base64.b64encode(data).decode()
            logger.debug("gemini_audio [path=%s, duration=%.1fs, single]", path.name, duration)
            yield _to_message([{"inline_data": {"mime_type": mime, "data": b64}}])
            return

        import tempfile

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
                extract_segment(path, seg_path, start, end)
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


register(AudioBase64())
register(AudioTranscribe())
register(GeminiAudio())
