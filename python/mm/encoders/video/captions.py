"""Embedded subtitle/caption extraction encoder.

Extracts subtitle tracks (SRT/VTT/SSA) from video files via PyAV
stream inspection.  Falls back to Whisper transcription when no
subtitle streams are found.

Subtitle text extraction still uses ffmpeg CLI (stream copy is
faster than re-encoding through PyAV for subtitle streams).
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable

from mm.encoders import register
from mm.encoders.base import Encoder, Message
from mm.encoders.image import _to_message

logger = logging.getLogger(__name__)


def _extract_subtitles(path: Path, stream_index: int = 0) -> str | None:
    """Extract a subtitle stream as SRT text via ffmpeg CLI.

    Kept as subprocess because ffmpeg stream-copy is the most reliable
    method for subtitle format conversion.
    """
    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tmp:
        out_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "quiet",
                "-y",
                "-i",
                str(path),
                "-map",
                f"0:s:{stream_index}",
                "-c:s",
                "srt",
                str(out_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return None
        text = out_path.read_text(errors="replace").strip()
        return text if text else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    finally:
        out_path.unlink(missing_ok=True)


def _parse_srt(srt_text: str) -> list[tuple[str, str]]:
    """Parse SRT into (timestamp_range, text) pairs."""
    blocks = re.split(r"\n\n+", srt_text.strip())
    results: list[tuple[str, str]] = []
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        timestamp = lines[1].strip()
        text = " ".join(line.strip() for line in lines[2:])
        if text:
            results.append((timestamp, text))
    return results


class VideoCaptions(Encoder):
    """Extract embedded subtitles from video files.

    Probes the video for subtitle streams via PyAV (no ffprobe
    subprocess) and extracts the first (or specified) stream as
    timestamped text.  Falls back to Whisper transcription when
    no subtitles are found.

    Kwargs:
        subtitle_stream: Which subtitle stream index to use (default 0).
        fallback_to_whisper: Use Whisper if no subtitles found (default True).
        model: Transcription model name for fallback (default chosen by backend).
        language: Language code or "auto" for fallback (default "auto").
        audio_speed: Playback speed for fallback (default 1.0).
    """

    name = "captions"
    kind = "video"
    generate = {"fast": None, "accurate": None}

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        from mm.video import probe_subtitle_streams

        subtitle_stream: int = kwargs.get("subtitle_stream", 0)
        fallback_to_whisper: bool = kwargs.get("fallback_to_whisper", True)
        streams = probe_subtitle_streams(path)

        if streams:
            srt_text = _extract_subtitles(path, stream_index=subtitle_stream)
            if srt_text:
                entries = _parse_srt(srt_text)
                if entries:
                    lines = [f"[{ts}] {text}" for ts, text in entries]
                    text = (
                        f"Embedded captions from {path.name} "
                        f"({len(entries)} entries):\n\n" + "\n".join(lines)
                    )
                    yield _to_message([{"type": "text", "text": text}])
                    return

        if fallback_to_whisper:
            logger.debug(
                "video_captions: no subtitle streams in %s, falling back to Whisper",
                path.name,
            )
            from mm.encoders.video._transcript import transcript_messages

            model: str | None = kwargs.get("audio_model") or kwargs.get("model")
            language: str = kwargs.get("language", "auto")
            audio_speed: float = kwargs.get("audio_speed", 1.0)

            msgs = list(
                transcript_messages(
                    path,
                    model=model,
                    language=language,
                    audio_speed=audio_speed,
                    backend=kwargs.get("audio_backend") or kwargs.get("backend"),
                    base_url=kwargs.get("audio_base_url") or kwargs.get("base_url"),
                    api_key=kwargs.get("audio_api_key") or kwargs.get("api_key"),
                )
            )
            if msgs:
                yield from msgs
                return

        yield _to_message(
            [{"type": "text", "text": f"[No captions or transcript available for {path.name}]"}]
        )


register(VideoCaptions())
