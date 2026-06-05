"""Tests for centralized path settings and per-run isolation.

Proves the in-process isolation mode: pointing ``MM_*`` env vars at fresh
temp dirs and rebuilding the settings singleton fully redirects the cache,
SQLite DB, and blob store, so a run never touches another run's state.
"""

from __future__ import annotations

from pathlib import Path

_FILE_COLS = (
    "uri",
    "name",
    "stem",
    "ext",
    "size",
    "modified",
    "created",
    "mime",
    "kind",
    "is_binary",
    "depth",
    "parent",
    "indexed_at",
)
_FILE_ROW = ("/x/a.py", "a.py", "a", "py", 1, 0, 0, "text/x-python", "code", 0, 0, "/x", 0)


def _insert_one(conn) -> None:
    placeholders = ", ".join("?" for _ in _FILE_COLS)
    conn.execute(f"INSERT INTO files ({', '.join(_FILE_COLS)}) VALUES ({placeholders})", _FILE_ROW)
    conn.commit()


def _redirect(monkeypatch, root: Path) -> None:
    from mm.settings import reset_settings
    from mm.store.utils import shared_db

    monkeypatch.setenv("MM_DATA_DIR", str(root / "data"))
    monkeypatch.setenv("MM_CACHE_DIR", str(root / "cache"))
    reset_settings()
    shared_db.cache_clear()


def test_env_overrides_redirect_all_paths(tmp_path: Path, monkeypatch) -> None:
    """``MM_DATA_DIR``/``MM_CACHE_DIR`` redirect cache, DB, and blobs together."""
    from mm.cache import cache_dir
    from mm.settings import get_settings

    _redirect(monkeypatch, tmp_path / "run")
    settings = get_settings()

    assert settings.data_dir == tmp_path / "run" / "data"
    assert settings.db_path == tmp_path / "run" / "data" / "mm.db"
    assert settings.blobs_dir == tmp_path / "run" / "data" / "blobs"
    assert cache_dir() == tmp_path / "run" / "cache"


def test_independent_blobs_and_db_overrides(tmp_path: Path, monkeypatch) -> None:
    """``MM_DB_PATH`` and ``MM_BLOBS_DIR`` override their derived defaults."""
    from mm.settings import get_settings, reset_settings

    monkeypatch.setenv("MM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MM_DB_PATH", str(tmp_path / "custom" / "store.db"))
    monkeypatch.setenv("MM_BLOBS_DIR", str(tmp_path / "custom" / "blobs"))
    reset_settings()
    settings = get_settings()

    assert settings.db_path == tmp_path / "custom" / "store.db"
    assert settings.blobs_dir == tmp_path / "custom" / "blobs"


def test_shared_db_honors_fresh_path_and_is_isolated(tmp_path: Path, monkeypatch) -> None:
    """A fresh ``MM_DATA_DIR`` gives ``shared_db()`` a new, empty DB.

    Writes a row under the first run's data dir, then rebinds to a second run
    and asserts the cached ``shared_db()`` picks up the new path and sees an
    empty ``files`` table — no contamination from the first run.
    """
    from mm.store.utils import shared_db

    _redirect(monkeypatch, tmp_path / "run-a")
    db_a = shared_db()
    assert db_a._db_path == tmp_path / "run-a" / "data" / "mm.db"
    _insert_one(db_a._connect)
    assert (tmp_path / "run-a" / "data" / "mm.db").exists()
    assert db_a._connect.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 1

    _redirect(monkeypatch, tmp_path / "run-b")
    db_b = shared_db()
    assert db_b is not db_a
    assert db_b._db_path == tmp_path / "run-b" / "data" / "mm.db"
    assert db_b._connect.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
