"""ffmpeg pipelines for video mosaic extraction and audio processing.

Strategies:
- uniform: Parallel seek + thumbnail blur rejection. O(N) in desired frames,
  independent of video length. ~100ms/frame → 48 frames in ~0.6s for any video.
- keyframe: I-frame only extraction. ~5000x realtime but non-uniform spacing.
- scene: Scene-change detection. Full decode but semantically meaningful frames.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path


def ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@dataclass
class MosaicResult:
    """Result of mosaic extraction."""

    mosaic_paths: list[Path]
    frame_count: int
    tile_cols: int
    tile_rows: int
    thumb_width: int
    duration_s: float = 0.0
    strategy: str = "uniform"
    elapsed_ms: float = 0.0
    timestamps: list[float] = field(default_factory=list)


@dataclass
class AudioResult:
    """Result of audio extraction."""

    path: Path
    duration_s: float
    speed: float
    sample_rate: int
    channels: int


def probe_duration(video_path: str | Path) -> float:
    """Get video duration in seconds via ffprobe. Fast container-level read."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def extract_uniform_mosaics(
    video_path: str | Path,
    *,
    out_dir: str | Path | None = None,
    tile_cols: int = 6,
    tile_rows: int = 8,
    thumb_width: int = 160,
    num_mosaics: int = 1,
    quality: int = 3,
    blur_window: int = 10,
    max_workers: int = 8,
) -> MosaicResult:
    """Uniform temporal sampling with per-frame blur rejection.

    For each desired frame position, seeks directly to that timestamp (O(1)
    container seek) and uses ffmpeg's thumbnail filter on a small window to
    select the sharpest nearby frame. Blur rejection at zero extra cost.

    Performance: ~100ms per frame via parallel seeking.
    48 frames (1 mosaic) in ~0.6s for ANY video length.
    384 frames (8 mosaics) in ~5s.
    """
    import time

    t0 = time.monotonic()

    video_path = Path(video_path)
    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="vlmctx_um_"))
    else:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

    num_mosaics = max(1, min(num_mosaics, 8))
    duration = probe_duration(video_path)
    if duration <= 0:
        return MosaicResult(
            mosaic_paths=[],
            frame_count=0,
            tile_cols=tile_cols,
            tile_rows=tile_rows,
            thumb_width=thumb_width,
            strategy="uniform",
        )

    frames_per_mosaic = tile_cols * tile_rows
    total_frames = frames_per_mosaic * num_mosaics
    interval = duration / total_frames

    timestamps = [(i + 0.5) * interval for i in range(total_frames)]

    frame_dir = Path(tempfile.mkdtemp(prefix="vlmctx_fr_"))

    def _seek_extract(args: tuple[int, float]) -> Path:
        idx, ts = args
        frame_path = frame_dir / f"frame_{idx:04d}.jpg"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{ts:.3f}",
                "-i",
                str(video_path),
                "-vf",
                f"thumbnail={blur_window},scale={thumb_width}:-1",
                "-frames:v",
                "1",
                "-q:v",
                str(quality),
                "-update",
                "1",
                str(frame_path),
            ],
            capture_output=True,
            timeout=30,
        )
        return frame_path

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(_seek_extract, enumerate(timestamps)))

    extracted = sorted(frame_dir.glob("frame_*.jpg"))
    if not extracted:
        shutil.rmtree(frame_dir, ignore_errors=True)
        return MosaicResult(
            mosaic_paths=[],
            frame_count=0,
            tile_cols=tile_cols,
            tile_rows=tile_rows,
            thumb_width=thumb_width,
            strategy="uniform",
        )

    # Tile extracted frames into mosaic grids
    stem = video_path.stem
    out_pattern = str(out_dir / f"{stem}_mosaic_%d.jpg")

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-start_number",
            "0",
            "-i",
            str(frame_dir / "frame_%04d.jpg"),
            "-vf",
            f"tile={tile_cols}x{tile_rows}",
            "-q:v",
            str(quality),
            out_pattern,
        ],
        capture_output=True,
        timeout=60,
    )

    shutil.rmtree(frame_dir, ignore_errors=True)

    mosaic_paths = sorted(out_dir.glob(f"{stem}_mosaic_*.jpg"))
    elapsed = (time.monotonic() - t0) * 1000

    return MosaicResult(
        mosaic_paths=mosaic_paths,
        frame_count=len(extracted),
        tile_cols=tile_cols,
        tile_rows=tile_rows,
        thumb_width=thumb_width,
        duration_s=duration,
        strategy="uniform",
        elapsed_ms=elapsed,
        timestamps=timestamps,
    )


