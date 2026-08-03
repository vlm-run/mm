"""Adaptive visual summary encoder.

Selects a fixed budget of representative frames from a video using
scene detection (when available) or uniform temporal spread. Unlike
``shots`` which returns ALL shots, this targets a compact
fixed-size output suitable for long videos.

Uses PyAV for in-process frame decoding — no subprocess or temp files.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from mm.encoders import register, resolve_provider
from mm.encoders.base import Encoder, Message, to_message
from mm.encoders.image import _image_part
from mm.encoders.video._transcript import encode_with_transcript

logger = logging.getLogger(__name__)


def _select_summary_timestamps(
    path: Path,
    duration: float,
    num_frames: int,
    use_scene_detection: bool,
) -> list[float]:
    """Pick N representative timestamps spread across the video."""
    if use_scene_detection:
        from mm.common.video.shot_detection import detect_scenes

        result = detect_scenes(path)
        if result.scenes and len(result.scenes) > 1:
            midpoints = [(s + e) / 2 for s, e in result.scenes]
            if len(midpoints) <= num_frames:
                return midpoints
            step = len(midpoints) / num_frames
            return [midpoints[int(i * step)] for i in range(num_frames)]

    if num_frames <= 1:
        return [duration / 2]
    step = duration / (num_frames + 1)
    return [step * (i + 1) for i in range(num_frames)]


class VideoSummary(Encoder):
    """Adaptive N-frame visual summary of a video.

    Combines scene detection with temporal spread to select the most
    representative frames. Good for very long videos where a compact
    overview is needed.

    Kwargs:
        num_frames: Number of frames in the summary (default 12).
        use_scene_detection: Try scene detection first (default True).
        max_width: Frame resize width in pixels (default 1024).
        mode: fast | accurate.
        generate_model: --generate.model CLI flag.
    """

    name = "summary"
    kind = "video"

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        from mm.video import VideoReader, pyav_runnable

        if not pyav_runnable():
            yield to_message([{"type": "text", "text": f"[PyAV not runnable for {path.name}]"}])
            return

        num_frames: int = kwargs.get("num_frames", 12)
        use_scene_detection: bool = kwargs.get("use_scene_detection", True)
        max_width: int = kwargs.get("max_width", 1024)
        generate_model = kwargs.get("generate_model", None)

        provider: str = resolve_provider(generate_model)

        with VideoReader(path) as reader:
            video_duration = reader.duration
            if video_duration <= 0:
                yield to_message(
                    [{"type": "text", "text": f"[Cannot determine duration for {path.name}]"}]
                )
                return

            timestamps = _select_summary_timestamps(
                path, video_duration, num_frames, use_scene_detection
            )

            logger.debug(
                "video_summary [path=%s, duration=%.1fs, frames=%d, scene_detect=%s]",
                path.name,
                video_duration,
                len(timestamps),
                use_scene_detection,
            )

            frames = reader.frames(timestamps, width=max_width).collect()

            if not frames:
                yield to_message(
                    [{"type": "text", "text": f"[No frames extracted from {path.name}]"}]
                )
                return

            mins, secs = divmod(video_duration, 60)
            parts: list[dict[str, Any]] = [
                {
                    "type": "text",
                    "text": (
                        f"Video summary of {path.name} "
                        f"({int(mins)}m{secs:.0f}s, {len(frames)} frames):"
                    ),
                }
            ]

            for frame in frames:
                parts.append({"type": "text", "text": f"[{frame.timestamp:.1f}s]"})
                b64, mime = frame.encode_jpeg()
                parts.append(_image_part(b64, mime, provider))

            yield to_message(parts)


class VideoSummaryWithTranscript(Encoder):
    """Adaptive video summary with Whisper transcript prepended.

    Kwargs: Same as ``VideoSummary`` plus ``model``, ``language``, ``audio_speed``.
    """

    name = "summary-w-transcript"
    kind = "video"

    _visual = VideoSummary()

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        yield from encode_with_transcript(path, self._visual.encode, **kwargs)


register(VideoSummary())
register(VideoSummaryWithTranscript())
