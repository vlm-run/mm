"""Shared test fixtures for mm Python tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def small_tree(tmp_path: Path) -> Path:
    """Create a small directory tree with mixed file types."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main():\n    print('hello')\n")
    (tmp_path / "src" / "lib.rs").write_text("pub fn add(a: i32, b: i32) -> i32 { a + b }\n")
    (tmp_path / "src" / "utils.js").write_text("export const add = (a, b) => a + b;\n")

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "readme.md").write_text("# Project\n\nA test project.\n")

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.toml").write_text("[server]\nport = 8080\n")
    (tmp_path / "config" / "data.json").write_text('{"key": "value"}\n')

    (tmp_path / "README.md").write_text("# Root README\n")
    (tmp_path / "Makefile").write_text("all:\n\techo hello\n")

    # Create a small binary-like file (PNG header)
    png_header = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
    (tmp_path / "icon.png").write_bytes(png_header + b"\x00" * 100)

    return tmp_path


@pytest.fixture
def large_tree(tmp_path: Path) -> Path:
    """Create a larger directory tree for benchmarking."""
    extensions = [".py", ".rs", ".js", ".md", ".toml", ".json", ".txt", ".yaml"]
    for i in range(500):
        depth = i % 4
        dir_path = tmp_path
        for d in range(depth):
            dir_path = dir_path / f"d{d}"
        dir_path.mkdir(parents=True, exist_ok=True)
        ext = extensions[i % len(extensions)]
        (dir_path / f"file_{i}{ext}").write_text(f"content {i}\n")
    return tmp_path


@pytest.fixture
def mixed_1k_tree(tmp_path: Path) -> Path:
    """Create a 1000-file mixed directory with code, images, config, and text."""
    import struct

    extensions = [".py", ".rs", ".js", ".ts", ".md", ".toml", ".json", ".yaml", ".txt", ".csv"]

    (tmp_path / "src").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "images").mkdir()
    (tmp_path / "data").mkdir()

    for i in range(800):
        depth = i % 3
        if depth == 0:
            dirs = ["src", "docs", "config", "data"]
        elif depth == 1:
            dirs = ["src", "docs"]
        else:
            dirs = ["config"]
        d = dirs[i % len(dirs)]
        ext = extensions[i % len(extensions)]
        if ext == ".json":
            content = f'{{"id": {i}}}'
        else:
            content = f"# File {i}\n" + "".join(f"content line {k}\n" for k in range(5 + i % 20))
        (tmp_path / d / f"file_{i}{ext}").write_text(content)

    # Small valid PNGs for the image portion
    for i in range(200):
        w, h = 100 + (i % 200), 80 + (i % 150)
        # Minimal valid PNG: 8-byte sig + IHDR + IEND
        png_sig = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
        import zlib

        ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
        ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
        iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
        iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
        (tmp_path / "images" / f"img_{i}.png").write_bytes(png_sig + ihdr + iend)

    return tmp_path


@pytest.fixture
def youtube_dir() -> Path | None:
    """Return the youtube data directory if it exists."""
    p = Path.home() / "data" / "youtube"
    if p.exists() and any(p.glob("*.mp4")):
        return p
    return None


@pytest.fixture
def demo_dir() -> Path | None:
    """Return the 1-demo data directory if it exists."""
    p = Path.home() / "data" / "1-demo"
    if p.exists():
        return p
    return None
