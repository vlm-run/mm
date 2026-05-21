"""Correctness tests for the P0 video-encoder performance changes.

Each section corresponds to one P0 item from
``benchmark/260429-rebased-video-encoders-perf-plan.md``:

- P0 #1 — ``Frame.reformat`` resize hot path (mm.video._resize_to_pil)
- P0 #2 — JPEG default subsampling 4:2:0 (Frame.encode_jpeg)
- P0 #3 — Streaming mosaic + bundled per-shot decode
  (mm.encoders.video.mosaic, shots)
- P0 #4 — Process-local LRU caches for probe / detect_scenes / transcript
- P0 #5 — Concurrent Whisper + visual extraction (encode_with_transcript)

Tests that need real video data require ``~/data/mmbench-tiny/bakery.mp4``
and are skipped automatically when it is missing.
"""

from __future__ import annotations

import base64
import io
import time
from pathlib import Path

import pytest
from mm.common.video.shot_detection import (
    SceneResult,
    detect_scenes,
)
from mm.encoders.video._transcript import encode_with_transcript, transcript_messages
from mm.video import Frame, VideoInfo, _resize_to_pil, probe
from PIL import Image

BAKERY = Path.home() / "data" / "mmbench-tiny" / "bakery.mp4"
requires_bakery = pytest.mark.skipif(
    not BAKERY.exists(),
    reason="bakery.mp4 not found at ~/data/mmbench-tiny/",
)

# Every memoize_file-wrapped function exposes the same handle surface.
# Iterating over them keeps test setup/teardown a one-liner.
_CACHED = (probe, detect_scenes, transcript_messages)


@pytest.fixture(autouse=True)
def _isolate_caches():
    """Clear every memoize_file cache before/after each test for determinism."""
    for fn in _CACHED:
        fn.cache_clear()
    yield
    for fn in _CACHED:
        fn.cache_clear()


class TestJpegSubsampling:
    """P0 #2 — JPEG defaults to 4:2:0; explicit 4:4:4 still works."""

    def test_default_is_smaller_than_full_chroma(self):
        # A horizontally-striped image with high-frequency chroma exposes
        # subsampling differences clearly.
        img = Image.new("RGB", (256, 256))
        for y in range(256):
            for x in range(256):
                img.putpixel((x, y), (255 if x % 2 == 0 else 0, 0, 255 if y % 2 == 0 else 0))
        frame = Frame(timestamp=0.0, image=img)

        b64_default, _ = frame.encode_jpeg()
        b64_full, _ = frame.encode_jpeg(subsampling=0)

        assert len(b64_default) < len(b64_full), (
            "4:2:0 (default) should produce smaller bytes than 4:4:4"
        )

    def test_default_payload_is_decodable(self):
        img = Image.new("RGB", (320, 180), (123, 45, 67))
        frame = Frame(timestamp=2.0, image=img)
        b64, mime = frame.encode_jpeg()

        decoded = Image.open(io.BytesIO(base64.b64decode(b64)))
        assert mime == "image/jpeg"
        assert decoded.size == (320, 180)
        assert decoded.mode == "RGB"

    def test_default_subsampling_matches_constant(self):
        # Locking in the chosen subsampling factor — bumping it from 4:2:0
        # to anything else needs a deliberate code change *and* this test.
        from mm.video import _JPEG_SUBSAMPLING

        assert _JPEG_SUBSAMPLING == 2  # 0=4:4:4, 1=4:2:2, 2=4:2:0

    def test_quality_still_affects_size(self):
        img = Image.new("RGB", (400, 300), (200, 100, 50))
        frame = Frame(timestamp=0.0, image=img)
        b64_low, _ = frame.encode_jpeg(quality=10)
        b64_high, _ = frame.encode_jpeg(quality=95)
        assert len(b64_high) > len(b64_low)


