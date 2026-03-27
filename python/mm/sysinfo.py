"""System capability detection for mm.

Detects available hardware (GPU, CUDA) and optional dependencies
(faster-whisper, scenedetect, docling) for reproducible benchmark
reporting and adaptive strategy selection.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class SystemInfo:
    """System capabilities snapshot."""

    ffmpeg_version: str = ""
    ffmpeg_available: bool = False
    gpu_name: str = ""
    gpu_vram_mb: int = 0
    cuda_available: bool = False
    whisper_available: bool = False
    scenedetect_available: bool = False
    docling_available: bool = False


def collect() -> SystemInfo:
    """Collect system capabilities. Non-blocking, never raises."""
    info = SystemInfo()

    # ffmpeg
    if shutil.which("ffmpeg"):
        info.ffmpeg_available = True
        info.ffmpeg_version = _ffmpeg_version()

    # GPU via nvidia-smi
    gpu_name, vram = _detect_gpu()
    info.gpu_name = gpu_name
    info.gpu_vram_mb = vram
    info.cuda_available = bool(gpu_name)

    # Optional Python deps
    try:
        from mm.whisper import whisper_available

        info.whisper_available = whisper_available()
    except Exception:
        pass

    try:
        from mm.scenes import scenedetect_available

        info.scenedetect_available = scenedetect_available()
    except Exception:
        pass

    try:
        from mm.docling_extract import docling_available

        info.docling_available = docling_available()
    except Exception:
        pass

    return info


def _ffmpeg_version() -> str:
    """Get ffmpeg version string."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        first_line = result.stdout.split("\n")[0]
        # "ffmpeg version 6.1.1 ..." → "6.1.1"
        parts = first_line.split()
        for i, p in enumerate(parts):
            if p == "version" and i + 1 < len(parts):
                return parts[i + 1]
        return first_line.strip()
    except Exception:
        return ""


def _detect_gpu() -> tuple[str, int]:
    """Detect GPU via nvidia-smi. Returns (name, vram_mb)."""
    if not shutil.which("nvidia-smi"):
        return "", 0
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        line = result.stdout.strip().split("\n")[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            return parts[0], int(float(parts[1]))
        return parts[0] if parts else "", 0
    except Exception:
        return "", 0
