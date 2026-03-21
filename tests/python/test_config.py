"""Tests for vlmctx configuration resolution.

Validates the priority chain: CLI flags > env vars > config file > defaults.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vlmctx.config import (
    DEFAULTS,
    ProviderConfig,
    get_provider,
    get_provider_with_sources,
    set_cli_overrides,
    update_config,
    write_config,
)


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path: Path, monkeypatch):
    """Point config module at a temp dir and clear CLI overrides + env vars."""
    monkeypatch.setattr("vlmctx.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("vlmctx.config.CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.setattr("vlmctx.config.CONFIG_DIR_XDG", tmp_path)
    monkeypatch.setattr("vlmctx.config.CONFIG_PATH_XDG", tmp_path / "config.toml")
    monkeypatch.setattr("vlmctx.config.CONFIG_DIR_LEGACY", tmp_path / "legacy")
    monkeypatch.setattr("vlmctx.config.CONFIG_PATH_LEGACY", tmp_path / "legacy" / "config.toml")

    set_cli_overrides(None, None, None)

    for var in ("VLMCTX_BASE_URL", "VLMCTX_API_KEY", "VLMCTX_MODEL"):
        monkeypatch.delenv(var, raising=False)


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


class TestEnvVars:
    def test_env_overrides_file(self, tmp_path: Path, monkeypatch):
        write_config(base_url="http://file:8000", api_key="", model="file-model")
        monkeypatch.setenv("VLMCTX_MODEL", "env-model")
        cfg = get_provider()
        assert cfg.model == "env-model"
        assert cfg.base_url == "http://file:8000"

    def test_all_env_vars(self, monkeypatch):
        monkeypatch.setenv("VLMCTX_BASE_URL", "http://env:9000")
        monkeypatch.setenv("VLMCTX_API_KEY", "env-key")
        monkeypatch.setenv("VLMCTX_MODEL", "env-model")
        cfg = get_provider()
        assert cfg.base_url == "http://env:9000"
        assert cfg.api_key == "env-key"
        assert cfg.model == "env-model"


class TestCliOverrides:
    def test_cli_overrides_env(self, monkeypatch):
        monkeypatch.setenv("VLMCTX_MODEL", "env-model")
        set_cli_overrides(model="cli-model")
        cfg = get_provider()
        assert cfg.model == "cli-model"

    def test_cli_partial_override(self, tmp_path: Path):
        write_config(base_url="http://file:8000", api_key="file-key", model="file-model")
        set_cli_overrides(base_url="http://cli:7000")
        cfg = get_provider()
        assert cfg.base_url == "http://cli:7000"
        assert cfg.api_key == "file-key"
        assert cfg.model == "file-model"

    def test_source_labels(self, tmp_path: Path, monkeypatch):
        write_config(base_url="http://f:1", api_key="k", model="m")
        monkeypatch.setenv("VLMCTX_API_KEY", "ek")
        set_cli_overrides(model="cm")
        rows = get_provider_with_sources()
        sources = {r[0]: r[2] for r in rows}
        assert sources["base_url"] == "file"
        assert sources["api_key"] == "env"
        assert sources["model"] == "cli"


class TestWriteAndUpdate:
    def test_write_creates_file(self, tmp_path: Path):
        p = write_config("http://a", "k", "m")
        assert p.exists()
        assert 'base_url = "http://a"' in p.read_text()

    def test_update_preserves_others(self, tmp_path: Path):
        write_config("http://a", "k", "model-old")
        update_config("model", "model-new")
        cfg = get_provider()
        assert cfg.model == "model-new"
        assert cfg.base_url == "http://a"

    def test_update_nonexistent_creates_file(self, tmp_path: Path):
        update_config("model", "brand-new")
        cfg = get_provider()
        assert cfg.model == "brand-new"


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
