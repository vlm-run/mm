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


class TestResetDb:
    """Tests for mm config reset-db."""

    @pytest.fixture()
    def storage_dir(self, tmp_path: Path, monkeypatch):
        """Point MmDatabase storage at a temp dir and create fake data."""
        db_dir = tmp_path / "mm-storage"
        db_dir.mkdir()
        monkeypatch.setattr("mm.store.db.MmDatabase.DB_DIR", db_dir)
        monkeypatch.setattr("mm.store.db.MmDatabase.DB_PATH", db_dir / "mm.db")
        return db_dir

    def _create_storage(self, storage_dir: Path):
        """Create fake db file."""
        (storage_dir / "mm.db").write_text("fake")

    def test_reset_deletes_db(self, storage_dir: Path):
        from typer.testing import CliRunner

        from mm.cli import app

        self._create_storage(storage_dir)
        assert (storage_dir / "mm.db").exists()

        runner = CliRunner()
        result = runner.invoke(app, ["config", "reset-db", "--yes"])
        assert result.exit_code == 0
        assert "reset" in result.output.lower()
        assert not (storage_dir / "mm.db").exists()

    def test_reset_aborts_without_yes(self, storage_dir: Path):
        from typer.testing import CliRunner

        from mm.cli import app

        self._create_storage(storage_dir)

        runner = CliRunner()
        result = runner.invoke(app, ["config", "reset-db"], input="n\n")
        assert result.exit_code == 1
        # Files should still exist
        assert (storage_dir / "mm.db").exists()

    def test_reset_confirms_with_y(self, storage_dir: Path):
        from typer.testing import CliRunner

        from mm.cli import app

        self._create_storage(storage_dir)

        runner = CliRunner()
        result = runner.invoke(app, ["config", "reset-db"], input="y\n")
        assert result.exit_code == 0
        assert not (storage_dir / "mm.db").exists()

    def test_reset_noop_when_empty(self, storage_dir: Path):
        from typer.testing import CliRunner

        from mm.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["config", "reset-db", "--yes"])
        assert result.exit_code == 0
        assert "nothing to reset" in result.output.lower()
