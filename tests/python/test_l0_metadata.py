"""Comprehensive tests for L0 metadata extraction.

Validates schema, column types, image dimension enrichment,
file kind classification, and SQL queryability of all L0 columns.
"""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pytest
from typer.testing import CliRunner

from vlmctx.cli import app
from vlmctx.context import Context

runner = CliRunner()


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def media_tree(tmp_path: Path) -> Path:
    """Directory with real images, fake video, code, documents, and configs."""
    # Real 1x1 PNG
    _write_png(tmp_path / "logo.png", 1, 1)

    # Real 2x3 PNG (different dimensions)
    _write_png(tmp_path / "banner.png", 2, 3)

    # Real 10x10 JPEG
    _write_jpeg(tmp_path / "photo.jpg", 10, 10)

    # Code files
    (tmp_path / "app.py").write_text("import os\nprint('hello world')\n")
    (tmp_path / "lib.rs").write_text("fn main() { println!(\"hello\"); }\n")
    (tmp_path / "index.js").write_text("console.log('hi');\n")

    # Config
    (tmp_path / "config.toml").write_text("[server]\nport = 3000\n")
    (tmp_path / "data.json").write_text('{"a": 1}\n')

    # Text / markdown
    (tmp_path / "readme.md").write_text("# Hello\n\nWorld.\n")
    (tmp_path / "notes.txt").write_text("Remember to test.\n")

    # Nested structure
    sub = tmp_path / "sub" / "deep"
    sub.mkdir(parents=True)
    _write_png(sub / "nested.png", 4, 5)
    (sub / "helper.py").write_text("def helper(): pass\n")

    # Fake video (just bytes, won't decode, but kind detection works)
    (tmp_path / "clip.mp4").write_bytes(b"\x00" * 200)

    return tmp_path


def _write_png(path: Path, width: int, height: int):
    """Create a valid PNG by constructing the binary format directly."""
    import struct
    import zlib

    raw = b""
    for _ in range(height):
        raw += b"\x00" + b"\x80\x00\x40" * width
    compressed = zlib.compress(raw)

    def _chunk(ctype, data):
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", ihdr_data)
    png += _chunk(b"IDAT", compressed)
    png += _chunk(b"IEND", b"")
    path.write_bytes(png)


def _write_jpeg(path: Path, width: int, height: int):
    """Create a valid JPEG."""
    try:
        from PIL import Image
        img = Image.new("RGB", (width, height), color=(64, 128, 0))
        img.save(str(path), format="JPEG")
    except ImportError:
        # Minimal JFIF stub — may not decode dimensions but tests kind detection
        path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 200 + b"\xff\xd9")


# ── L0 Schema Tests ──────────────────────────────────────────────────


class TestL0Schema:
    """Verify L0 Arrow schema: column names, types, nullability."""

    def test_schema_has_14_columns(self, media_tree: Path):
        ctx = Context(media_tree)
        table = ctx.to_arrow()
        assert table.num_columns == 14

    def test_required_columns_present(self, media_tree: Path):
        ctx = Context(media_tree)
        cols = ctx.to_arrow().column_names
        for name in [
            "path", "name", "stem", "ext", "size", "modified", "created",
            "mime", "kind", "is_binary", "depth", "parent", "width", "height",
        ]:
            assert name in cols, f"Missing column: {name}"

    def test_width_height_are_uint32(self, media_tree: Path):
        ctx = Context(media_tree)
        schema = ctx.to_arrow().schema
        assert schema.field("width").type == pa.uint32()
        assert schema.field("height").type == pa.uint32()

    def test_width_height_nullable(self, media_tree: Path):
        ctx = Context(media_tree)
        schema = ctx.to_arrow().schema
        assert schema.field("width").nullable
        assert schema.field("height").nullable

    def test_size_column_type(self, media_tree: Path):
        ctx = Context(media_tree)
        assert ctx.to_arrow().schema.field("size").type == pa.uint64()

    def test_depth_column_type(self, media_tree: Path):
        ctx = Context(media_tree)
        assert ctx.to_arrow().schema.field("depth").type == pa.uint16()


