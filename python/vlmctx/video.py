"""Video metadata extraction via ffprobe (part of ffmpeg)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class VideoMeta:
    """Metadata extracted from a video file via ffprobe."""
    width: int | None = None
    height: int | None = None
    duration_s: float | None = None
    fps: float | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    has_audio: bool = False
    bitrate: int | None = None
    frame_count: int | None = None
    rotation: int | None = None
    pixel_format: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


def ffprobe_available() -> bool:
    """Check if ffprobe is on the PATH."""
    try:
        subprocess.run(
            ["ffprobe", "-version"],
            capture_output=True,
            timeout=5,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def extract_video_metadata(path: str | Path) -> VideoMeta:
    """Extract video metadata using ffprobe JSON output.

    Returns a VideoMeta with whatever fields could be parsed;
    never raises on malformed probe output.
    """
    path = Path(path)
    meta = VideoMeta()

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return meta
        probe = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return meta

    streams = probe.get("streams", [])
    fmt = probe.get("format", {})

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    meta.has_audio = audio_stream is not None
    if audio_stream:
        meta.audio_codec = audio_stream.get("codec_name")

    if video_stream:
        meta.width = _int(video_stream.get("width"))
        meta.height = _int(video_stream.get("height"))
        meta.video_codec = video_stream.get("codec_name")
        meta.pixel_format = video_stream.get("pix_fmt")

        # Duration: prefer stream, fallback to format
        dur = video_stream.get("duration") or fmt.get("duration")
        meta.duration_s = _float(dur)

        # FPS from r_frame_rate (e.g. "30000/1001")
        rfr = video_stream.get("r_frame_rate", "")
        meta.fps = _parse_fraction(rfr)

        # Frame count
        meta.frame_count = _int(video_stream.get("nb_frames"))

        # Rotation from side_data or tags
        for sd in video_stream.get("side_data_list", []):
            if "rotation" in sd:
                meta.rotation = _int(sd["rotation"])
                break
        if meta.rotation is None:
            meta.rotation = _int(video_stream.get("tags", {}).get("rotate"))

    # Bitrate
    meta.bitrate = _int(fmt.get("bit_rate"))

    # Format-level tags (title, encoder, creation_time, etc.)
    meta.tags = {k: str(v) for k, v in fmt.get("tags", {}).items()}

    return meta


def _int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_fraction(s: str) -> float | None:
    """Parse ffprobe fraction like '30000/1001' -> 29.97."""
    if "/" in s:
        parts = s.split("/")
        try:
            num, den = float(parts[0]), float(parts[1])
            return round(num / den, 3) if den != 0 else None
        except (ValueError, IndexError):
            return None
    return _float(s)
