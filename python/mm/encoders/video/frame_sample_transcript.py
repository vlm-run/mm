"""Frame sampling with audio transcript for accurate video understanding.

Combines ``VideoFrameSample`` (visual frames at configurable fps) with
Whisper transcription of the audio track.  The transcript is yielded as
the first Message so that the LLM receives spoken context before frames.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any, Iterable

from mm.encoders import Message, _resolve_provider, register
from mm.encoders.image import _image_part, _to_message
from mm.encoders.video import _uniform_timestamps

logger = logging.getLogger(__name__)


class VideoFrameSampleWithTranscript:
    """Extract frames at *fps* **and** transcribe audio via Whisper.

    Yields a transcript Message first, then batches of frames identical
    to ``VideoFrameSample``.  When Whisper is unavailable the encoder
    falls back to frame-only output.

    Kwargs:
        fps: Frames per second to sample (default 1.0).
        max_width: Frame resize width in pixels (default 1024).
        max_frames_per_message: Frames per Message (default 16).
        whisper_model: Whisper model size (default "medium").
        language: Language code or "auto" (default "auto").
        audio_speed: Playback speed multiplier (default 1.0).
    """

    name: str = "video-frames-transcript"
    media_types: tuple[str, ...] = ("video",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        fps: float = kwargs.get("fps", 1.0)
        max_width: int = kwargs.get("max_width", 1024)
        max_frames_per_message: int = kwargs.get("max_frames_per_message", 16)
        whisper_model: str = kwargs.get("whisper_model", "medium")
        language: str = kwargs.get("language", "auto")
        audio_speed: float = kwargs.get("audio_speed", 1.0)
        provider: str = _resolve_provider()

        from mm.ffmpeg import (
            extract_frames_at_timestamps,
            ffmpeg_available,
            probe_duration,
        )

        if not ffmpeg_available():
            yield _to_message([{"type": "text", "text": f"[ffmpeg not available for {path.name}]"}])
            return

        duration: float = probe_duration(path)
        if duration <= 0:
            yield _to_message(
                [{"type": "text", "text": f"[Cannot determine duration for {path.name}]"}]
            )
            return

        yield from self._transcript_messages(path, whisper_model, language, audio_speed)

        timestamps: list[float] = _uniform_timestamps(duration, fps)
        max_total: int = max_frames_per_message * 8
        if len(timestamps) > max_total:
            step: int = len(timestamps) // max_total
            timestamps = timestamps[::step]

        logger.debug(
            "frame_sample_w_transcript [path=%s, duration=%.1fs, fps=%.1f, frames=%d]",
            path.name,
            duration,
            fps,
            len(timestamps),
        )

        frame_paths: list[Path] = extract_frames_at_timestamps(
            path,
            timestamps,
            thumb_width=max_width,
        )

        if not frame_paths:
            yield _to_message([{"type": "text", "text": f"[No frames extracted from {path.name}]"}])
            return

        try:
            for i in range(0, len(frame_paths), max_frames_per_message):
                batch: list[Path] = frame_paths[i : i + max_frames_per_message]
                parts: list[dict[str, Any]] = []

                t_start: float = timestamps[i] if i < len(timestamps) else 0.0
                t_end_idx: int = min(i + max_frames_per_message, len(timestamps)) - 1
                t_end: float = timestamps[t_end_idx] if timestamps else 0.0
                parts.append(
                    {
                        "type": "text",
                        "text": f"Video frames from {path.name} ({t_start:.1f}s - {t_end:.1f}s):",
                    }
                )

                for frame_path in batch:
                    b64: str = base64.b64encode(frame_path.read_bytes()).decode()
                    parts.append(_image_part(b64, "image/jpeg", provider))

                yield _to_message(parts)
        finally:
            for fp in frame_paths:
                try:
                    fp.unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def _transcript_messages(
        path: Path,
        whisper_model: str,
        language: str,
        audio_speed: float,
    ) -> Iterable[Message]:
        """Extract and yield a transcript Message, or skip silently."""
        try:
            from mm.ffmpeg import extract_audio
            from mm.whisper import transcribe, whisper_available
        except ImportError:
            return

        if not whisper_available():
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
            return

        if whisper_result.segments:
            segment_lines = [
                f"[{seg.start:.1f}s - {seg.end:.1f}s] {seg.text.strip()}"
                for seg in whisper_result.segments
            ]
            text = (
                f"Audio transcript of {path.name}"
                f" (lang={whisper_result.language},"
                f" model={whisper_model},"
                f" {whisper_result.elapsed_ms:.0f}ms):\n\n" + "\n".join(segment_lines)
            )
        else:
            text = f"Audio transcript of {path.name}:\n\n{transcript}"

        yield _to_message([{"type": "text", "text": text}])


register(VideoFrameSampleWithTranscript())
