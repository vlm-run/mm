"""I-frame (keyframe) extraction encoder.

Extracts only I-frames from the video bitstream via ffprobe, which
represent natural visual boundaries in the compressed stream.  More
efficient than uniform sampling for capturing scene changes.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Iterable

from mm.encoders import Message, _resolve_provider, register
from mm.encoders.image import _image_part, _to_message
from mm.encoders.video import _read_frames_b64
from mm.encoders.video._transcript import encode_with_transcript

logger = logging.getLogger(__name__)


def _probe_keyframe_timestamps(path: Path, max_frames: int | None = None) -> list[float]:
    """Use ffprobe to find I-frame timestamps in the video."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-select_streams",
                "v:0",
                "-show_entries",
                "frame=pict_type,pts_time",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return []

        data = json.loads(result.stdout)
        frames = data.get("frames", [])

        timestamps: list[float] = []
        for frame in frames:
            if frame.get("pict_type") == "I":
                pts = frame.get("pts_time")
                if pts is not None:
                    timestamps.append(float(pts))

        if max_frames and len(timestamps) > max_frames:
            step = len(timestamps) / max_frames
            timestamps = [timestamps[int(i * step)] for i in range(max_frames)]

        return timestamps
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError, ValueError):
        return []


class VideoKeyframes:
    """Extract I-frames (keyframes) from the video bitstream.

    Uses ffprobe to identify I-frames then extracts them via ffmpeg.
    Much more efficient than uniform sampling since I-frames represent
    natural visual boundaries in the encoded stream.

    Kwargs:
        max_frames: Cap the number of keyframes (default None = all).
        max_width: Frame resize width in pixels (default 1024).
        max_frames_per_message: Frames per Message batch (default 16).
    """

    name: str = "video-keyframes"
    media_types: tuple[str, ...] = ("video",)

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        max_frames: int | None = kwargs.get("max_frames", None)
        max_width: int = kwargs.get("max_width", 1024)
        max_frames_per_message: int = kwargs.get("max_frames_per_message", 16)
        provider: str = _resolve_provider()

        from mm.ffmpeg import extract_frames_at_timestamps, ffmpeg_available

        if not ffmpeg_available():
            yield _to_message([{"type": "text", "text": f"[ffmpeg not available for {path.name}]"}])
            return

        timestamps = _probe_keyframe_timestamps(path, max_frames=max_frames)
        if not timestamps:
            yield _to_message([{"type": "text", "text": f"[No keyframes found in {path.name}]"}])
            return

        logger.debug(
            "video_keyframes [path=%s, keyframes=%d]",
            path.name,
            len(timestamps),
        )

        frame_paths: list[Path] = extract_frames_at_timestamps(
            path,
            timestamps,
            thumb_width=max_width,
        )

        if not frame_paths:
            yield _to_message(
                [{"type": "text", "text": f"[No keyframes extracted from {path.name}]"}]
            )
            return

        try:
            for i in range(0, len(frame_paths), max_frames_per_message):
                batch = frame_paths[i : i + max_frames_per_message]
                t_start = timestamps[i] if i < len(timestamps) else 0.0
                t_end_idx = min(i + max_frames_per_message, len(timestamps)) - 1
                t_end = timestamps[t_end_idx] if timestamps else 0.0

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
                for b64 in _read_frames_b64(batch):
                    parts.append(_image_part(b64, "image/jpeg", provider))

                yield _to_message(parts)
        finally:
            for fp in frame_paths:
                try:
                    fp.unlink(missing_ok=True)
                except OSError:
                    pass


class VideoKeyframesWithTranscript:
    """Extract I-frames with Whisper transcript prepended.

    Kwargs: Same as ``VideoKeyframes`` plus ``whisper_model``,
    ``language``, ``audio_speed``.
    """

    name: str = "video-keyframes-w-transcript"
    media_types: tuple[str, ...] = ("video",)

    _visual = VideoKeyframes()

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        yield from encode_with_transcript(path, self._visual.encode, **kwargs)


register(VideoKeyframes())
register(VideoKeyframesWithTranscript())
