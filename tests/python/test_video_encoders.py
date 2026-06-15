"""Tests for mm.encoders.video helpers.

Covers Frame.encode_jpeg() (the replacement for the old _read_frames_b64
helper) and encoder registration verification.
"""

from __future__ import annotations

import base64
import io

from mm.video import Frame
from PIL import Image


class TestFrameEncodeJpeg:
    """Test Frame.encode_jpeg() — the new in-memory equivalent."""

    def test_basic_roundtrip(self):
        img = Image.new("RGB", (200, 100), (128, 64, 32))
        frame = Frame(timestamp=5.0, image=img)
        b64, mime = frame.encode_jpeg()
        assert mime == "image/jpeg"
        decoded = Image.open(io.BytesIO(base64.b64decode(b64)))
        assert decoded.size == (200, 100)

    def test_rgba_auto_converts(self):
        img = Image.new("RGBA", (50, 50), (255, 0, 0, 128))
        frame = Frame(timestamp=0.0, image=img)
        b64, mime = frame.encode_jpeg()
        assert mime == "image/jpeg"
        decoded = Image.open(io.BytesIO(base64.b64decode(b64)))
        assert decoded.mode == "RGB"

    def test_small_image(self):
        img = Image.new("RGB", (1, 1), (0, 0, 0))
        frame = Frame(timestamp=0.0, image=img)
        b64, mime = frame.encode_jpeg()
        assert len(b64) > 0

    def test_quality_affects_size(self):
        img = Image.new("RGB", (500, 500), (100, 150, 200))
        frame = Frame(timestamp=0.0, image=img)
        b64_low, _ = frame.encode_jpeg(quality=10)
        b64_high, _ = frame.encode_jpeg(quality=95)
        assert len(b64_high) > len(b64_low)


class TestEncoderRegistration:
    """Verify all video encoders are correctly registered."""

    def test_all_video_encoders_registered(self):
        from mm.encoders import get

        expected = [
            "frames",
            "frames-w-transcript",
            "mosaic",
            "mosaic-w-transcript",
            "shots",
            "shots-w-transcript",
            "shot-mosaic",
            "shot-mosaic-w-transcript",
            "clips",
            "clips-w-transcript",
            "chunks",
            "keyframes",
            "keyframes-w-transcript",
            "summary",
            "summary-w-transcript",
            "captions",
            "transcript",
        ]
        for name in expected:
            enc = get(name, "video")
            assert enc is not None, f"Encoder {name!r} not registered"
            assert hasattr(enc, "encode"), f"Encoder {name!r} has no encode method"
