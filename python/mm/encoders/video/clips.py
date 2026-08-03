"""Native base64 video clip encoders.

Sends video content directly as base64-encoded clips rather than
extracting individual frames.  Useful for models that accept video
input natively.

- ``clips``: Base64-encode video in uniform-duration chunks.
- ``clips-w-transcript``: Same with Whisper transcript prepended.

Uses PyAV for probing duration and ``mm.ffmpeg.extract_segment`` for
stream-copy segment extraction (fastest available method).
"""

from __future__ import annotations

import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterable

from mm.constants import guess_mime
from mm.encoders import register
from mm.encoders.base import Encoder, Message, to_message
from mm.encoders.video._transcript import encode_with_transcript
from mm.utils import get_b64

logger = logging.getLogger(__name__)

DEFAULT_CLIP_DURATION = 120
DEFAULT_OVERLAP = 10


class VideoClips(Encoder):
    """Base64-encode video clips of uniform duration.

    When ``duration`` is 0, -1, or not provided the video is clipped using
    the default clip duration and each one processed as base64-encoded clip.
    Otherwise the video is split into chunks of ``duration`` seconds and each
    is processed separately.

    Kwargs:
        duration: Clip length in seconds (default 120).
        overlap: Overlap between clips in seconds (default 10).
        max_size_mb: Skip chunks exceeding this size in MB (default None).
        mode: fast | accurate
    """

    name = "clips"
    kind = "video"

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        from mm.video import probe, pyav_runnable

        if not pyav_runnable():
            yield to_message(
                [
                    {"type": "text", "text": f"[PyAV not runnable for {path.name}]"},
                ]
            )
            return

        clip_duration: int = kwargs.get("duration", DEFAULT_CLIP_DURATION)
        max_size_mb: float | None = kwargs.get("max_size_mb", None)
        overlap: int = kwargs.get("overlap", DEFAULT_OVERLAP)
        video_duration = probe(path).duration

        if video_duration <= 0:
            yield to_message(
                [{"type": "text", "text": f"[Cannot determine duration for {path.name}]"}]
            )
            return

        mime: str = guess_mime(path.name)
        if video_duration <= clip_duration:
            yield from self._send_whole(path, video_duration, mime, max_size_mb)
        else:
            yield from self._send_chunks(
                path, video_duration, clip_duration, mime, max_size_mb, overlap
            )

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
            yield to_message(
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

        yield to_message(
            [
                {
                    "type": "text",
                    "text": f"Video clip of {path.name} (0.0s - {duration:.1f}s, {size_mb:.1f} MB):",
                },
                {
                    "type": "video_url",
                    "video_url": {"url": f"data:{mime};base64,{get_b64(data)}"},
                },
            ]
        )

    def _send_chunks(
        self,
        path: Path,
        video_duration: float,
        chunk_duration: int,
        mime: str,
        max_size_mb: float | None,
        overlap: int,
    ) -> Iterable[Message]:
        from mm.ffmpeg import extract_segment

        start: float = 0.0
        step: int = max(chunk_duration - overlap, 1)
        segments: list[tuple[float, float]] = []
        while start < video_duration:
            end = min(start + chunk_duration, video_duration)
            segments.append((start, end))
            start += step

        logger.debug(
            "video_clips_chunked [path=%s, duration=%.1fs, chunk=%ds, segments=%d]",
            path.name,
            video_duration,
            chunk_duration,
            len(segments),
        )

        def _submit_fn(varg: tuple[int, tuple[float, float]]):
            idx, (start, end) = varg
            with tempfile.NamedTemporaryFile(suffix=path.suffix, delete=False) as tmp:
                seg_path = Path(tmp.name)
            try:
                extract_segment(path, seg_path, start, end)
                seg_data = seg_path.read_bytes()
            finally:
                seg_path.unlink(missing_ok=True)

            size_mb = len(seg_data) / (1024 * 1024)
            if max_size_mb and size_mb > max_size_mb:
                return None

            return to_message(
                [
                    {
                        "type": "text",
                        "text": (
                            f"Video clip {idx + 1} of {path.name} "
                            f"({start:.1f}s - {end:.1f}s, {size_mb:.1f} MB):"
                        ),
                    },
                    {
                        "type": "video_url",
                        "video_url": {"url": f"data:{mime};base64,{get_b64(seg_data)}"},
                    },
                ]
            )

        with ThreadPoolExecutor(max_workers=min(4, len(segments))) as pool:
            yield from filter(None, pool.map(_submit_fn, enumerate(segments)))


class VideoClipsWithTranscript(Encoder):
    """Base64 video clips with Whisper transcript prepended.

    Kwargs: Same as ``VideoClips`` plus ``model``, ``language``, ``audio_speed``.
    """

    name = "clips-w-transcript"
    kind = "video"

    _visual = VideoClips()

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        yield from encode_with_transcript(path, self._visual.encode, **kwargs)


register(VideoClips())
register(VideoClipsWithTranscript())
