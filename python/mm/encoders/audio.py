"""Audio encoding strategies: base64 passthrough, transcription, and Gemini.

``AudioBase64`` base64-encodes the raw audio file as an OpenAI ``input_audio``
part — the native way to send audio to multimodal LLMs. Generate prompts come
from the pipeline YAML.

``AudioTranscribe`` runs Whisper transcription and returns the transcript as
text. Suppresses the LLM call via ``generate = {"fast": None, "accurate": None}``.

``GeminiAudio`` passes audio directly as Gemini ``inline_data`` Parts with
automatic chunking for long files. Generate prompts come from the pipeline YAML.
"""

from __future__ import annotations

import base64
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterable

from mm.encoders import register
from mm.encoders.base import Encoder, Message

logger = logging.getLogger(__name__)

_EXT_TO_FORMAT: dict[str, str] = {
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


class AudioBase64(Encoder):
    """Send the raw audio file as a base64-encoded ``input_audio`` part.

    This is the native way to pass audio to OpenAI-compatible models —
    no transcription, no preprocessing, just the raw waveform. The
    model receives the actual audio and can understand speech, music,
    ambient sound, etc.

    Kwargs:
        format: Audio format hint (default: inferred from file extension).
            One of ``mp3``, ``wav``, ``flac``, ``ogg``, ``m4a``, ``aac``.
        max_seconds: audio clip duration to encode
        overlap: overlap between audio clips
        mode: fast | accurate.
        generate_model: --generate.model CLI flag.
    """

    name = "base64"
    kind = "audio"

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        from mm.ffmpeg import extract_segment, probe_duration
        from mm.video import pyav_runnable

        fmt: str = kwargs.get(
            "format",
            _EXT_TO_FORMAT.get(path.suffix.lower(), "mp3"),
        )

        if not pyav_runnable():
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": "Audio content to analyze",
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": base64.b64encode(path.read_bytes()).decode(),
                            "format": fmt,
                        },
                    },
                ]
            )
            return

        max_seconds: int = int(kwargs.get("max_seconds", 120))
        overlap: int = int(kwargs.get("overlap", 10))
        duration = probe_duration(path)
        if duration <= max_seconds:
            logger.debug("base64 [path=%s, duration=%.1fs, single]", path.name, duration)
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": "Audio content to analyze",
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": base64.b64encode(path.read_bytes()).decode(),
                            "format": fmt,
                        },
                    },
                ]
            )
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
            "audio_base64_chunked [path=%s, duration=%.1fs, chunk=%ds, n_segments=%d]",
            path.name,
            duration,
            max_seconds,
            len(segments),
        )

        def _submit_fn(varg: tuple[int, tuple[float, float]]) -> Message:
            idx, (start, end) = varg
            with tempfile.NamedTemporaryFile(suffix=path.suffix, delete=False) as tmp:
                seg_path = Path(tmp.name)
            try:
                extract_segment(path, seg_path, start, end)
                seg_data = seg_path.read_bytes()
            finally:
                seg_path.unlink(missing_ok=True)

            return _to_message(
                [
                    {
                        "type": "text",
                        "text": f"Audio chunk to analyze {idx + 1} ({start:.0f}s-{end:.0f}s):",
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {"data": base64.b64encode(seg_data).decode(), "format": fmt},
                    },
                ]
            )

        with ThreadPoolExecutor(max_workers=min(4, len(segments))) as pool:
            yield from pool.map(_submit_fn, enumerate(segments))


class AudioTranscribe(Encoder):
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

    name = "transcribe"
    kind = "audio"
    generate = {"fast": None, "accurate": None}

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

        from mm.common.audio import transcribe_available, transcribe_file
        from mm.ffmpeg import ffmpeg_available

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

        resolved_lang = None if language == "auto" else language
        whisper_result = transcribe_file(
            path,
            model=model,
            language=resolved_lang,
            audio_speed=audio_speed,
            beam_size=5,
            backend=backend,
            base_url=base_url,
            api_key=api_key,
        )

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


class GeminiAudio(Encoder):
    """Pass an audio file directly as a Gemini ``input_audio`` Part.

    For files longer than ``max_seconds``, splits into overlapping
    chunks via ffmpeg and yields one Message per chunk.

    Kwargs:
        max_seconds: Maximum chunk length in seconds (default 120).
        overlap: Overlap between chunks in seconds (default 10).
        mode: fast | accurate.
    """

    name = "gemini"
    kind = "audio"

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        from mm.ffmpeg import extract_segment, probe_duration
        from mm.video import pyav_runnable

        fmt: str = kwargs.get(
            "format",
            _EXT_TO_FORMAT.get(path.suffix.lower(), "mp3"),
        )

        if not pyav_runnable():
            data = path.read_bytes()
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": "Audio content to analyze",
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {"data": base64.b64encode(data).decode(), "format": fmt},
                    },
                ]
            )
            return

        max_seconds: int = kwargs.get("max_seconds", 120)
        overlap: int = kwargs.get("overlap", 10)
        duration = probe_duration(path)

        if duration <= max_seconds:
            data = path.read_bytes()
            logger.debug("gemini_audio [path=%s, duration=%.1fs, single]", path.name, duration)
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": "Audio content to analyze",
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {"data": base64.b64encode(data).decode(), "format": fmt},
                    },
                ]
            )
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

        def _submit_fn(varg: tuple[int, tuple[float, float]]) -> Message:
            idx, (start, end) = varg
            with tempfile.NamedTemporaryFile(suffix=path.suffix, delete=False) as tmp:
                seg_path = Path(tmp.name)
            try:
                extract_segment(path, seg_path, start, end)
                seg_data = seg_path.read_bytes()
            finally:
                seg_path.unlink(missing_ok=True)
            return _to_message(
                [
                    {
                        "type": "text",
                        "text": f"Audio chunk to analyze {idx + 1} ({start:.0f}s-{end:.0f}s):",
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {"data": base64.b64encode(seg_data).decode(), "format": fmt},
                    },
                ]
            )

        with ThreadPoolExecutor(max_workers=min(4, len(segments))) as pool:
            yield from pool.map(_submit_fn, enumerate(segments))


register(AudioBase64())
register(AudioTranscribe())
register(GeminiAudio())
