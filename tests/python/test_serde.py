"""Tests for mm.encoders message serialization strategies."""

from __future__ import annotations

import base64
import json
import struct
import zlib
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_png(path: Path, w: int, h: int) -> Path:
    """Create a minimal valid PNG file."""
    png_sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)

    # Minimal IDAT with empty scanlines
    raw_data = b""
    for _ in range(h):
        raw_data += b"\x00" + b"\x00" * (w * 3)  # filter byte + RGB
    compressed = zlib.compress(raw_data)
    idat_crc = zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF
    idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc)

    iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)

    path.write_bytes(png_sig + ihdr + idat + iend)
    return path


def _make_jpeg(path: Path, w: int, h: int) -> Path:
    """Create a valid JPEG via Pillow."""
    from PIL import Image

    img = Image.new("RGB", (w, h), color=(128, 64, 32))
    img.save(path, "JPEG", quality=80)
    return path


@pytest.fixture
def serde_images(tmp_path: Path) -> dict[str, Path]:
    """Create test images at various sizes."""
    return {
        "small_png": _make_png(tmp_path / "small.png", 100, 80),
        "medium_png": _make_png(tmp_path / "medium.png", 1000, 800),
        "large_png": _make_png(tmp_path / "large.png", 3000, 2000),
        "small_jpg": _make_jpeg(tmp_path / "small.jpg", 100, 80),
        "medium_jpg": _make_jpeg(tmp_path / "medium.jpg", 1000, 800),
        "large_jpg": _make_jpeg(tmp_path / "large.jpg", 3000, 2000),
    }


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_builtin_strategies_registered(self):
        from mm.encoders import list_strategies

        names = list_strategies()
        assert "resize" in names
        assert "tile" in names
        # ``video-frames`` and ``video-chunks`` are the current PyAV-based
        # equivalents of the retired ``frame-sample`` / ``video-chunk``.
        assert "video-frames" in names
        assert "video-chunks" in names
        assert "rasterize" in names
        assert "rasterize-text" in names
        assert "video-gemini" in names
        assert "video-gemini-chunked" in names
        assert "document-gemini" in names
        assert len(names) >= 9

    def test_list_strategies_by_image(self):
        from mm.encoders import list_strategies

        names = list_strategies(media_type="image")
        assert "resize" in names
        assert "tile" in names
        # No video-only encoders should leak into the image namespace.
        assert "video-frames" not in names

    def test_list_strategies_by_video(self):
        from mm.encoders import list_strategies

        names = list_strategies(media_type="video")
        assert "video-frames" in names
        assert "video-chunks" in names
        assert "video-gemini" in names
        assert "resize" not in names

    def test_list_strategies_by_document(self):
        from mm.encoders import list_strategies

        names = list_strategies(media_type="document")
        assert "rasterize" in names
        assert "rasterize-text" in names
        assert "document-gemini" in names
        assert "resize" not in names

    def test_get_unknown_strategy_raises(self):
        from mm.encoders import get

        with pytest.raises(KeyError, match="Unknown encoder"):
            get("nonexistent_strategy_xyz")

    def test_strategy_decorator(self):
        from mm.encoders import _REGISTRY, strategy

        @strategy(name="test-decorator-xyz", media_types=("image",))
        def test_decorator_xyz(path, **kw):
            yield {"role": "user", "content": []}

        assert "test-decorator-xyz" in _REGISTRY
        assert _REGISTRY["test-decorator-xyz"].media_types == ("image",)

    def test_strategy_decorator_auto_name(self):
        """@strategy without name= should derive name from function name."""
        from mm.encoders import _REGISTRY, strategy

        @strategy(media_types=("image",))
        def my_auto_named_strat(path, **kw):
            yield {"role": "user", "content": []}

        assert "my-auto-named-strat" in _REGISTRY


# ---------------------------------------------------------------------------
# Image strategy tests
# ---------------------------------------------------------------------------


