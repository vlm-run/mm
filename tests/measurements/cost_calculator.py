#!/usr/bin/env python3
"""Token cost calculator for long-form media processing.

Estimates token usage and cost for:
- 1 hour of video
- 1 hour of audio
- 100-page PDF

Usage:
    python -m tests.measurements.cost_calculator
    python tests/measurements/cost_calculator.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass

# ── Token estimation constants ────────────────────────────────────

# Image/video frame tokens (OpenAI tile-based model)
TOKENS_PER_IMAGE_BASE = 85
TOKENS_PER_TILE = 170
TILE_PX = 512

# Audio tokens (whisper-style models)
TOKENS_PER_AUDIO_SECOND = 25

# PDF/text tokens
TOKENS_PER_CHAR = 0.75
CHARS_PER_PAGE = 3000  # average text-heavy page

# Video keyframe extraction rates
KEYFRAME_FPS_FAST = 0.5  # 1 keyframe every 2 seconds
KEYFRAME_FPS_DEFAULT = 1.0  # 1 keyframe per second
KEYFRAME_FPS_ACCURATE = 2.0  # 2 keyframes per second

# Common video resolutions for frame token estimation
VIDEO_RESOLUTIONS = {
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "4K": (3840, 2160),
}

# ── Provider pricing ($/Mtok input) ──────────────────────────────

PROVIDERS = {
    "claude-haiku": {"name": "Claude 4.5 Haiku", "input": 0.80, "output": 4.00},
    "gpt-4o-mini": {"name": "GPT-4o Mini", "input": 0.15, "output": 0.60},
    "gemini-flash": {"name": "Gemini 2.5 Flash", "input": 0.15, "output": 0.60},
    "qwen-vl-72b": {"name": "Qwen3-VL 72B", "input": 0.40, "output": 0.40},
}


# ── Core estimation functions ────────────────────────────────────


@dataclass
class TokenEstimate:
    """Token and cost estimate for a media asset."""

    media_type: str
    variant: str
    duration_s: float = 0.0
    pages: int = 0
    resolution: str = ""
    keyframe_fps: float = 0.0
    tokens: int = 0
    cost_per_provider: dict[str, float] | None = None

    @property
    def tokens_per_second(self) -> float:
        return self.tokens / self.duration_s if self.duration_s > 0 else 0

    @property
    def tokens_per_page(self) -> float:
        return self.tokens / self.pages if self.pages > 0 else 0

    @property
    def tokens_per_hour(self) -> float:
        if self.duration_s > 0:
            return self.tokens * (3600 / self.duration_s)
        return 0


def _image_tokens(width: int, height: int) -> int:
    tiles_w = max(1, -(-width // TILE_PX))
    tiles_h = max(1, -(-height // TILE_PX))
    return TOKENS_PER_IMAGE_BASE + tiles_w * tiles_h * TOKENS_PER_TILE


def estimate_video_1hr(
    resolution: str = "1080p",
    keyframe_fps: float = KEYFRAME_FPS_DEFAULT,
) -> TokenEstimate:
    """Estimate tokens for 1 hour of video."""
    duration_s = 3600.0
    w, h = VIDEO_RESOLUTIONS[resolution]
    tokens_per_frame = _image_tokens(w, h)
    num_keyframes = int(duration_s * keyframe_fps)
    total_tokens = num_keyframes * tokens_per_frame

    costs = {pid: total_tokens * p["input"] / 1_000_000 for pid, p in PROVIDERS.items()}

    return TokenEstimate(
        media_type="video",
        variant=f"1hr_{resolution}_{keyframe_fps}kf",
        duration_s=duration_s,
        resolution=resolution,
        keyframe_fps=keyframe_fps,
        tokens=total_tokens,
        cost_per_provider=costs,
    )


def estimate_audio_1hr() -> TokenEstimate:
    """Estimate tokens for 1 hour of audio."""
    duration_s = 3600.0
    total_tokens = int(duration_s * TOKENS_PER_AUDIO_SECOND)

    costs = {pid: total_tokens * p["input"] / 1_000_000 for pid, p in PROVIDERS.items()}

    return TokenEstimate(
        media_type="audio",
        variant="1hr",
        duration_s=duration_s,
        tokens=total_tokens,
        cost_per_provider=costs,
    )


def estimate_pdf_100pages(chars_per_page: int = CHARS_PER_PAGE) -> TokenEstimate:
    """Estimate tokens for a 100-page PDF."""
    pages = 100
    total_chars = chars_per_page * pages
    total_tokens = int(total_chars * TOKENS_PER_CHAR)

    costs = {pid: total_tokens * p["input"] / 1_000_000 for pid, p in PROVIDERS.items()}

    return TokenEstimate(
        media_type="pdf",
        variant="100pages",
        pages=pages,
        tokens=total_tokens,
        cost_per_provider=costs,
    )


def run_all_estimates() -> list[TokenEstimate]:
    """Run all cost estimates and return results."""
    estimates: list[TokenEstimate] = []

    # Video: 1hr at different resolutions and keyframe rates
    for res in ["720p", "1080p", "4K"]:
        for kf in [KEYFRAME_FPS_FAST, KEYFRAME_FPS_DEFAULT, KEYFRAME_FPS_ACCURATE]:
            estimates.append(estimate_video_1hr(res, kf))

    # Audio: 1hr
    estimates.append(estimate_audio_1hr())

    # PDF: 100 pages
    estimates.append(estimate_pdf_100pages())

    return estimates


# ── Display ──────────────────────────────────────────────────────


def print_report(estimates: list[TokenEstimate]) -> None:
    """Print a formatted cost report."""
    try:
        from rich import box
        from rich.console import Console
        from rich.table import Table

        console = Console()

        # ── Video table ──
        video_table = Table(
            title="Video (1 hour) — Token & Cost Estimates",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold white",
        )
        video_table.add_column("Resolution", style="bold")
        video_table.add_column("KF/s", justify="right")
        video_table.add_column("Keyframes", justify="right")
        video_table.add_column("Tokens", justify="right", style="cyan")
        video_table.add_column("$/hr", justify="right")
        for pid, p in PROVIDERS.items():
            video_table.add_column(p["name"], justify="right")

        for e in estimates:
            if e.media_type != "video":
                continue
            row = [
                e.resolution,
                f"{e.keyframe_fps}",
                f"{int(e.duration_s * e.keyframe_fps):,}",
                f"{e.tokens:,}",
                "",
            ]
            for pid in PROVIDERS:
                cost = e.cost_per_provider[pid]
                row.append(f"${cost:.4f}" if cost < 1 else f"${cost:.2f}")
            video_table.add_row(*row)

        console.print(video_table)
        console.print()

        # ── Audio table ──
        audio_est = [e for e in estimates if e.media_type == "audio"][0]
        audio_table = Table(
            title="Audio (1 hour) — Token & Cost Estimates",
            box=box.ROUNDED,
        )
        audio_table.add_column("Provider", style="bold")
        audio_table.add_column("Tokens", justify="right", style="cyan")
        audio_table.add_column("$/hr", justify="right", style="green")

        for pid, p in PROVIDERS.items():
            cost = audio_est.cost_per_provider[pid]
            audio_table.add_row(
                p["name"],
                f"{audio_est.tokens:,}",
                f"${cost:.4f}" if cost < 1 else f"${cost:.2f}",
            )
        console.print(audio_table)
        console.print()

        # ── PDF table ──
        pdf_est = [e for e in estimates if e.media_type == "pdf"][0]
        pdf_table = Table(
            title="PDF (100 pages) — Token & Cost Estimates",
            box=box.ROUNDED,
        )
        pdf_table.add_column("Provider", style="bold")
        pdf_table.add_column("Tokens", justify="right", style="cyan")
        pdf_table.add_column("Tok/page", justify="right")
        pdf_table.add_column("$/100pg", justify="right", style="green")
        pdf_table.add_column("$/page", justify="right")

        for pid, p in PROVIDERS.items():
            cost = pdf_est.cost_per_provider[pid]
            pdf_table.add_row(
                p["name"],
                f"{pdf_est.tokens:,}",
                f"{pdf_est.tokens_per_page:,.0f}",
                f"${cost:.6f}" if cost < 0.01 else f"${cost:.4f}",
                f"${cost / 100:.8f}" if cost / 100 < 0.0001 else f"${cost / 100:.6f}",
            )
        console.print(pdf_table)

    except ImportError:
        # Fallback: plain text
        print("=" * 80)
        print("TOKEN & COST ESTIMATES")
        print("=" * 80)
        for e in estimates:
            print(f"\n{e.media_type.upper()} — {e.variant}")
            print(f"  Tokens: {e.tokens:,}")
            if e.cost_per_provider:
                for pid, cost in e.cost_per_provider.items():
                    print(f"  {PROVIDERS[pid]['name']}: ${cost:.6f}")


def export_json(estimates: list[TokenEstimate]) -> str:
    """Export estimates as JSON for the metrics webapp."""
    data = []
    for e in estimates:
        d = {
            "media_type": e.media_type,
            "variant": e.variant,
            "tokens": e.tokens,
            "duration_s": e.duration_s,
            "pages": e.pages,
            "resolution": e.resolution,
            "keyframe_fps": e.keyframe_fps,
        }
        if e.cost_per_provider:
            d["costs"] = {
                pid: {"name": PROVIDERS[pid]["name"], "cost": round(cost, 8)}
                for pid, cost in e.cost_per_provider.items()
            }
        data.append(d)
    return json.dumps({"estimates": data, "providers": PROVIDERS}, indent=2)


if __name__ == "__main__":
    estimates = run_all_estimates()

    if "--json" in sys.argv:
        print(export_json(estimates))
    else:
        print_report(estimates)