# ── Image Dimension Enrichment ────────────────────────────────────────


class TestImageDimensions:
    """Verify width/height populated for images, null for non-images."""

    def test_png_dimensions_populated(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        row = df.filter(df["name"] == "logo.png")
        assert row["width"][0] == 1
        assert row["height"][0] == 1

    def test_different_png_dimensions(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        row = df.filter(df["name"] == "banner.png")
        assert row["width"][0] == 2
        assert row["height"][0] == 3

    def test_jpeg_dimensions_populated(self, media_tree: Path):
        """JPEG dims depend on having Pillow to create valid test JPEGs."""
        ctx = Context(media_tree)
        df = ctx.to_polars()
        row = df.filter(df["name"] == "photo.jpg")
        try:
            import PIL  # noqa
            w, h = row["width"][0], row["height"][0]
            assert w is not None and w > 0
            assert h is not None and h > 0
        except ImportError:
            pass  # fallback JPEG stub may not have parseable dims

    def test_nested_image_dimensions(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        row = df.filter(df["name"] == "nested.png")
        assert row["width"][0] == 4
        assert row["height"][0] == 5

    def test_code_files_have_null_dimensions(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        code = df.filter(df["kind"] == "code")
        assert code["width"].null_count() == len(code)
        assert code["height"].null_count() == len(code)

    def test_config_files_have_null_dimensions(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        conf = df.filter(df["kind"] == "config")
        assert conf["width"].null_count() == len(conf)

    def test_text_files_have_null_dimensions(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        text = df.filter(df["kind"] == "text")
        assert text["width"].null_count() == len(text)

    def test_sql_query_with_dimensions(self, media_tree: Path):
        ctx = Context(media_tree)
        result = ctx.sql(
            "SELECT name, width, height, width*height as pixels "
            "FROM files WHERE width IS NOT NULL ORDER BY pixels DESC"
        )
        assert result.num_rows > 0
        names = [r.as_py() for r in result.column("name")]
        assert any("png" in n or "jpg" in n for n in names)

    def test_sql_avg_dimensions(self, media_tree: Path):
        ctx = Context(media_tree)
        result = ctx.sql(
            "SELECT AVG(width) as avg_w, AVG(height) as avg_h "
            "FROM files WHERE kind='image'"
        )
        assert result.num_rows == 1
        avg_w = result.column("avg_w")[0].as_py()
        assert avg_w is not None and avg_w > 0


# ── File Kind Classification ──────────────────────────────────────────


class TestFileKindClassification:

    def test_code_detection(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        py = df.filter(df["name"] == "app.py")
        assert py["kind"][0] == "code"
        rs = df.filter(df["name"] == "lib.rs")
        assert rs["kind"][0] == "code"
        js = df.filter(df["name"] == "index.js")
        assert js["kind"][0] == "code"

    def test_image_detection(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        for img in ["logo.png", "banner.png", "photo.jpg"]:
            row = df.filter(df["name"] == img)
            assert row["kind"][0] == "image", f"{img} not detected as image"

    def test_config_detection(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        assert df.filter(df["name"] == "config.toml")["kind"][0] == "config"

    def test_text_detection(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        assert df.filter(df["name"] == "readme.md")["kind"][0] == "text"
        assert df.filter(df["name"] == "notes.txt")["kind"][0] == "text"

    def test_video_detection(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        assert df.filter(df["name"] == "clip.mp4")["kind"][0] == "video"

    def test_data_detection(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        assert df.filter(df["name"] == "data.json")["kind"][0] == "data"

    def test_binary_flag_for_images(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        images = df.filter(df["kind"] == "image")
        assert all(v is True for v in images["is_binary"].to_list())

    def test_binary_flag_false_for_code(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        code = df.filter(df["kind"] == "code")
        assert all(v is False for v in code["is_binary"].to_list())


# ── Path / Depth / Parent ─────────────────────────────────────────────


class TestPathMetadata:

    def test_top_level_depth_zero(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        top = df.filter(df["name"] == "app.py")
        assert top["depth"][0] == 0

    def test_nested_depth(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        nested = df.filter(df["name"] == "nested.png")
        assert nested["depth"][0] == 2  # sub/deep/nested.png

    def test_parent_field(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        nested = df.filter(df["name"] == "nested.png")
        assert nested["parent"][0] == "sub/deep"

    def test_top_level_parent_empty(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        top = df.filter(df["name"] == "app.py")
        assert top["parent"][0] == ""


# ── Extension and MIME ────────────────────────────────────────────────


class TestExtensionMime:

    def test_ext_includes_dot(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        py = df.filter(df["name"] == "app.py")
        assert py["ext"][0] == ".py"

    def test_mime_for_python(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        py = df.filter(df["name"] == "app.py")
        mime = py["mime"][0]
        assert "text" in mime.lower()  # mime_guess returns text/plain or text/x-python

    def test_mime_for_png(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        png = df.filter(df["name"] == "logo.png")
        assert png["mime"][0] == "image/png"

    def test_mime_for_mp4(self, media_tree: Path):
        ctx = Context(media_tree)
        df = ctx.to_polars()
        mp4 = df.filter(df["name"] == "clip.mp4")
        assert "mp4" in mp4["mime"][0].lower() or "video" in mp4["mime"][0].lower()


# ── Parquet Roundtrip ─────────────────────────────────────────────────


class TestParquetRoundtrip:

    def test_roundtrip_preserves_dimensions(self, media_tree: Path):
        ctx = Context(media_tree)
        saved = ctx.save()
        assert saved.exists()

        import pyarrow.parquet as pq
        table = pq.read_table(saved)
        assert "width" in table.column_names
        assert "height" in table.column_names

        df = table.to_pandas()
        pngs = df[df["name"].str.endswith(".png")]
        assert pngs["width"].notna().all()
        assert pngs["height"].notna().all()

    def test_roundtrip_column_count(self, media_tree: Path):
        ctx = Context(media_tree)
        saved = ctx.save()
        import pyarrow.parquet as pq
        table = pq.read_table(saved)
        assert table.num_columns == 14


# ── CLI Integration ───────────────────────────────────────────────────


class TestL0Cli:

    def test_describe_shows_width_height(self, media_tree: Path):
        result = runner.invoke(app, ["find", str(media_tree), "--schema", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = [c["column"] for c in data]
        assert "width" in names
        assert "height" in names

    def test_find_width_height_columns(self, media_tree: Path):
        result = runner.invoke(app, [
            "find", str(media_tree), "--columns", "name,kind,width,height",
        ])
        assert result.exit_code == 0

    def test_sql_dimensions_query(self, media_tree: Path):
        result = runner.invoke(app, [
            "sql",
            "SELECT name, width, height FROM files WHERE width IS NOT NULL",
            "--dir", str(media_tree),
            "--format", "json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) > 0
        assert all("width" in row for row in data)

    def test_find_json_has_dimensions(self, media_tree: Path):
        result = runner.invoke(app, ["find", str(media_tree), "--kind", "image", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) > 0
        for row in data:
            assert "width" in row
        pngs = [r for r in data if r.get("name", "").endswith(".png")]
        assert all(int(r["width"]) > 0 for r in pngs)


# ── File Count ────────────────────────────────────────────────────────


class TestFileCount:

    def test_total_file_count(self, media_tree: Path):
        ctx = Context(media_tree)
        assert ctx.num_files == 13

    def test_image_count(self, media_tree: Path):
        ctx = Context(media_tree)
        images = ctx.filter(kind="image")
        assert images.num_files == 4  # logo.png, banner.png, photo.jpg, nested.png

    def test_code_count(self, media_tree: Path):
        ctx = Context(media_tree)
        code = ctx.filter(kind="code")
        assert code.num_files == 4  # app.py, lib.rs, index.js, helper.py