class TestResizeToPil:
    """P0 #1 — ``_resize_to_pil`` uses ``frame.reformat`` when downscaling."""

    def test_no_resize_when_width_none(self):
        av = pytest.importorskip("av")
        frame = av.VideoFrame.from_ndarray(_solid_rgb(640, 360, (10, 20, 30)), format="rgb24")
        img = _resize_to_pil(frame, None)
        assert img.size == (640, 360)
        assert img.mode == "RGB"

    def test_no_resize_when_target_larger(self):
        av = pytest.importorskip("av")
        frame = av.VideoFrame.from_ndarray(_solid_rgb(320, 180, (50, 60, 70)), format="rgb24")
        img = _resize_to_pil(frame, 1280)  # asks for upscale → leave alone
        assert img.size == (320, 180)

    def test_resize_preserves_aspect(self):
        av = pytest.importorskip("av")
        frame = av.VideoFrame.from_ndarray(_solid_rgb(1280, 720, (200, 100, 50)), format="rgb24")
        img = _resize_to_pil(frame, 640)
        # 1280×720 → 640×360 (height = round(720 * 640 / 1280))
        assert img.size == (640, 360)
        assert img.mode == "RGB"

    def test_resize_visual_close_to_pil(self):
        """Reformat output should be visually close to PIL resize.

        Compares mean per-channel RGB delta on a synthetic gradient image.
        Tolerance is generous (libswscale uses bilinear by default vs PIL
        LANCZOS) but proves we're not getting random noise back.
        """
        av = pytest.importorskip("av")
        # Horizontal gradient — easy reference, easy to compare.
        import numpy as np

        arr = np.zeros((360, 640, 3), dtype=np.uint8)
        arr[:, :, 0] = np.linspace(0, 255, 640, dtype=np.uint8)
        frame = av.VideoFrame.from_ndarray(arr, format="rgb24")

        # PyAV reformat path (production path).
        out_av = _resize_to_pil(frame, 320)
        # Reference PIL path.
        ref = Image.fromarray(arr).resize((320, 180), Image.LANCZOS)

        out_arr = np.asarray(out_av, dtype=np.int16)
        ref_arr = np.asarray(ref, dtype=np.int16)
        mean_delta = float(np.abs(out_arr - ref_arr).mean())

        assert out_av.size == ref.size == (320, 180)
        assert mean_delta < 5.0, f"reformat vs PIL resize mean Δ={mean_delta:.2f}"


def _solid_rgb(w: int, h: int, color: tuple[int, int, int]):
    """Build an HxWx3 uint8 ndarray for an av.VideoFrame.from_ndarray call."""
    import numpy as np

    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:] = color
    return arr


@requires_bakery
class TestProbeCache:
    """P0 #4 — ``probe()`` is cached per (path, mtime, size)."""

    def test_returns_video_info(self):
        info = probe(BAKERY)
        assert isinstance(info, VideoInfo)
        assert info.duration > 250

    def test_same_path_returns_same_object(self):
        a = probe(BAKERY)
        b = probe(BAKERY)
        assert a is b, "second call must return the cached instance"

    def test_path_str_and_path_equivalent(self):
        a = probe(BAKERY)
        b = probe(str(BAKERY))
        assert a is b, "Path and str should hash to the same cache key"

    def test_clear_cache_drops_entries(self):
        probe(BAKERY)
        assert probe.cache_info()["currsize"] >= 1
        probe.cache_clear()
        info = probe.cache_info()
        assert info["currsize"] == 0
        assert info["hits"] == 0
        assert info["misses"] == 0

    def test_cache_info_tracks_hits_and_misses(self):
        probe(BAKERY)
        probe(BAKERY)
        probe(BAKERY)
        info = probe.cache_info()
        assert info["misses"] == 1
        assert info["hits"] == 2
        assert info["currsize"] == 1

    def test_mtime_change_invalidates(self, tmp_path):
        # Use a small temp video (or skip if unable to create one).
        av = pytest.importorskip("av")
        clip = tmp_path / "tiny.mp4"
        _write_minimal_mp4(av, clip, frames=8)

        a = probe(clip)
        # Touch the file with a future mtime — same content, new fingerprint.
        future = clip.stat().st_mtime + 100.0
        import os

        os.utime(clip, (future, future))

        b = probe(clip)
        assert a is not b, "mtime change should bypass the cache"

    def test_nonexistent_falls_through(self):
        # Should raise (no caching of failures) — and not poison the cache.
        with pytest.raises(Exception):
            probe("/no/such/video.mp4")
        assert probe.cache_info()["currsize"] == 0


