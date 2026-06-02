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

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["MmSettings", "get_settings", "reset_settings"]


def _xdg_dir(xdg_var: str, fallback: Path) -> Path:
    """Resolve an ``$XDG_*_HOME/mm`` location, falling back to a home path."""
    if xdg := os.environ.get(xdg_var):
        return Path(xdg).expanduser() / "mm"
    return fallback


def _default_cache_dir() -> Path:
    return _xdg_dir("XDG_CACHE_HOME", Path.home() / ".cache" / "mm")


def _default_data_dir() -> Path:
    return _xdg_dir("XDG_DATA_HOME", Path.home() / ".local" / "share" / "mm")


def _default_config_dir() -> Path:
    return _xdg_dir("XDG_CONFIG_HOME", Path.home() / ".config" / "mm")


class MmSettings(BaseSettings):
    """Source of truth for mm's on-disk paths.

    ``db_path`` and ``blobs_dir`` derive from ``data_dir`` unless given their
    own ``MM_DB_PATH`` / ``MM_BLOBS_DIR`` override.
    """

    model_config = SettingsConfigDict(env_prefix="MM_", extra="ignore")

    cache_dir: Path = Field(default_factory=_default_cache_dir)
    data_dir: Path = Field(default_factory=_default_data_dir)
    config_dir: Path = Field(default_factory=_default_config_dir)
    db_path: Path = Field(default=Path("mm.db"))
    blobs_dir: Path = Field(default=Path("blobs"))

    @model_validator(mode="after")
    def _derive(self) -> MmSettings:
        """Anchor derived paths to ``data_dir`` and expand ``~`` in every path."""
        if "db_path" not in self.model_fields_set:
            self.db_path = self.data_dir / "mm.db"
        if "blobs_dir" not in self.model_fields_set:
            self.blobs_dir = self.data_dir / "blobs"
        self.cache_dir = self.cache_dir.expanduser()
        self.data_dir = self.data_dir.expanduser()
        self.config_dir = self.config_dir.expanduser()
        self.db_path = self.db_path.expanduser()
        self.blobs_dir = self.blobs_dir.expanduser()
        return self


@lru_cache(maxsize=1)
def get_settings() -> MmSettings:
    """Return the process-wide :class:`MmSettings` singleton, built on first call."""
    return MmSettings()


def reset_settings() -> None:
    """Discard the cached settings so the next :func:`get_settings` re-reads env."""
    get_settings.cache_clear()
