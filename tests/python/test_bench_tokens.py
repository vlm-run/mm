"""Token count benchmarks for different media types.

Measures estimated token counts for:
- Single image (various resolutions)
- 1 minute of video
- 1 minute of audio
- 10 pages of PDF
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Token estimation helpers
# ---------------------------------------------------------------------------

# OpenAI/Anthropic token estimation rules (approximate):
# - Image: base 85 tokens + 170 tokens per 512x512 tile
# - Video: ~600 tokens per frame (keyframes extracted)
# - Audio: ~25 tokens/second (whisper-style)
# - PDF text: ~0.75 tokens per character (~4 chars/token)

TOKENS_PER_IMAGE_BASE = 85
TOKENS_PER_IMAGE_TILE = 170
TILE_SIZE = 512

TOKENS_PER_AUDIO_SECOND = 25
TOKENS_PER_VIDEO_KEYFRAME = 600
TOKENS_PER_PDF_CHAR = 0.75


def estimate_image_tokens(width: int, height: int) -> int:
    """Estimate tokens for an image based on OpenAI's tile-based counting."""
    tiles_w = max(1, -(-width // TILE_SIZE))  # ceil division
    tiles_h = max(1, -(-height // TILE_SIZE))
    return TOKENS_PER_IMAGE_BASE + (tiles_w * tiles_h * TOKENS_PER_IMAGE_TILE)


def estimate_audio_tokens(duration_s: float) -> int:
    """Estimate tokens for audio content."""
    return int(duration_s * TOKENS_PER_AUDIO_SECOND)


def estimate_video_tokens(duration_s: float, fps: float = 1.0) -> int:
    """Estimate tokens for video (keyframe-based extraction)."""
    # Typically 1 keyframe/sec or scene-change detection
    num_keyframes = max(1, int(duration_s * fps))
    return num_keyframes * TOKENS_PER_VIDEO_KEYFRAME


def estimate_pdf_tokens(text: str) -> int:
    """Estimate tokens from extracted PDF text."""
    return int(len(text) * TOKENS_PER_PDF_CHAR)


# ---------------------------------------------------------------------------
# Image token benchmarks
# ---------------------------------------------------------------------------


RESOLUTIONS = [
    ("SD_640x480", 640, 480),
    ("HD_1280x720", 1280, 720),
    ("FHD_1920x1080", 1920, 1080),
    ("4K_3840x2160", 3840, 2160),
]


@pytest.mark.parametrize("name,width,height", RESOLUTIONS)
def test_token_count_image(name, width, height):
    """Report estimated token count for images at various resolutions."""
    tokens = estimate_image_tokens(width, height)
    cost_per_mtok_input = 3.0  # $/Mtok (Claude Sonnet range)
    cost = tokens * cost_per_mtok_input / 1_000_000

    print(f"\n  {name}: {width}x{height}")
    print(f"    Tiles: {-(-width // TILE_SIZE)}x{-(-height // TILE_SIZE)}")
    print(f"    Estimated tokens: {tokens:,}")
    print(f"    Cost @ $3/Mtok: ${cost:.6f}")
    assert tokens > 0


# ---------------------------------------------------------------------------
# Audio token benchmarks (1 minute)
# ---------------------------------------------------------------------------


def test_token_count_audio_1min():
    """Report estimated token count for 1 minute of audio."""
    duration_s = 60.0
    tokens = estimate_audio_tokens(duration_s)
    cost_per_mtok = 3.0
    cost = tokens * cost_per_mtok / 1_000_000

    print(f"\n  Audio (1 min = {duration_s}s)")
    print(f"    Estimated tokens: {tokens:,}")
    print(f"    Tokens/second: {TOKENS_PER_AUDIO_SECOND}")
    print(f"    Cost @ $3/Mtok: ${cost:.6f}")
    assert tokens == 1500


# ---------------------------------------------------------------------------
# Video token benchmarks (1 minute)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("keyframe_fps", [0.5, 1.0, 2.0])
def test_token_count_video_1min(keyframe_fps):
    """Report estimated token count for 1 minute of video at various keyframe rates."""
    duration_s = 60.0
    tokens = estimate_video_tokens(duration_s, fps=keyframe_fps)
    cost_per_mtok = 3.0
    cost = tokens * cost_per_mtok / 1_000_000

    print(f"\n  Video (1 min, keyframe_fps={keyframe_fps})")
    print(f"    Keyframes: {int(duration_s * keyframe_fps)}")
    print(f"    Estimated tokens: {tokens:,}")
    print(f"    Cost @ $3/Mtok: ${cost:.6f}")
    assert tokens > 0


# ---------------------------------------------------------------------------
# PDF token benchmarks (10 pages)
# ---------------------------------------------------------------------------


def test_token_count_pdf_10pages():
    """Report estimated token count for 10-page PDF (~3000 chars/page)."""
    chars_per_page = 3000
    pages = 10
    total_chars = chars_per_page * pages
    tokens = estimate_pdf_tokens("x" * total_chars)
    cost_per_mtok = 3.0
    cost = tokens * cost_per_mtok / 1_000_000

    print(f"\n  PDF (10 pages, ~{chars_per_page} chars/page)")
    print(f"    Total characters: {total_chars:,}")
    print(f"    Estimated tokens: {tokens:,}")
    print(f"    Tokens/page: {tokens // pages:,}")
    print(f"    Cost @ $3/Mtok: ${cost:.6f}")
    assert tokens > 0


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------


def test_token_summary_table():
    """Print a summary table of token estimates across all media types."""
    rows = []

    # Images
    for name, w, h in RESOLUTIONS:
        tokens = estimate_image_tokens(w, h)
        rows.append({"type": "image", "variant": name, "tokens": tokens})

    # Audio 1min
    rows.append({"type": "audio", "variant": "1min", "tokens": estimate_audio_tokens(60)})

    # Video 1min at 1 kf/s
    rows.append(
        {"type": "video", "variant": "1min@1kf/s", "tokens": estimate_video_tokens(60, 1.0)}
    )

    # PDF 10 pages
    rows.append({"type": "pdf", "variant": "10pages", "tokens": estimate_pdf_tokens("x" * 30000)})

    cost_rates = [1.0, 3.0, 15.0]  # $/Mtok: Haiku, Sonnet, Opus range
    print("\n  Token Count Summary")
    print(
        f"  {'Type':<10} {'Variant':<20} {'Tokens':>10}  "
        + "  ".join(f"${'@' + str(r) + '/Mt':>8}" for r in cost_rates)
    )
    print("  " + "-" * 80)

    for row in rows:
        costs = [f"${row['tokens'] * r / 1_000_000:.6f}" for r in cost_rates]
        print(
            f"  {row['type']:<10} {row['variant']:<20} {row['tokens']:>10,}  {'  '.join(f'{c:>10}' for c in costs)}"
        )