def _write_minimal_mp4(av_module, dest: Path, frames: int = 8) -> None:
    """Create a tiny ``frames``-frame mp4 for cache invalidation tests."""
    import numpy as np

    container = av_module.open(str(dest), mode="w")
    try:
        stream = container.add_stream("h264", rate=24)
        stream.width = 64
        stream.height = 64
        stream.pix_fmt = "yuv420p"
        for i in range(frames):
            arr = np.full((64, 64, 3), (i * 30) % 255, dtype=np.uint8)
            frame = av_module.VideoFrame.from_ndarray(arr, format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    finally:
        container.close()


@requires_bakery
class TestSceneDetectCache:
    """P0 #4 — ``detect_scenes()`` is cached per (path, mtime, size, threshold, min_scene_len)."""

    def test_same_params_returns_equal_value(self):
        # ``detect_scenes`` is disk-backed, so the second call unpickles a
        # fresh object — identity (``is``) no longer holds, but value
        # equality and the cache_info hit-counter do.
        detect_scenes.cache_clear()
        a = detect_scenes(BAKERY, threshold=27.0, min_scene_len=15)
        b = detect_scenes(BAKERY, threshold=27.0, min_scene_len=15)
        assert isinstance(a, SceneResult)
        assert a == b
        assert detect_scenes.cache_info()["hits"] >= 1

    def test_warm_call_is_much_faster(self):
        # First (cold) call dominates; second (warm) call should be free.
        detect_scenes.cache_clear()
        t0 = time.monotonic()
        detect_scenes(BAKERY, threshold=27.0, min_scene_len=15)
        cold = time.monotonic() - t0

        t0 = time.monotonic()
        detect_scenes(BAKERY, threshold=27.0, min_scene_len=15)
        warm = time.monotonic() - t0

        assert warm < cold * 0.05, f"warm ({warm:.3f}s) should be ≪ cold ({cold:.3f}s)"

    def test_different_threshold_misses_cache(self):
        a = detect_scenes(BAKERY, threshold=27.0, min_scene_len=15)
        b = detect_scenes(BAKERY, threshold=15.0, min_scene_len=15)
        # Different thresholds → distinct cache entries → almost
        # certainly different scene boundaries (and never the same
        # pickled blob, even if they happened to coincide).
        assert isinstance(a, SceneResult)
        assert isinstance(b, SceneResult)
        assert detect_scenes.cache_info()["currsize"] >= 2

    def test_clear_cache_drops_entries(self):
        detect_scenes(BAKERY, threshold=27.0, min_scene_len=15)
        assert detect_scenes.cache_info()["currsize"] >= 1
        detect_scenes.cache_clear()
        assert detect_scenes.cache_info()["currsize"] == 0


class TestTranscriptCache:
    """P0 #4 — Transcript helper caches via ``@memoize_file`` on the public
    ``transcript_messages`` function.

    The decorator's behaviour itself is exercised in ``test_cache.py``;
    these tests verify the integration: that ``transcript_messages`` exposes
    the standard ``cache_info`` / ``cache_clear`` handles and that its
    cache key includes ``model``.
    """

    def test_exposes_cache_handles(self):
        # Public surface contract — every memoize_file-wrapped function gets these.
        assert callable(transcript_messages.cache_clear)
        assert callable(transcript_messages.cache_info)

    @staticmethod
    def _stub_whisper(monkeypatch, *, available: bool = False) -> None:
        """Make the transcript body terminate early without touching Whisper.

        The body short-circuits on ``whisper_available() == False`` and returns
        ``[]`` — that's the cleanest way to keep tests fast while still
        exercising the real cached function (not a monkeypatched shim).
        """
        monkeypatch.setattr("mm.common.audio.transcribe_available", lambda: available)

    def test_cache_hit_on_repeated_call(self, tmp_path, monkeypatch):
        self._stub_whisper(monkeypatch)
        clip = tmp_path / "fake.mp4"
        clip.write_bytes(b"\x00\x00\x00\x18ftypisom")

        a = transcript_messages(clip, model="tiny", language="auto", audio_speed=1.0)
        b = transcript_messages(clip, model="tiny", language="auto", audio_speed=1.0)

        info = transcript_messages.cache_info()
        assert info["hits"] >= 1
        assert info["misses"] == 1
        assert info["currsize"] == 1
        # Disk-backed cache rehydrates a fresh object — value equality
        # plus the hit counter is the contract callers can rely on.
        assert a == b == []

    def test_cache_key_includes_model(self, tmp_path, monkeypatch):
        self._stub_whisper(monkeypatch)
        clip = tmp_path / "fake2.mp4"
        clip.write_bytes(b"\x00\x00\x00\x18ftypisom")

        a = transcript_messages(clip, model="tiny", language="auto", audio_speed=1.0)
        b = transcript_messages(clip, model="medium", language="auto", audio_speed=1.0)
        # Different models → separate cache entries.
        assert transcript_messages.cache_info()["currsize"] == 2
        # Same call should hit, not grow.
        transcript_messages(clip, model="tiny", language="auto", audio_speed=1.0)
        assert transcript_messages.cache_info()["currsize"] == 2
        # Both empty because Whisper is stubbed unavailable.
        assert a == b == []

    def test_clear_cache_forces_rebuild(self, tmp_path, monkeypatch):
        self._stub_whisper(monkeypatch)
        clip = tmp_path / "fake3.mp4"
        clip.write_bytes(b"\x00\x00\x00\x18ftypisom")

        transcript_messages(clip, model="tiny", language="auto", audio_speed=1.0)
        assert transcript_messages.cache_info()["currsize"] == 1
        transcript_messages.cache_clear()
        assert transcript_messages.cache_info() == {
            "hits": 0,
            "misses": 0,
            "currsize": 0,
            "maxsize": 16,
        }

    def test_mtime_change_invalidates(self, tmp_path, monkeypatch):
        import os

        self._stub_whisper(monkeypatch)
        clip = tmp_path / "fake4.mp4"
        clip.write_bytes(b"\x00\x00\x00\x18ftypisom")

        transcript_messages(clip, model="tiny", language="auto", audio_speed=1.0)
        before = transcript_messages.cache_info()["currsize"]

        future = clip.stat().st_mtime + 100.0
        os.utime(clip, (future, future))

        transcript_messages(clip, model="tiny", language="auto", audio_speed=1.0)
        after = transcript_messages.cache_info()["currsize"]

        # New mtime → new cache entry, old one still present.
        assert after == before + 1


class TestEncodeWithTranscript:
    """P0 #5 — Whisper runs concurrently with the visual encoder.

    Visual encoder is faked with a sleep so we can detect concurrency
    without depending on Whisper being installed.  The transcript helper
    is monkey-patched at the module level so the wrapped (cached)
    callable is replaced wholesale.
    """

    def test_transcript_first_then_visual(self, tmp_path, monkeypatch):
        clip = tmp_path / "v.mp4"
        clip.write_bytes(b"\x00\x00\x00\x18ftypisom")

        monkeypatch.setattr(
            "mm.encoders.video._transcript.transcript_messages",
            lambda p, **kw: [{"role": "user", "content": [{"type": "text", "text": "TRANSCRIPT"}]}],
        )

        def fake_visual(path, **kwargs):
            yield {"role": "user", "content": [{"type": "text", "text": "V0"}]}
            yield {"role": "user", "content": [{"type": "text", "text": "V1"}]}

        msgs = list(encode_with_transcript(clip, fake_visual))
        texts = [m["content"][0]["text"] for m in msgs]
        assert texts == ["TRANSCRIPT", "V0", "V1"], (
            "transcript Message must be yielded first, then visual"
        )

    def test_runs_concurrently(self, tmp_path, monkeypatch):
        """Total wall time should be ≈ max(visual, transcript), not the sum."""
        clip = tmp_path / "v2.mp4"
        clip.write_bytes(b"\x00\x00\x00\x18ftypisom")

        def slow_transcript(p, **kw):
            time.sleep(0.30)
            return [{"role": "user", "content": [{"type": "text", "text": "T"}]}]

        def slow_visual(path, **kwargs):
            time.sleep(0.30)
            yield {"role": "user", "content": [{"type": "text", "text": "V"}]}

        monkeypatch.setattr(
            "mm.encoders.video._transcript.transcript_messages",
            slow_transcript,
        )

        t0 = time.monotonic()
        msgs = list(encode_with_transcript(clip, slow_visual))
        elapsed = time.monotonic() - t0

        # Sum would be 0.6s; concurrent should be near 0.3s.
        assert elapsed < 0.5, f"expected concurrent (<0.5s), got {elapsed:.2f}s"
        assert len(msgs) == 2

    def test_empty_transcript_still_yields_visual(self, tmp_path, monkeypatch):
        clip = tmp_path / "v3.mp4"
        clip.write_bytes(b"\x00\x00\x00\x18ftypisom")

        monkeypatch.setattr(
            "mm.encoders.video._transcript.transcript_messages",
            lambda p, **kw: [],
        )

        def fake_visual(path, **kwargs):
            yield {"role": "user", "content": [{"type": "text", "text": "V"}]}

        msgs = list(encode_with_transcript(clip, fake_visual))
        assert len(msgs) == 1
        assert msgs[0]["content"][0]["text"] == "V"


@requires_bakery
class TestStreamingMosaic:
    """P0 #3 — ``video-mosaic`` streams via ``.batched()`` instead of ``.collect()``.

    Verifies output remains identical (one Message containing N image parts).
    """

    def test_default_run_yields_one_message(self):
        from mm.encoders import get

        msgs = list(get("video-mosaic").encode(BAKERY))
        assert len(msgs) == 1
        parts = msgs[0]["content"]
        # 1 leading text part + N image parts.
        text_parts = [p for p in parts if p.get("type") == "text"]
        image_parts = [p for p in parts if p.get("type") == "image_url"]
        assert len(text_parts) == 1
        # Default config is 8 mosaics × (4×4 grid) = 8 images
        assert len(image_parts) >= 1
        assert all("data:image/jpeg;base64," in p["image_url"]["url"] for p in image_parts)

    def test_num_mosaics_kwarg_caps_emission(self):
        from mm.encoders import get

        msgs = list(get("video-mosaic").encode(BAKERY, num_mosaics=2))
        parts = msgs[0]["content"]
        image_parts = [p for p in parts if p.get("type") == "image_url"]
        assert len(image_parts) == 2

    def test_each_mosaic_image_is_decodable(self):
        from mm.encoders import get

        msgs = list(get("video-mosaic").encode(BAKERY, num_mosaics=1))
        parts = msgs[0]["content"]
        image_parts = [p for p in parts if p.get("type") == "image_url"]
        url = image_parts[0]["image_url"]["url"]
        b64 = url.split(",", 1)[1]
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        assert img.mode == "RGB"
        assert img.size[0] > 0 and img.size[1] > 0


@requires_bakery
class TestBundledShots:
    """P0 #3 — ``video-shots`` bundles all per-shot timestamps into one decode pass.

    Verifies one Message per shot with correctly-ordered frames inside each.
    """

    def test_one_message_per_shot(self):
        from mm.encoders import get

        msgs = list(get("video-shots").encode(BAKERY, max_frames_per_shot=2))
        scenes = detect_scenes(BAKERY, threshold=27.0, min_scene_len=15)
        # Some shots may be skipped if their range produces no decodable frames,
        # so we allow ≤ but flag if we drop more than ~5%.
        assert len(msgs) > 0
        assert len(msgs) <= scenes.num_scenes
        assert (scenes.num_scenes - len(msgs)) <= max(1, int(0.05 * scenes.num_scenes))

    def test_each_shot_has_text_then_images(self):
        from mm.encoders import get

        msgs = list(get("video-shots").encode(BAKERY, max_frames_per_shot=2))
        for m in msgs[:5]:
            parts = m["content"]
            assert parts[0]["type"] == "text"
            assert "Shot " in parts[0]["text"]
            for p in parts[1:]:
                assert p["type"] == "image_url"

    def test_shot_mosaic_produces_one_image_per_shot(self):
        from mm.encoders import get

        msgs = list(get("video-shot-mosaic").encode(BAKERY))
        for m in msgs[:5]:
            parts = m["content"]
            text_parts = [p for p in parts if p.get("type") == "text"]
            image_parts = [p for p in parts if p.get("type") == "image_url"]
            assert len(text_parts) == 1
            assert len(image_parts) == 1


@requires_bakery
class TestCacheCrossEncoderReuse:
    """End-to-end check that running multiple encoders against the same file
    populates and reuses the caches as expected (P0 #4 integration)."""

    def test_probe_and_scene_caches_shared_across_encoders(self):
        from mm.encoders import get

        list(get("video-mosaic").encode(BAKERY, num_mosaics=1))
        probe_after_mosaic = probe.cache_info()["currsize"]
        scene_after_mosaic = detect_scenes.cache_info()["currsize"]
        scene_misses_before = detect_scenes.cache_info()["misses"]

        # A second encoder against the same file must NOT add new entries —
        # both probe and scene-detect should hit the cache.
        list(get("video-shots").encode(BAKERY, max_frames_per_shot=1))

        assert probe.cache_info()["currsize"] == probe_after_mosaic
        assert detect_scenes.cache_info()["currsize"] == scene_after_mosaic
        # Scene-detect parameters are identical across the two encoders, so
        # no new misses should have happened.
        assert detect_scenes.cache_info()["misses"] == scene_misses_before
        assert probe_after_mosaic >= 1
        assert scene_after_mosaic >= 1
        assert probe.cache_info()["hits"] >= 1
