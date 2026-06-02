"""Centralized on-disk path settings for mm.

All of mm's cache, storage, database, blob, and config locations are declared
here in a single :class:`MmSettings` object. Keeping them in one place lets a
test or benchmark redirect *every* path at once to a fresh, isolated location
via ``MM_*`` environment variables (or by stubbing the settings object),
guaranteeing zero state contamination between runs.

Resolution is lazy: :func:`get_settings` builds the singleton on first access,
so environment variables set *after* ``mm`` is imported — e.g. in
``conftest.py`` — are still honoured. Call :func:`reset_settings` to rebuild the
singleton after mutating the environment within a live process.

Each path has an XDG-compliant default and a dedicated ``MM_*`` override:

==============  =================  ============================================
Setting         Env var            Default
==============  =================  ============================================
``cache_dir``   ``MM_CACHE_DIR``   ``$XDG_CACHE_HOME/mm`` or ``~/.cache/mm``
``data_dir``    ``MM_DATA_DIR``    ``$XDG_DATA_HOME/mm`` or ``~/.local/share/mm``
``config_dir``  ``MM_CONFIG_DIR``  ``$XDG_CONFIG_HOME/mm`` or ``~/.config/mm``
``db_path``     ``MM_DB_PATH``     ``<data_dir>/mm.db``
``blobs_dir``   ``MM_BLOBS_DIR``   ``<data_dir>/blobs``
==============  =================  ============================================

``db_path`` and ``blobs_dir`` default to being derived from ``data_dir`` but
each remains independently overridable by its own env var.
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
    """Single source of truth for mm's on-disk paths.

    Attributes:
        cache_dir: Memoisation cache root (transcripts, scene detection).
        data_dir: Storage root for the SQLite DB and content-addressed blobs.
        config_dir: Directory holding ``mm.toml`` plus user pipelines/encoders.
        db_path: SQLite database file; defaults to ``data_dir / "mm.db"``.
        blobs_dir: Content-addressed blob store; defaults to ``data_dir / "blobs"``.

    Example:
        >>> import os
        >>> os.environ["MM_DATA_DIR"] = "/tmp/mm-run"
        >>> from mm.settings import get_settings, reset_settings
        >>> reset_settings()
        >>> get_settings().db_path
        PosixPath('/tmp/mm-run/mm.db')
    """

    model_config = SettingsConfigDict(env_prefix="MM_", extra="ignore")

    cache_dir: Path = Field(default_factory=_default_cache_dir)
    data_dir: Path = Field(default_factory=_default_data_dir)
    config_dir: Path = Field(default_factory=_default_config_dir)
    db_path: Path = Field(default_factory=lambda: _default_data_dir() / "mm.db")
    blobs_dir: Path = Field(default_factory=lambda: _default_data_dir() / "blobs")

    @model_validator(mode="after")
    def _anchor_and_expand(self) -> MmSettings:
        """Anchor derived paths to ``data_dir`` and expand user home references.

        ``db_path`` and ``blobs_dir`` follow ``data_dir`` whenever they were not
        set explicitly (via ``MM_DB_PATH`` / ``MM_BLOBS_DIR``), so overriding
        ``MM_DATA_DIR`` alone relocates the whole storage root. ``~`` is then
        expanded across every path.
        """
        explicit = self.model_fields_set
        if "db_path" not in explicit:
            self.db_path = self.data_dir / "mm.db"
        if "blobs_dir" not in explicit:
            self.blobs_dir = self.data_dir / "blobs"
        self.cache_dir = self.cache_dir.expanduser()
        self.data_dir = self.data_dir.expanduser()
        self.config_dir = self.config_dir.expanduser()
        self.db_path = self.db_path.expanduser()
        self.blobs_dir = self.blobs_dir.expanduser()
        return self


@lru_cache(maxsize=1)
def get_settings() -> MmSettings:
    """Return the process-wide :class:`MmSettings` singleton.

    Built lazily on first call so env vars set before that first access take
    effect. Use :func:`reset_settings` to rebuild it after changing the
    environment within a running process (e.g. in tests).
    """
    return MmSettings()


def reset_settings() -> None:
    """Discard the cached settings so the next :func:`get_settings` re-reads env."""
    get_settings.cache_clear()
