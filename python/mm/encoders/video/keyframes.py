"""I-frame (keyframe) extraction encoder.

Decodes only I-frames from the video bitstream via PyAV's codec-level
``skip_frame='NONKEY'``, which skips all non-keyframes at the demuxer
level — much faster than uniform sampling for capturing scene changes.

Replaces the old ffprobe JSON parse → ffmpeg extract pipeline with
a single in-process pass.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from mm.encoders import Message, _resolve_provider, register
from mm.encoders.image import _image_part, _to_message
from mm.encoders.video._transcript import encode_with_transcript

logger = logging.getLogger(__name__)


class VideoKeyframes:
    """Extract I-frames (keyframes) from the video bitstream.

    Uses PyAV's ``skip_frame='NONKEY'`` to decode only I-frames in a
    single pass — much more efficient than the old ffprobe + ffmpeg
    two-step pipeline.

    Kwargs:
        max_keyframes: Cap the number of keyframes (default None = all).
        max_width: Frame resize width in pixels (default 1024).
        max_keyframes_per_message: Keyframes per Message batch (default 16).
    """

    name: str = "video-keyframes"
    media_types: tuple[str, ...] = ("video",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        max_keyframes: int | None = kwargs.get("max_keyframes", None)
        max_width: int = kwargs.get("max_width", 1024)
        max_keyframes_per_message: int = kwargs.get("max_keyframes_per_message", 16)
        provider: str = _resolve_provider()

        from mm.video import VideoReader, _pyav_available

        if not _pyav_available():
            yield _to_message([{"type": "text", "text": f"[PyAV not available for {path.name}]"}])
            return

        with VideoReader(path) as reader:
            kf_stream = reader.keyframes(width=max_width, max_frames=max_keyframes)

            if len(kf_stream) == 0:
                yield _to_message(
                    [{"type": "text", "text": f"[No keyframes found in {path.name}]"}]
                )
                return

            logger.debug(
                "video_keyframes [path=%s, keyframes=%d]",
                path.name,
                len(kf_stream),
            )

            for batch in kf_stream.batched(max_keyframes_per_message):
                t_start = batch[0].timestamp
                t_end = batch[-1].timestamp
                parts: list[dict[str, Any]] = [
                    {
                        "type": "text",
                        "text": (
                            f"Keyframes from {path.name} "
                            f"({t_start:.1f}s - {t_end:.1f}s, "
                            f"{len(batch)} I-frames):"
                        ),
                    }
                ]
                for frame in batch:
                    b64, mime = frame.encode_jpeg()
                    parts.append(_image_part(b64, mime, provider))
                yield _to_message(parts)


class VideoKeyframesWithTranscript:
    """Extract I-frames with Whisper transcript prepended.

    Kwargs: Same as ``VideoKeyframes`` plus ``model``,
    ``language``, ``audio_speed``.
    """

    name: str = "video-keyframes-w-transcript"
    media_types: tuple[str, ...] = ("video",)

    _visual = VideoKeyframes()

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        yield from encode_with_transcript(path, self._visual.encode, **kwargs)


register(VideoKeyframes())
register(VideoKeyframesWithTranscript())
