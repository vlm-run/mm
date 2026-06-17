"""Tests for mm.encoders.video registration.

Verifies all video encoders are correctly registered and resolve via get().

Frame.encode_jpeg() coverage lives in test_video_reader.py (TestFrame) and
test_video_p0.py (TestJpegSubsampling).
"""

from __future__ import annotations


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
