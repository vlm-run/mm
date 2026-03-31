"""Tests for mm configuration resolution.

Validates the priority chain: active profile > defaults.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from mm.config import (
    DEFAULTS,
    ProviderConfig,
    get_provider,
    get_provider_with_sources,
    set_cli_overrides,
    update_mode_config,
    write_config,
)


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path: Path, monkeypatch):
    """Point config module at a temp dir and clear CLI overrides."""
    monkeypatch.setattr("mm.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("mm.config.CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.setattr("mm.config.CONFIG_DIR_XDG", tmp_path)
    monkeypatch.setattr("mm.config.CONFIG_PATH_XDG", tmp_path / "config.toml")
    monkeypatch.setattr("mm.config.CONFIG_DIR_LEGACY", tmp_path / "legacy")
    monkeypatch.setattr("mm.config.CONFIG_PATH_LEGACY", tmp_path / "legacy" / "config.toml")

    set_cli_overrides(None)

    monkeypatch.delenv("MM_PROFILE", raising=False)

    # Patch platform defaults to DEFAULTS for any OS (Linux CI uses different defaults)
    monkeypatch.setattr("mm.config._platform_defaults", lambda: dict(DEFAULTS))


class TestDefaults:
    def test_defaults_used_when_nothing_set(self):
        cfg = get_provider()
        assert cfg.base_url == DEFAULTS["base_url"]
        assert cfg.api_key == DEFAULTS["api_key"]
        assert cfg.model == DEFAULTS["model"]

    def test_source_is_default(self):
        rows = get_provider_with_sources()
        for _, _, source, _ in rows:
            assert source == "default"


class TestFileConfig:
    def test_file_overrides_defaults(self, tmp_path: Path):
        write_config(base_url="http://remote:8000", api_key="sk-123", model="gpt-4o")
        cfg = get_provider()
        assert cfg.base_url == "http://remote:8000"
        assert cfg.api_key == "sk-123"
        assert cfg.model == "gpt-4o"

    def test_partial_file_keeps_defaults(self, tmp_path: Path):
        toml = '[provider]\nmodel = "llama3"\n'
        (tmp_path / "config.toml").write_text(toml)
        cfg = get_provider()
        assert cfg.model == "llama3"
        assert cfg.base_url == DEFAULTS["base_url"]

    def test_malformed_file_falls_back(self, tmp_path: Path):
        (tmp_path / "config.toml").write_text("not valid toml {{{}}}}")
        cfg = get_provider()
        assert cfg == ProviderConfig()


class TestWriteConfig:
    def test_write_creates_file(self, tmp_path: Path):
        p = write_config("http://a", "k", "m")
        assert p.exists()
        assert 'base_url = "http://a"' in p.read_text()


class TestUpdateModeConfig:
    def test_update_mode_key(self, tmp_path: Path):
        write_config("http://a", "", "m")
        update_mode_config("mode.fast.whisper_model", "medium")
        from mm.config import get_mode_config

        cfg = get_mode_config("fast")
        assert cfg.whisper_model == "medium"

    def test_invalid_key_raises(self, tmp_path: Path):
        write_config("http://a", "", "m")
        with pytest.raises(ValueError, match="Invalid mode key"):
            update_mode_config("base_url", "http://x")


class TestApiKeyMasking:
    def test_api_key_masked_when_set(self, tmp_path: Path):
        write_config("http://a", "secret-key", "m")
        rows = get_provider_with_sources()
        api_row = [r for r in rows if r[0] == "api_key"][0]
        assert api_row[1] == "••••"

    def test_api_key_not_masked_for_default(self):
        rows = get_provider_with_sources()
        api_row = [r for r in rows if r[0] == "api_key"][0]
        assert api_row[1] == ""