def extract_keyframe_mosaics(
    video_path: str | Path,
    *,
    out_dir: str | Path | None = None,
    tile_cols: int = 6,
    tile_rows: int = 8,
    thumb_width: int = 160,
    max_mosaics: int = 1,
    quality: int = 3,
) -> MosaicResult:
    """I-frame only mosaic extraction. Fastest strategy but non-uniform spacing.

    Only decodes keyframes (skip_frame nokey), ~5000x realtime.
    """
    video_path = Path(video_path)
    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="vlmctx_kf_"))
    else:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

    stem = video_path.stem
    out_pattern = str(out_dir / f"{stem}_mosaic_%d.jpg")

    cmd = [
        "ffmpeg",
        "-y",
        "-skip_frame",
        "nokey",
        "-i",
        str(video_path),
        "-vsync",
        "vfr",
        "-vf",
        f"scale={thumb_width}:-1,tile={tile_cols}x{tile_rows}",
        "-frames:v",
        str(max_mosaics),
        "-q:v",
        str(quality),
        out_pattern,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    mosaic_paths = sorted(out_dir.glob(f"{stem}_mosaic_*.jpg"))
    kf_count = _parse_frame_count(result.stderr)

    return MosaicResult(
        mosaic_paths=mosaic_paths,
        frame_count=kf_count,
        tile_cols=tile_cols,
        tile_rows=tile_rows,
        thumb_width=thumb_width,
        strategy="keyframe",
    )


def extract_scene_mosaics(
    video_path: str | Path,
    *,
    out_dir: str | Path | None = None,
    threshold: float = 0.3,
    tile_cols: int = 6,
    tile_rows: int = 8,
    thumb_width: int = 160,
    max_mosaics: int = 1,
    quality: int = 3,
) -> MosaicResult:
    """Scene-change based mosaic extraction.

    Decodes all frames and selects those exceeding the scene change threshold.
    Slower than keyframe-only but produces semantically better frames.
    """
    video_path = Path(video_path)
    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="vlmctx_sc_"))
    else:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

    stem = video_path.stem
    out_pattern = str(out_dir / f"{stem}_scene_%d.jpg")

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"select='gt(scene\\,{threshold})',scale={thumb_width}:-1,tile={tile_cols}x{tile_rows}",
        "-vsync",
        "vfr",
        "-frames:v",
        str(max_mosaics),
        "-q:v",
        str(quality),
        out_pattern,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    mosaic_paths = sorted(out_dir.glob(f"{stem}_scene_*.jpg"))
    kf_count = _parse_frame_count(result.stderr)

    return MosaicResult(
        mosaic_paths=mosaic_paths,
        frame_count=kf_count,
        tile_cols=tile_cols,
        tile_rows=tile_rows,
        thumb_width=thumb_width,
        strategy="scene",
    )


def extract_audio(
    video_path: str | Path,
    *,
    out_path: str | Path | None = None,
    speed: float = 2.0,
    sample_rate: int = 16000,
    mono: bool = True,
    fmt: str = "wav",
) -> AudioResult:
    """Extract audio at Nx speed, downmixed to mono 16kHz for Whisper.

    At 2x speed, a 163s video produces 2.5MB WAV in ~0.2s (514x realtime).
    """
    video_path = Path(video_path)
    if out_path is None:
        suffix = f".{fmt}"
        fd, tmp = tempfile.mkstemp(prefix="vlmctx_audio_", suffix=suffix)
        os.close(fd)
        out_path = Path(tmp)
    else:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

    af_filters = []
    if speed != 1.0:
        if speed <= 2.0:
            af_filters.append(f"atempo={speed}")
        else:
            # atempo only supports 0.5-2.0, chain them
            remaining = speed
            while remaining > 2.0:
                af_filters.append("atempo=2.0")
                remaining /= 2.0
            if remaining > 1.0:
                af_filters.append(f"atempo={remaining:.4f}")

    channels = "1" if mono else "2"

    codec_map = {"wav": "pcm_s16le", "mp3": "libmp3lame", "flac": "flac"}
    codec = codec_map.get(fmt, "pcm_s16le")

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        channels,
        "-ar",
        str(sample_rate),
        "-c:a",
        codec,
    ]
    if af_filters:
        cmd += ["-af", ",".join(af_filters)]
    cmd.append(str(out_path))

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    duration = _parse_duration(result.stderr)

    return AudioResult(
        path=out_path,
        duration_s=duration / speed if duration > 0 else 0,
        speed=speed,
        sample_rate=sample_rate,
        channels=1 if mono else 2,
    )


def _parse_frame_count(stderr: str) -> int:
    """Parse 'frame=  NNN' from ffmpeg stderr."""
    for line in reversed(stderr.splitlines()):
        if "frame=" in line:
            for part in line.split():
                if part.startswith("frame="):
                    try:
                        return int(part.split("=")[1])
                    except (ValueError, IndexError):
                        pass
                # Also handle "frame=   NNN" with spaces
            parts = line.split("frame=")
            if len(parts) > 1:
                num = parts[-1].strip().split()[0]
                try:
                    return int(num)
                except ValueError:
                    pass
    return 0


def _parse_duration(stderr: str) -> float:
    """Parse 'Duration: HH:MM:SS.ms' from ffmpeg stderr."""
    for line in stderr.splitlines():
        if "Duration:" in line:
            parts = line.split("Duration:")[1].strip().split(",")[0].strip()
            try:
                h, m, s = parts.split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
            except (ValueError, IndexError):
                pass
    return 0.0
