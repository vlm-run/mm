"""Tests for mm configuration resolution.

Validates the priority chain: active profile > defaults.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from mm.config import (
    ConfigData,
    ProfileData,
    set_cli_overrides,
    update_mode_config,
    write_full_config,
)
from mm.profile import (
    DEFAULT_PROFILE,
    DEFAULTS,
    OLLAMA_DEFAULTS,
    OLLAMA_PROFILE,
    Profile,
    get_profile,
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


class TestDefaults:
    def test_defaults_used_when_nothing_set(self):
        profile = get_profile()
        assert profile.name == DEFAULT_PROFILE
        assert profile.base_url == DEFAULTS["base_url"]
        assert profile.api_key == DEFAULTS["api_key"]
        assert profile.model == DEFAULTS["model"]


class TestFileConfig:
    def test_file_overrides_defaults(self, tmp_path: Path):
        set_cli_overrides(OLLAMA_PROFILE)
        profile_data = cast(
            ProfileData,
            {"base_url": "http://remote:8000", "api_key": "sk-123", "model": "gpt-4o"},
        )
        write_full_config(
            cast(
                ConfigData,
                {"active_profile": OLLAMA_PROFILE, "profile": {OLLAMA_PROFILE: profile_data}},
            )
        )
        profile = get_profile()
        assert profile.base_url == "http://remote:8000"
        assert profile.api_key == "sk-123"
        assert profile.model == "gpt-4o"

    def test_partial_file_keeps_defaults(self, tmp_path: Path):
        toml = '[profile.default]\nmodel = "llama3"\n'
        (tmp_path / "config.toml").write_text(toml)
        profile = get_profile()
        assert profile.model == DEFAULTS["model"]
        assert profile.base_url == DEFAULTS["base_url"]
        assert profile.api_key == DEFAULTS["api_key"]

    def test_legacy_config_is_migrated_to_ollama_profile(self, tmp_path: Path):
        toml = '[provider]\nmodel = "llama3"\n'
        (tmp_path / "config.toml").write_text(toml)
        profile = get_profile()
        assert profile.name == OLLAMA_PROFILE
        assert profile.model == "llama3"
        assert profile.base_url == OLLAMA_DEFAULTS["base_url"]
        contents = (tmp_path / "config.toml").read_text()
        assert "[provider]" not in contents
        assert "[profile.ollama]" in contents

    def test_malformed_file_falls_back(self, tmp_path: Path):
        (tmp_path / "config.toml").write_text("not valid toml {{{}}}}")
        profile = get_profile()
        assert profile == Profile()


class TestWriteFullConfigSetup:
    def test_write_creates_file(self, tmp_path: Path):
        p = write_full_config(
            cast(
                ConfigData,
                {
                    "active_profile": OLLAMA_PROFILE,
                    "profile": {
                        OLLAMA_PROFILE: cast(
                            ProfileData, {"base_url": "http://a", "api_key": "k", "model": "m"}
                        )
                    },
                },
            )
        )
        assert p.exists()
        contents = p.read_text()
        assert "[profile.default]" in contents
        assert "[profile.ollama]" in contents
        assert 'base_url = "http://a"' in contents

    def test_default_profile_is_rewritten_to_builtin_values(self, tmp_path: Path):
        (tmp_path / "config.toml").write_text(
            """\
active_profile = "default"

[profile.default]
base_url = "http://localhost:11434"
api_key = "secret"
model = "qwen3-vl:2b"
"""
        )

        profile = get_profile()
        assert profile == Profile(name=DEFAULT_PROFILE, **DEFAULTS)
        contents = (tmp_path / "config.toml").read_text()
        assert 'base_url = "https://mm-ctx.ngrok.io/v1"' in contents
        assert 'model = "Qwen/Qwen3.5-0.8B"' in contents


class TestUpdateModeConfig:
    def test_update_mode_key(self, tmp_path: Path):
        write_full_config(
            cast(
                ConfigData,
                {
                    "active_profile": OLLAMA_PROFILE,
                    "profile": {
                        OLLAMA_PROFILE: cast(
                            ProfileData, {"base_url": "http://a", "api_key": "", "model": "m"}
                        )
                    },
                },
            )
        )
        update_mode_config("mode.fast.whisper_model", "medium")
        from mm.config import get_mode_config

        cfg = get_mode_config("fast")
        assert cfg.whisper_model == "medium"

    def test_invalid_key_raises(self, tmp_path: Path):
        write_full_config(
            cast(
                ConfigData,
                {
                    "active_profile": OLLAMA_PROFILE,
                    "profile": {
                        OLLAMA_PROFILE: cast(
                            ProfileData, {"base_url": "http://a", "api_key": "", "model": "m"}
                        )
                    },
                },
            )
        )
        with pytest.raises(ValueError, match="Invalid mode key"):
            update_mode_config("base_url", "http://x")
