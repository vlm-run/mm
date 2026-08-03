"""Audio-only transcript encoder for video files.

Extracts and transcribes the audio track from a video file without
extracting any visual frames.  Useful for podcasts with video,
lectures, or any content where spoken word is more important than
visuals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from mm.encoders import register
from mm.encoders.base import Encoder, Message, to_message
from mm.encoders.video._transcript import transcript_messages


class VideoTranscript(Encoder):
    """Transcribe audio from a video file, return transcript only.

    Equivalent to the ``transcribe`` encoder but registered for the
    ``video`` kind. No visual frames are extracted.

    Kwargs:
        model: Transcription model name (default chosen by backend).
        language: Language code or "auto" (default "auto").
        audio_speed: Playback speed multiplier (default 2.0).
    """

    name = "transcript"
    kind = "video"
    generate = {"fast": None, "accurate": None}

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        model: str | None = kwargs.get("model")
        language: str = kwargs.get("language", "auto")
        audio_speed: float = kwargs.get("audio_speed", 2.0)

        msgs = list(
            transcript_messages(
                path,
                model=model,
                language=language,
                audio_speed=audio_speed,
            )
        )

        if msgs:
            yield from msgs
        else:
            yield to_message(
                [{"type": "text", "text": f"[No transcript available for {path.name}]"}]
            )


register(VideoTranscript())
