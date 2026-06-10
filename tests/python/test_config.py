"""Tests for mm configuration resolution.

Validates the priority chain: active profile > defaults.
Also covers config CLI subcommands: reset-db, reset-profiles, reset.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from mm.config import (
    ConfigData,
    ProfileData,
    _read_config_file,
    set_cli_overrides,
    update_mode_config,
    write_full_config,
)
from mm.profile import (
    DEFAULT_PROFILE,
    GATEWAY_DEFAULTS,
    OLLAMA_DEFAULTS,
    OPENROUTER_DEFAULTS,
    RESERVED_PROFILES,
    Profile,
    add_profile,
    get_profile,
    get_profile_names,
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
        assert profile.base_url == GATEWAY_DEFAULTS["base_url"]
        assert profile.api_key == GATEWAY_DEFAULTS["api_key"]
        assert profile.model == GATEWAY_DEFAULTS["model"]


class TestFileConfig:
    def test_file_overrides_defaults(self, tmp_path: Path):
        set_cli_overrides("openrouter")
        profile_data = cast(
            ProfileData,
            {"base_url": "http://remote:8000", "api_key": "sk-123", "model": "gpt-4o"},
        )
        write_full_config(
            cast(
                ConfigData,
                {"active_profile": "openrouter", "profile": {"openrouter": profile_data}},
            )
        )
        profile = get_profile()
        assert profile.base_url == "http://remote:8000"
        assert profile.api_key == "sk-123"
        assert profile.model == "gpt-4o"

    def test_partial_file_keeps_user_values(self, tmp_path: Path):
        set_cli_overrides("ollama")
        toml = '[profile.ollama]\nbase_url = "http://localhost:11434/v1"\napi_key = ""\nmodel = "llama3"\n'
        (tmp_path / "config.toml").write_text(toml)
        profile = get_profile()
        # ollama is mutable — user values are preserved
        assert profile.model == "llama3"
        assert profile.base_url == OLLAMA_DEFAULTS["base_url"]
        assert profile.api_key == OLLAMA_DEFAULTS["api_key"]

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
                    "active_profile": "openrouter",
                    "profile": {
                        "openrouter": cast(
                            ProfileData, {"base_url": "http://a", "api_key": "k", "model": "m"}
                        )
                    },
                },
            )
        )
        assert p.exists()
        contents = p.read_text()
        assert "[profile.ollama]" in contents
        assert "[profile.openrouter]" in contents
        assert "[profile.gateway]" in contents
        assert 'base_url = "http://a"' in contents

    def test_gateway_profile_is_rewritten_to_builtin_values(self, tmp_path: Path):
        (tmp_path / "config.toml").write_text(
            """\
active_profile = "gateway"

