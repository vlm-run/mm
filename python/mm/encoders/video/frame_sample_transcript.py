"""Legacy frame sampling + transcript encoder (deprecated).

Thin wrapper that delegates to ``video-frames-w-transcript``.
Kept for backward compatibility only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from mm.encoders import Message, register
from mm.encoders.video.frames import VideoFramesWithTranscript


class VideoFrameSampleWithTranscript:
    """Deprecated: use ``video-frames-w-transcript`` instead."""

    name: str = "video-frames-transcript"
    media_types: tuple[str, ...] = ("video",)

    _delegate = VideoFramesWithTranscript()

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        yield from self._delegate.encode(path, **kwargs)


register(VideoFrameSampleWithTranscript())