class TestImageResize:
    def test_output_format(self, serde_images):
        from mm.encoders import get

        strat = get("resize")
        messages = list(strat.encode(serde_images["small_jpg"]))
        assert len(messages) == 1
        msg = messages[0]
        assert msg["role"] == "user"
        assert isinstance(msg["content"], list)
        assert len(msg["content"]) >= 1
        part = msg["content"][0]
        assert part["type"] == "image_url"
        url = part["image_url"]["url"]
        assert url.startswith("data:image/")
        assert ";base64," in url

    def test_resize_small_no_upscale(self, serde_images):
        """Images smaller than max_width should not be upscaled."""
        from mm.encoders import get

        strat = get("resize")
        messages = list(strat.encode(serde_images["small_png"], max_width=1024))
        msg = messages[0]
        # Decode and check dimensions
        url = msg["content"][0]["image_url"]["url"]
        b64_data = url.split(";base64,")[1]
        img_bytes = base64.b64decode(b64_data)
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(img_bytes))
        assert img.size[0] == 100  # Not upscaled

    def test_resize_large_respects_max_width(self, serde_images):
        from mm.encoders import get

        strat = get("resize")
        messages = list(strat.encode(serde_images["large_jpg"], max_width=512))
        msg = messages[0]
        url = msg["content"][0]["image_url"]["url"]
        b64_data = url.split(";base64,")[1]
        img_bytes = base64.b64decode(b64_data)
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(img_bytes))
        assert img.size[0] <= 512

    def test_resize_preserves_aspect_ratio(self, serde_images):
        from mm.encoders import get

        strat = get("resize")
        messages = list(strat.encode(serde_images["large_jpg"], max_width=1024))
        msg = messages[0]
        url = msg["content"][0]["image_url"]["url"]
        b64_data = url.split(";base64,")[1]
        img_bytes = base64.b64decode(b64_data)
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(img_bytes))
        w, h = img.size
        # Original: 3000x2000, ratio ~1.5
        ratio = w / h
        assert abs(ratio - 1.5) < 0.1

    def test_resize_tall_image_respects_max_height(self, tmp_path):
        """A tall image (H > max_width) should be downscaled by height."""
        tall = _make_jpeg(tmp_path / "tall.jpg", 500, 3000)
        from mm.encoders import get

        strat = get("resize")
        messages = list(strat.encode(tall, max_width=1024))
        msg = messages[0]
        url = msg["content"][0]["image_url"]["url"]
        b64_data = url.split(";base64,")[1]
        img_bytes = base64.b64decode(b64_data)
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(img_bytes))
        w, h = img.size
        assert w <= 1024
        assert h <= 1024
        # Aspect ratio: 500/3000 ≈ 0.167
        assert abs(w / h - 500 / 3000) < 0.05


class TestImageTile:
    def test_small_image_single_tile(self, serde_images):
        """Image smaller than max_width yields a single message with overview only."""
        from mm.encoders import get

        strat = get("tile")
        messages = list(strat.encode(serde_images["small_jpg"], max_width=1024))
        assert len(messages) == 1
        content = messages[0]["content"]
        image_parts = [p for p in content if p.get("type") == "image_url" or "inline_data" in p]
        assert len(image_parts) == 1

    def test_large_image_overview_plus_tiles(self, serde_images):
        """Large image yields one message with overview + tiles."""
        from mm.encoders import get

        strat = get("tile")
        messages = list(strat.encode(serde_images["large_jpg"], max_width=1024))
        assert len(messages) == 1
        content = messages[0]["content"]
        image_parts = [p for p in content if p.get("type") == "image_url" or "inline_data" in p]
        # 3000/1024 = 3 cols, 2000/1024 = 2 rows -> 6 tiles + 1 overview = 7
        assert len(image_parts) == 7

    def test_tile_medium_image(self, serde_images):
        from mm.encoders import get

        strat = get("tile")
        messages = list(strat.encode(serde_images["medium_jpg"], max_width=512))
        assert len(messages) == 1
        content = messages[0]["content"]
        image_parts = [p for p in content if p.get("type") == "image_url" or "inline_data" in p]
        # 1000/512 = 2 cols, 800/512 = 2 rows -> 4 tiles + 1 overview = 5
        assert len(image_parts) == 5