[profile.gateway]
base_url = "http://custom:9999"
api_key = "secret"
model = "custom-model"
"""
        )

        set_cli_overrides("gateway")
        profile = get_profile()
        assert profile == Profile(
            name=GATEWAY_DEFAULTS["name"],
            base_url=GATEWAY_DEFAULTS["base_url"],
            api_key=GATEWAY_DEFAULTS["api_key"],
            model=GATEWAY_DEFAULTS["model"],
        )
        contents = (tmp_path / "config.toml").read_text()
        assert f'base_url = "{GATEWAY_DEFAULTS["base_url"]}"' in contents
        assert f'model = "{GATEWAY_DEFAULTS["model"]}"' in contents


class TestUpdateModeConfig:
    def test_update_mode_key(self, tmp_path: Path):
        write_full_config(
            cast(
                ConfigData,
                {
                    "active_profile": "ollama",
                    "profile": {
                        "ollama": cast(
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
                    "active_profile": "ollama",
                    "profile": {
                        "ollama": cast(
                            ProfileData, {"base_url": "http://a", "api_key": "", "model": "m"}
                        )
                    },
                },
            )
        )
        with pytest.raises(ValueError, match="Invalid config key"):
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
        from mm.cli import app
        from typer.testing import CliRunner

        self._create_storage(storage_dir)
        assert (storage_dir / "mm.db").exists()

        runner = CliRunner()
        result = runner.invoke(app, ["config", "reset-db", "--yes"])
        assert result.exit_code == 0
        assert "reset" in result.output.lower()
        assert not (storage_dir / "mm.db").exists()

    def test_reset_aborts_without_yes(self, storage_dir: Path):
        from mm.cli import app
        from typer.testing import CliRunner

        self._create_storage(storage_dir)

        runner = CliRunner()
        result = runner.invoke(app, ["config", "reset-db"], input="n\n")
        assert result.exit_code == 1
        # Files should still exist
        assert (storage_dir / "mm.db").exists()

    def test_reset_confirms_with_y(self, storage_dir: Path):
        from mm.cli import app
        from typer.testing import CliRunner

        self._create_storage(storage_dir)

        runner = CliRunner()
        result = runner.invoke(app, ["config", "reset-db"], input="y\n")
        assert result.exit_code == 0
        assert not (storage_dir / "mm.db").exists()

    def test_reset_noop_when_empty(self, storage_dir: Path):
        from mm.cli import app
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(app, ["config", "reset-db", "--yes"])
        assert result.exit_code == 0
        assert "nothing to reset" in result.output.lower()


class TestResetProfiles:
    """Tests for mm config reset-profiles."""

    def _setup_custom_profiles(self):
        """Add custom profiles and switch active to a non-default."""
        add_profile("openai", base_url="https://api.openai.com/v1", model="gpt-4o", api_key="sk-x")
        add_profile("custom", base_url="http://custom:8000", model="custom-m")
        from mm.profile import set_active_profile

        set_active_profile("openai")

    def test_reset_profiles_with_yes(self):
        from mm.cli import app
        from typer.testing import CliRunner

        self._setup_custom_profiles()
        assert "openai" in get_profile_names()
        assert "custom" in get_profile_names()

        runner = CliRunner()
        result = runner.invoke(app, ["config", "reset-profiles", "--yes"])
        assert result.exit_code == 0
        assert "reset to defaults" in result.output.lower()

        # Custom profiles removed
        names = get_profile_names()
        assert "openai" not in names
        assert "custom" not in names

        # Reserved profiles present
        for name in RESERVED_PROFILES:
            assert name in names

        # Active profile reset to default
        profile = get_profile()
        assert profile.name == DEFAULT_PROFILE

    def test_reset_profiles_aborts_without_yes(self):
        from mm.cli import app
        from typer.testing import CliRunner

        self._setup_custom_profiles()

        runner = CliRunner()
        result = runner.invoke(app, ["config", "reset-profiles"], input="n\n")
        assert result.exit_code == 1
        assert "openai" in get_profile_names()

    def test_reset_profiles_confirms_with_y(self):
        from mm.cli import app
        from typer.testing import CliRunner

        self._setup_custom_profiles()

        runner = CliRunner()
        result = runner.invoke(app, ["config", "reset-profiles"], input="y\n")
        assert result.exit_code == 0
        assert "openai" not in get_profile_names()

    def test_reset_profiles_restores_reserved_defaults(self):
        from mm.cli import app
        from mm.profile import update_profile
        from typer.testing import CliRunner

        # Modify a mutable reserved profile
        update_profile("openrouter", base_url="http://modified:9000", model="modified-model")
        file_data = _read_config_file()
        assert "profile" in file_data
        assert file_data["profile"]["openrouter"]["base_url"] == "http://modified:9000"

        runner = CliRunner()
        result = runner.invoke(app, ["config", "reset-profiles", "--yes"])
        assert result.exit_code == 0

        # openrouter should be back to defaults
        file_data = _read_config_file()
        assert "profile" in file_data
        assert file_data["profile"]["openrouter"]["base_url"] == OPENROUTER_DEFAULTS["base_url"]
        assert file_data["profile"]["openrouter"]["model"] == OPENROUTER_DEFAULTS["model"]

    def test_reset_profiles_preserves_mode_settings(self):
        from mm.cli import app
        from typer.testing import CliRunner

        update_mode_config("mode.fast.whisper_model", "medium")
        from mm.config import get_mode_config

        assert get_mode_config("fast").whisper_model == "medium"

        runner = CliRunner()
        result = runner.invoke(app, ["config", "reset-profiles", "--yes"])
        assert result.exit_code == 0

        cfg = get_mode_config("fast")
        assert cfg.whisper_model == "medium"

    def test_reset_profiles_shows_custom_in_output(self):
        from mm.cli import app
        from typer.testing import CliRunner

        self._setup_custom_profiles()

        runner = CliRunner()
        result = runner.invoke(app, ["config", "reset-profiles", "--yes"])
        assert result.exit_code == 0
        assert "openai" in result.output
        assert "custom" in result.output


class TestResetAll:
    """Tests for mm config reset (db + profiles)."""

    @pytest.fixture()
    def storage_dir(self, tmp_path: Path, monkeypatch):
        db_dir = tmp_path / "mm-storage"
        db_dir.mkdir()
        monkeypatch.setattr("mm.store.db.MmDatabase.DB_DIR", db_dir)
        monkeypatch.setattr("mm.store.db.MmDatabase.DB_PATH", db_dir / "mm.db")
        return db_dir

    def _create_storage(self, storage_dir: Path):
        (storage_dir / "mm.db").write_text("fake")

    def test_reset_all_with_yes(self, storage_dir: Path):
        from mm.cli import app
        from typer.testing import CliRunner

        self._create_storage(storage_dir)
        add_profile("openai", base_url="https://api.openai.com/v1", model="gpt-4o")

        runner = CliRunner()
        result = runner.invoke(app, ["config", "reset", "--yes"])
        assert result.exit_code == 0

        # DB deleted
        assert not (storage_dir / "mm.db").exists()

        # Profiles reset
        names = get_profile_names()
        assert "openai" not in names
        for name in RESERVED_PROFILES:
            assert name in names

        # Active profile is default
        profile = get_profile()
        assert profile.name == DEFAULT_PROFILE

    def test_reset_all_aborts_without_yes(self, storage_dir: Path):
        from mm.cli import app
        from typer.testing import CliRunner

        self._create_storage(storage_dir)
        add_profile("openai", base_url="https://api.openai.com/v1", model="gpt-4o")

        runner = CliRunner()
        result = runner.invoke(app, ["config", "reset"], input="n\n")
        assert result.exit_code == 1
        assert (storage_dir / "mm.db").exists()
        assert "openai" in get_profile_names()

    def test_reset_all_confirms_with_y(self, storage_dir: Path):
        from mm.cli import app
        from typer.testing import CliRunner

        self._create_storage(storage_dir)

        runner = CliRunner()
        result = runner.invoke(app, ["config", "reset"], input="y\n")
        assert result.exit_code == 0
        assert not (storage_dir / "mm.db").exists()
        assert "reset" in result.output.lower()

    def test_reset_all_no_db_still_resets_profiles(self):
        from mm.cli import app
        from typer.testing import CliRunner

        add_profile("scratch", base_url="http://scratch", model="scratch-m")

        runner = CliRunner()
        result = runner.invoke(app, ["config", "reset", "--yes"])
        assert result.exit_code == 0
        assert "scratch" not in get_profile_names()
        assert "reset to defaults" in result.output.lower()

    def test_reset_all_preserves_mode_settings(self, storage_dir: Path):
        from mm.cli import app
        from typer.testing import CliRunner

        self._create_storage(storage_dir)
        update_mode_config("mode.fast.whisper_model", "medium")

        runner = CliRunner()
        result = runner.invoke(app, ["config", "reset", "--yes"])
        assert result.exit_code == 0

        from mm.config import get_mode_config

        cfg = get_mode_config("fast")
        assert cfg.whisper_model == "medium"


class TestConfigDoctor:
    """Tests for mm config doctor."""

    def test_doctor_exits_zero(self):
        from mm.cli import app
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(app, ["config", "doctor"])
        assert result.exit_code == 0

    def test_doctor_json_output(self):
        import json

        from mm.cli import app
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(app, ["config", "doctor", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        names = [c["name"] for c in data]
        assert "rust_extension" in names
        assert "mm_version" in names
        assert "python" in names

    def test_doctor_tsv_output(self):
        from mm.cli import app
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(app, ["config", "doctor", "--format", "tsv"])
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        assert lines[0] == "check\tstatus\tdetail"
        assert len(lines) >= 5

    def test_doctor_checks_rust_extension(self):
        import json

        from mm.cli import app
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(app, ["config", "doctor", "--format", "json"])
        data = json.loads(result.output)
        rust_check = next(c for c in data if c["name"] == "rust_extension")
        assert rust_check["status"] == "ok"
