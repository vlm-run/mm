"""Adaptive visual summary encoder.

Selects a fixed budget of representative frames from a video using
scene detection (when available) or uniform temporal spread.  Unlike
``video-shots`` which returns ALL shots, this targets a compact
fixed-size output suitable for long videos.
"""

from __future__ import annotations

import base64
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable

from mm.encoders import Message, _resolve_provider, register
from mm.encoders.image import _image_part, _to_message
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
        try:
            from mm.common.video.shot_detection import (
                detect_scenes,
                scenedetect_available,
            )

            if scenedetect_available():
                result = detect_scenes(path)
                if result.scenes and len(result.scenes) > 1:
                    midpoints = [(s + e) / 2 for s, e in result.scenes]
                    if len(midpoints) <= num_frames:
                        return midpoints
                    step = len(midpoints) / num_frames
                    return [midpoints[int(i * step)] for i in range(num_frames)]
        except ImportError:
            pass

    if num_frames <= 1:
        return [duration / 2]
    step = duration / (num_frames + 1)
    return [step * (i + 1) for i in range(num_frames)]


class VideoSummary:
    """Adaptive N-frame visual summary of a video.

    Combines scene detection with temporal spread to select the most
    representative frames.  Good for very long videos where a compact
    overview is needed.

    Kwargs:
        num_frames: Number of frames in the summary (default 12).
        use_scene_detection: Try scene detection first (default True).
        max_width: Frame resize width in pixels (default 1024).
    """

    name: str = "video-summary"
    media_types: tuple[str, ...] = ("video",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        num_frames: int = kwargs.get("num_frames", 12)
        use_scene_detection: bool = kwargs.get("use_scene_detection", True)
        max_width: int = kwargs.get("max_width", 1024)
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

        timestamps = _select_summary_timestamps(path, duration, num_frames, use_scene_detection)

        logger.debug(
            "video_summary [path=%s, duration=%.1fs, frames=%d, scene_detect=%s]",
            path.name,
            duration,
            len(timestamps),
            use_scene_detection,
        )

        out_dir = Path(tempfile.mkdtemp(prefix="mm_summary_"))
        try:
            frame_paths = extract_frames_at_timestamps(
                path,
                timestamps,
                thumb_width=max_width,
                out_dir=out_dir,
            )

            if not frame_paths:
                yield _to_message(
                    [{"type": "text", "text": f"[No frames extracted from {path.name}]"}]
                )
                return

            mins, secs = divmod(duration, 60)
            parts: list[dict[str, Any]] = [
                {
                    "type": "text",
                    "text": (
                        f"Video summary of {path.name} "
                        f"({int(mins)}m{secs:.0f}s, {len(frame_paths)} frames):"
                    ),
                }
            ]

            for idx, fp in enumerate(frame_paths):
                ts = timestamps[idx] if idx < len(timestamps) else 0.0
                b64 = base64.b64encode(fp.read_bytes()).decode()
                parts.append({"type": "text", "text": f"[{ts:.1f}s]"})
                parts.append(_image_part(b64, "image/jpeg", provider))

            yield _to_message(parts)
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)


class VideoSummaryWithTranscript:
    """Adaptive video summary with Whisper transcript prepended.

    Kwargs: Same as ``VideoSummary`` plus ``whisper_model``,
    ``language``, ``audio_speed``.
    """

    name: str = "video-summary-w-transcript"
    media_types: tuple[str, ...] = ("video",)

    _visual = VideoSummary()

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        yield from encode_with_transcript(path, self._visual.encode, **kwargs)


register(VideoSummary())
register(VideoSummaryWithTranscript())
