"""Legacy shot-based video encoders (deprecated).

These are thin wrappers that delegate to the new ``shots.py`` encoders.
Kept for backward compatibility only — use ``video-shots`` and
``video-shot-mosaic`` instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from mm.encoders import Message, register
from mm.encoders.video.shots import VideoShotMosaic, VideoShots


class ShotFrames:
    """Deprecated: use ``video-shots`` instead."""

    name: str = "shot-frames"
    media_types: tuple[str, ...] = ("video",)

    _delegate = VideoShots()

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        yield from self._delegate.encode(path, **kwargs)


class ShotMosaic:
    """Deprecated: use ``video-shot-mosaic`` instead."""

    name: str = "shot-mosaic"
    media_types: tuple[str, ...] = ("video",)

    _delegate = VideoShotMosaic()

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        yield from self._delegate.encode(path, **kwargs)


register(ShotFrames())
register(ShotMosaic())
