"""Shared test fixtures for vlmctx Python tests."""

from __future__ import annotations

import os
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
    (tmp_path / "config" / "settings.toml").write_text('[server]\nport = 8080\n')
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
