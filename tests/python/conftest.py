"""Shared test fixtures for mm Python tests."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

# Redirect mm's on-disk caches (FSLRUCache for transcripts/scenes) to a
# session-scoped temp directory before any ``mm.*`` import runs.  Without
# this, tests that invoke ``transcript_messages`` or ``detect_scenes``
# would write pickle entries into the developer's real ``~/.cache/mm/``
# and pollute it with ephemeral fingerprints from ``tmp_path`` files.
#
# Done at module-level (not in a fixture) because pytest imports test
# modules — which transitively import mm — before any fixture fires.
# ``mm.cache.cache_dir()`` resolves ``MM_CACHE_DIR`` lazily on first
# cache access, so setting the env var here is sufficient.
_MM_CACHE_TMP = tempfile.mkdtemp(prefix="mm-test-cache-")
os.environ.setdefault("MM_CACHE_DIR", _MM_CACHE_TMP)


@pytest.fixture
def active_profile() -> str:
    """Name of the LLM profile to pin for the duration of a test.

    Defaults to ``"ollama"`` — the built-in OpenAI-compatible profile.
    It has no ``"gemini"`` substring, so ``mm.encoders.resolve_provider``
    resolves to ``"openai"`` and encoders emit OpenAI-shaped content
    parts, matching what ``LlmBackend`` (OpenAI SDK) and
    ``refs_messages._adapt_part`` assume.

    Override per-test via indirect parametrization::

        @pytest.mark.parametrize("active_profile", ["gemini"], indirect=True)
        def test_gemini_workflow(...): ...

    or per-class by redefining the fixture on the test class::

        class TestGeminiStuff:
            @pytest.fixture
            def active_profile(self) -> str:
                return "gemini"
    """
    return "ollama"


@pytest.fixture(autouse=True)
def use_active_profile(active_profile: str, monkeypatch) -> None:
    """Apply the name from ``active_profile`` to ``MM_PROFILE`` for the test.

    ``MM_PROFILE`` wins over the file config in
    ``mm.profile.get_active_profile_name``, so this isolates every test
    from the developer's local ``~/.config/mm/config.toml``. Tests that
    exercise profile resolution itself (``test_profile.py``) clear
    ``MM_PROFILE`` in their own module-scoped fixture, which takes
    precedence within that module.
    """
    monkeypatch.setenv("MM_PROFILE", active_profile)
    _stub = {
        "name": active_profile,
        "model": "test_model",
        "base_url": "test_base_url",
        "api_key": "noop",
    }
    monkeypatch.setattr("mm.profile.get_profile_by_name", lambda _n: _stub)


def _sqlite_vec_available() -> bool:
    """Check if sqlite3 supports loading extensions (needed for sqlite-vec)."""
    try:
        conn = sqlite3.connect(":memory:")
        conn.enable_load_extension(True)
        import sqlite_vec

        sqlite_vec.load(conn)
        conn.close()
        return True
    except (AttributeError, ImportError, OSError):
        return False


requires_sqlite_vec = pytest.mark.skipif(
    not _sqlite_vec_available(),
    reason="sqlite3 extension loading not available (no sqlite-vec support)",
)


@pytest.fixture(autouse=True)
def reset_shared_db():
    """Clear the ``shared_db`` cache before each test to reset the MmDatabase instance."""
    from mm.store.utils import shared_db

    yield
    shared_db.cache_clear()


@pytest.fixture
def isolated_db(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``MmDatabase`` at a temp directory outside any test's ``tmp_path``.

    Keeping the DB out of ``tmp_path`` ensures its WAL/SHM sidecar files aren't
    picked up by directory scans the command-under-test runs against ``tmp_path``.
    """
    from mm.store.db import MmDatabase

    db_dir = tmp_path_factory.mktemp("mmdb")
    db_path = db_dir / "mm.db"
    monkeypatch.setattr(MmDatabase, "DB_PATH", db_path)
    monkeypatch.setattr(MmDatabase, "DB_DIR", db_dir)
    return db_path


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

    # WebM magic bytes so scanners classify this as kind=video
    (tmp_path / "clip.webm").write_bytes(b"\x1a\x45\xdf\xa3" + b"\x00" * 64)

    # PDF magic bytes so scanners classify this as kind=document
    (tmp_path / "doc.pdf").write_bytes(b"%PDF-1.4\n" + b"\x00" * 64)

    return tmp_path


@pytest.fixture
def gitignored_tree(tmp_path: Path) -> Path:
    """Directory with a .gitignore that excludes some files."""
    root = tmp_path / "gi"
    root.mkdir()
    (root / ".git").mkdir()
    (root / ".gitignore").write_text("*.log\ndata/\n")
    (root / "keep.py").write_text("x = 1\n")
    (root / "skip.log").write_text("log line\n")
    (root / "data").mkdir()
    (root / "data" / "file.csv").write_text("a,b,c\n")
    return root


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
