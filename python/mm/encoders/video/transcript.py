"""Audio-only transcript encoder for video files.

Extracts and transcribes the audio track from a video file without
extracting any visual frames.  Useful for podcasts with video,
lectures, or any content where spoken word is more important than
visuals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from mm.encoders import Message, register
from mm.encoders.image import _to_message
from mm.encoders.video._transcript import transcript_messages


class VideoTranscript:
    """Transcribe audio from a video file, return transcript only.

    Equivalent to the ``audio-transcribe`` encoder but registered for
    the ``video`` media type.  No visual frames are extracted.

    Kwargs:
        whisper_model: Whisper model size (default "medium").
        language: Language code or "auto" (default "auto").
        audio_speed: Playback speed multiplier (default 1.0).
    """

    name: str = "video-transcript"
    media_types: tuple[str, ...] = ("video",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        whisper_model: str = kwargs.get("whisper_model", "medium")
        language: str = kwargs.get("language", "auto")
        audio_speed: float = kwargs.get("audio_speed", 1.0)

        msgs = list(
            transcript_messages(
                path,
                whisper_model=whisper_model,
                language=language,
                audio_speed=audio_speed,
            )
        )

        if msgs:
            yield from msgs
        else:
            yield _to_message(
                [{"type": "text", "text": f"[No transcript available for {path.name}]"}]
            )


register(VideoTranscript())
