"""Centralized on-disk paths for mm.

A single :class:`MmSettings` is the source of truth for every cache, data,
db, blob, and config location, each with an XDG default and an ``MM_*``
override. Resolution is lazy via :func:`get_settings`, so env vars set after
``mm`` is imported are honoured; call :func:`reset_settings` to rebuild the
singleton after mutating the environment in-process.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

__all__ = ["MmSettings", "get_settings", "reset_settings"]


def _xdg_dir(xdg_var: str, fallback: Path) -> Path:
    """Resolve an ``$XDG_*_HOME/mm`` location, ignoring non-absolute values."""
    if xdg := os.environ.get(xdg_var):
        base = Path(xdg).expanduser()
        if base.is_absolute():
            return base / "mm"
    return fallback


def _default_cache_dir() -> Path:
    return _xdg_dir("XDG_CACHE_HOME", Path.home() / ".cache" / "mm")


def _default_data_dir() -> Path:
    return _xdg_dir("XDG_DATA_HOME", Path.home() / ".local" / "share" / "mm")


def _default_config_dir() -> Path:
    return _xdg_dir("XDG_CONFIG_HOME", Path.home() / ".config" / "mm")


class MmSettings:
    """Source of truth for mm's on-disk paths.

    ``db_path`` and ``blobs_dir`` derive from ``data_dir`` unless given their
    own ``MM_DB_PATH`` / ``MM_BLOBS_DIR`` override.
    """

    __slots__ = ("blobs_dir", "cache_dir", "config_dir", "data_dir", "db_path")

    def __init__(
        self,
        *,
        cache_dir: Path | str | None = None,
        data_dir: Path | str | None = None,
        config_dir: Path | str | None = None,
        db_path: Path | str | None = None,
        blobs_dir: Path | str | None = None,
    ) -> None:
        env = os.environ.get
        self.cache_dir = Path(cache_dir or env("MM_CACHE_DIR") or _default_cache_dir()).expanduser()
        self.data_dir = Path(data_dir or env("MM_DATA_DIR") or _default_data_dir()).expanduser()
        self.config_dir = Path(
            config_dir or env("MM_CONFIG_DIR") or _default_config_dir()
        ).expanduser()
        self.db_path = Path(db_path or env("MM_DB_PATH") or self.data_dir / "mm.db").expanduser()
        self.blobs_dir = Path(
            blobs_dir or env("MM_BLOBS_DIR") or self.data_dir / "blobs"
        ).expanduser()


@lru_cache(maxsize=1)
def get_settings() -> MmSettings:
    """Return the process-wide :class:`MmSettings` singleton, built on first call."""
    return MmSettings()


def reset_settings() -> None:
    """Discard the cached settings so the next :func:`get_settings` re-reads env."""
    get_settings.cache_clear()