# ---------------------------------------------------------------------------
# Rust vs Pillow parity
# ---------------------------------------------------------------------------


class TestRustParity:
    def test_resize_rust_available(self):
        """Verify the Rust resize_image function is importable."""
        from mm._mm import resize_image

        assert callable(resize_image)

    def test_resize_rust_output(self, serde_images):
        from mm._mm import resize_image

        result = resize_image(str(serde_images["large_jpg"]), 1024)
        assert "base64" in result
        assert "mime" in result
        assert "width" in result
        assert "height" in result
        assert result["width"] <= 1024
        assert result["mime"] in ("image/jpeg", "image/png")

    def test_tile_rust_available(self):
        from mm._mm import tile_image

        assert callable(tile_image)

    def test_tile_rust_output(self, serde_images):
        from mm._mm import tile_image

        tiles = tile_image(str(serde_images["large_jpg"]), 1024)
        assert len(tiles) == 6  # 3000/1024=3 cols, 2000/1024=2 rows
        for tile in tiles:
            assert "base64" in tile
            assert "col" in tile
            assert "row" in tile
            assert "total_cols" in tile

    def test_gemini_image_part(self, serde_images):
        from mm._mm import gemini_image_part

        json_str = gemini_image_part(str(serde_images["small_jpg"]))
        part = json.loads(json_str)
        assert "inline_data" in part
        assert part["inline_data"]["mime_type"] == "image/jpeg"


# ---------------------------------------------------------------------------
# Benchmark tests
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestSerdeBenchmarks:
    """Serde strategy benchmarks."""

    def test_bench_image_resize_small(self, benchmark, serde_images):
        """Benchmark: resize 100x80 JPEG."""
        from mm.encoders import get

        strat = get("resize")
        benchmark(lambda: list(strat.encode(serde_images["small_jpg"], max_width=1024)))

    def test_bench_image_resize_medium(self, benchmark, serde_images):
        """Benchmark: resize 1000x800 JPEG."""
        from mm.encoders import get

        strat = get("resize")
        benchmark(lambda: list(strat.encode(serde_images["medium_jpg"], max_width=1024)))

    def test_bench_image_resize_large(self, benchmark, serde_images):
        """Benchmark: resize 3000x2000 JPEG."""
        from mm.encoders import get

        strat = get("resize")
        benchmark(lambda: list(strat.encode(serde_images["large_jpg"], max_width=1024)))

    def test_bench_image_tile_large(self, benchmark, serde_images):
        """Benchmark: tile 3000x2000 JPEG into 1024x1024 tiles."""
        from mm.encoders import get

        strat = get("tile")
        benchmark(lambda: list(strat.encode(serde_images["large_jpg"], max_width=1024)))

    def test_bench_rust_resize(self, benchmark, serde_images):
        """Benchmark: Rust resize_image directly."""
        from mm._mm import resize_image

        benchmark(lambda: resize_image(str(serde_images["large_jpg"]), 1024))

    def test_bench_rust_tile(self, benchmark, serde_images):
        """Benchmark: Rust tile_image directly."""
        from mm._mm import tile_image

        benchmark(lambda: tile_image(str(serde_images["large_jpg"]), 1024))

    def test_bench_rust_gemini_part(self, benchmark, serde_images):
        """Benchmark: Rust gemini_image_part."""
        from mm._mm import gemini_image_part

        benchmark(lambda: gemini_image_part(str(serde_images["medium_jpg"])))

    def test_bench_pillow_resize(self, benchmark, serde_images):
        """Benchmark: Pillow fallback resize."""
        from mm.encoders.image import _pillow_resize

        benchmark(lambda: _pillow_resize(serde_images["large_jpg"], 1024))

    def test_bench_pillow_tile(self, benchmark, serde_images):
        """Benchmark: Pillow fallback tile."""
        from mm.encoders.image import _pillow_tile

        benchmark(lambda: _pillow_tile(serde_images["large_jpg"], 1024))
