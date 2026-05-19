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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterable

from mm.constants import guess_mime
from mm.encoders import Message, register
from mm.pipelines.schema import Generate

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


class AudioGenerate:
    fast = Generate(
        prompt="Describe this audio in 10 words or less.",
        max_tokens=128,
    )
    accurate = Generate(
        prompt=(
            "Describe the content of this audio in detail. Include what is spoken or heard, "
            "key topics covered, the speaker's tone, and any notable sounds or context."
        ),
        max_tokens=1024,
    )


class AudioBase64(AudioGenerate):
    """Send the raw audio file as a base64-encoded ``input_audio`` part.

    This is the native way to pass audio to OpenAI-compatible models —
    no transcription, no preprocessing, just the raw waveform. The
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

    Uses the modular transcription backend system. By default, calls
    the VLM Run gateway's OpenAI-compatible endpoint. Override
    ``base_url`` to point at localhost or OpenAI directly.

    Kwargs:
        model: Model name (default chosen by backend).
        language: Language code or "auto" for detection (default "auto").
        audio_speed: Playback speed multiplier (default 1.0).
        backend: Transcription backend name (``"openai"``, ``"mlx"``,
            ``"ctranslate2"``).  ``None`` for auto-detect.
        base_url: Custom base URL for the ``openai`` backend.
        api_key: API key for the ``openai`` backend.
    """

    name: str = "audio-transcribe"
    media_types: tuple[str, ...] = ("audio",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        model: str | None = kwargs.get("model")
        language: str = kwargs.get("language", "auto")
        audio_speed: float = kwargs.get("audio_speed", 1.0)

        backend: str | None = kwargs.get("backend", None)
        base_url: str | None = kwargs.get("base_url", None)
        api_key: str | None = kwargs.get("api_key", None)

        if backend is None or base_url is None or api_key is None:
            from mm.config import get_transcription_config

            cfg = get_transcription_config()
            backend = backend or cfg.backend
            base_url = base_url or cfg.base_url
            api_key = api_key or cfg.api_key

        from mm.common.audio import transcribe, transcribe_available
        from mm.ffmpeg import audio_transformer, ffmpeg_available

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

        if not transcribe_available():
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": "[no transcription backend available — check your mm installation]",
                    }
                ]
            )
            return

        audio_result = audio_transformer(path, speed=audio_speed)

        lang_kwarg: dict[str, str | None] = {}
        if language != "auto":
            lang_kwarg["language"] = language

        whisper_result = transcribe(
            audio_result.path,
            model=model,
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
                        f" model={whisper_result.model_size},"
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
            whisper_result.model_size,
            whisper_result.elapsed_ms,
        )
        yield _to_message(parts)


class GeminiAudio(AudioGenerate):
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

        from mm.video import extract_segment, probe, pyav_runnable

        if not pyav_runnable():
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

        step: float = max(max_seconds - overlap, 1)
        segments: list[tuple[float, float]] = []
        start: float = 0.0
        while start < duration:
            end = min(start + max_seconds, duration)
            segments.append((start, end))
            start += step

        logger.debug(
            "gemini_audio_chunked [path=%s, duration=%.1fs, chunk=%ds, n_segments=%d]",
            path.name,
            duration,
            max_seconds,
            len(segments),
        )

        mime = guess_mime(path.name)

        def _submit_fn(varg: tuple[int, tuple[float, float]]) -> Message:
            idx, (start, end) = varg
            with tempfile.NamedTemporaryFile(suffix=path.suffix, delete=False) as tmp:
                seg_path = Path(tmp.name)
            try:
                extract_segment(path, seg_path, start, end)
                seg_data = seg_path.read_bytes()
            finally:
                seg_path.unlink(missing_ok=True)
            b64 = base64.b64encode(seg_data).decode()
            return _to_message(
                [
                    {
                        "type": "text",
                        "text": f"Audio chunk {idx + 1} ({start:.0f}s-{end:.0f}s):",
                    },
                    {"inline_data": {"mime_type": mime, "data": b64}},
                ]
            )

        with ThreadPoolExecutor(max_workers=min(4, len(segments))) as pool:
            yield from pool.map(_submit_fn, enumerate(segments))


register(AudioBase64())
register(AudioTranscribe())
register(GeminiAudio())
