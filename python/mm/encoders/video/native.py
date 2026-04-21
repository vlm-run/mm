"""Native base64 video clip encoders.

Sends video content directly as base64-encoded clips rather than
extracting individual frames.  Useful for models that accept video
input natively.

- ``video-clips``: Base64-encode video in uniform-duration chunks.
- ``video-clips-w-transcript``: Same with Whisper transcript prepended.

Uses PyAV for probing duration and ``mm.video.extract_segment`` for
stream-copy segment extraction (fastest available method).
"""

from __future__ import annotations

import base64
import logging
import tempfile
from pathlib import Path
from typing import Any, Iterable

from mm.constants import guess_mime
from mm.encoders import Message, register
from mm.encoders.image import _to_message
from mm.encoders.video._transcript import encode_with_transcript

logger = logging.getLogger(__name__)


class VideoClips:
    """Base64-encode video clips of uniform duration.

    When ``duration`` is 0, -1, or not provided the entire video is sent
    as a single base64-encoded clip.  Otherwise the video is split into
    chunks of ``duration`` seconds and each is sent separately.

    Kwargs:
        duration: Clip length in seconds (default 0 = whole video).
        max_size_mb: Skip chunks exceeding this size in MB (default None).
    """

    name: str = "video-clips"
    media_types: tuple[str, ...] = ("video",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        duration: int = kwargs.get("duration", 0)
        max_size_mb: float | None = kwargs.get("max_size_mb", None)

        from mm.video import _pyav_available, probe

        if not _pyav_available():
            yield _to_message([{"type": "text", "text": f"[PyAV not available for {path.name}]"}])
            return

        info = probe(path)
        video_duration = info.duration
        if video_duration <= 0:
            yield _to_message(
                [{"type": "text", "text": f"[Cannot determine duration for {path.name}]"}]
            )
            return

        mime: str = guess_mime(path.name)

        if duration <= 0:
            yield from self._send_whole(path, video_duration, mime, max_size_mb)
        else:
            yield from self._send_chunks(path, video_duration, duration, mime, max_size_mb)

    def _send_whole(
        self,
        path: Path,
        duration: float,
        mime: str,
        max_size_mb: float | None,
    ) -> Iterable[Message]:
        data = path.read_bytes()
        size_mb = len(data) / (1024 * 1024)
        if max_size_mb and size_mb > max_size_mb:
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": f"[Video {path.name} is {size_mb:.1f} MB, exceeds {max_size_mb} MB limit]",
                    }
                ]
            )
            return

        logger.debug(
            "video_clips [path=%s, duration=%.1fs, whole=%.1fMB]",
            path.name,
            duration,
            size_mb,
        )

        b64 = base64.b64encode(data).decode()
        yield _to_message(
            [
                {
                    "type": "text",
                    "text": f"Video clip of {path.name} (0.0s - {duration:.1f}s, {size_mb:.1f} MB):",
                },
                {"inline_data": {"mime_type": mime, "data": b64}},
            ]
        )

    def _send_chunks(
        self,
        path: Path,
        video_duration: float,
        chunk_duration: int,
        mime: str,
        max_size_mb: float | None,
    ) -> Iterable[Message]:
        from mm.video import extract_segment

        start: float = 0.0
        chunk_idx: int = 0

        logger.debug(
            "video_clips_chunked [path=%s, duration=%.1fs, chunk=%ds]",
            path.name,
            video_duration,
            chunk_duration,
        )

        while start < video_duration:
            end: float = min(start + chunk_duration, video_duration)
            seg_path = Path(tempfile.mktemp(suffix=path.suffix))
            try:
                extract_segment(path, seg_path, start, end)
                seg_data = seg_path.read_bytes()
            finally:
                seg_path.unlink(missing_ok=True)

            size_mb = len(seg_data) / (1024 * 1024)
            if max_size_mb and size_mb > max_size_mb:
                start = end
                chunk_idx += 1
                continue

            b64 = base64.b64encode(seg_data).decode()
            yield _to_message(
                [
                    {
                        "type": "text",
                        "text": (
                            f"Video clip {chunk_idx + 1} of {path.name} "
                            f"({start:.1f}s - {end:.1f}s, {size_mb:.1f} MB):"
                        ),
                    },
                    {"inline_data": {"mime_type": mime, "data": b64}},
                ]
            )
            start = end
            chunk_idx += 1


class VideoClipsWithTranscript:
    """Base64 video clips with Whisper transcript prepended.

    Kwargs: Same as ``VideoClips`` plus ``whisper_model``, ``language``,
    ``audio_speed``.
    """

    name: str = "video-clips-w-transcript"
    media_types: tuple[str, ...] = ("video",)

    _visual = VideoClips()

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        yield from encode_with_transcript(path, self._visual.encode, **kwargs)


register(VideoClips())
register(VideoClipsWithTranscript())
