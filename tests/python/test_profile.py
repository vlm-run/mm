"""Tests for mm profile management.

Covers: profile CRUD, active profile resolution, backward-compat migration,
CLI subcommands (list/use/add/remove), --profile flag, MM_PROFILE env.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mm.config import (
    DEFAULTS,
    _read_config_file,
    get_provider,
    get_provider_with_sources,
    set_cli_overrides,
    write_config,
)
from mm.profile import (
    add_profile,
    get_active_profile_name,
    get_profile_names,
    get_profile_section,
    migrate_to_profiles,
    remove_profile,
    set_active_profile,
    write_full_config,
)


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path: Path, monkeypatch):
    """Point config + profile modules at a temp dir and clear overrides."""
    monkeypatch.setattr("mm.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("mm.config.CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.setattr("mm.config.CONFIG_DIR_XDG", tmp_path)
    monkeypatch.setattr("mm.config.CONFIG_PATH_XDG", tmp_path / "config.toml")
    monkeypatch.setattr("mm.config.CONFIG_DIR_LEGACY", tmp_path / "legacy")
    monkeypatch.setattr("mm.config.CONFIG_PATH_LEGACY", tmp_path / "legacy" / "config.toml")

    set_cli_overrides(None, None, None, None)

    for var in ("MM_BASE_URL", "MM_API_KEY", "MM_MODEL", "MM_PROFILE"):
        monkeypatch.delenv(var, raising=False)

    monkeypatch.setattr("mm.config._platform_defaults", lambda: dict(DEFAULTS))


@pytest.fixture
def two_profile_config(tmp_path: Path) -> Path:
    """Write a config file with two profiles and return the path."""
    toml = """\
active_profile = "default"

[profile.default]
base_url = "http://localhost:11434"
api_key = ""
model = "qwen3.5:0.8b"

[profile.vlmrun]
base_url = "https://api.vlm.run/v1"
api_key = "sk-vlm-test"
model = "vlm-1"
"""
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(toml)
    return cfg_path


@pytest.fixture
def legacy_config(tmp_path: Path) -> Path:
    """Write a legacy [provider]-style config and return the path."""
    toml = """\
[provider]
base_url = "http://legacy:8000"
api_key = "legacy-key"
model = "legacy-model"
"""
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(toml)
    return cfg_path


# ── Profile resolution ──────────────────────────────────────────────


class TestActiveProfileResolution:
    def test_default_when_nothing_set(self):
        assert get_active_profile_name() == "default"

    def test_file_active_profile(self, two_profile_config):
        assert get_active_profile_name() == "default"

    def test_env_overrides_file(self, two_profile_config, monkeypatch):
        monkeypatch.setenv("MM_PROFILE", "vlmrun")
        assert get_active_profile_name() == "vlmrun"

    def test_cli_overrides_env(self, two_profile_config, monkeypatch):
        monkeypatch.setenv("MM_PROFILE", "vlmrun")
        set_cli_overrides(profile="default")
        assert get_active_profile_name() == "default"

    def test_cli_profile_flag(self):
        set_cli_overrides(profile="custom")
        assert get_active_profile_name() == "custom"


# ── Profile section reading ─────────────────────────────────────────


class TestGetProfileSection:
    def test_reads_named_profile(self, two_profile_config):
        file_data = _read_config_file()
        section = get_profile_section(file_data, "vlmrun")
        assert section["base_url"] == "https://api.vlm.run/v1"
        assert section["model"] == "vlm-1"

    def test_returns_empty_for_missing(self, two_profile_config):
        file_data = _read_config_file()
        assert get_profile_section(file_data, "nonexistent") == {}

    def test_backward_compat_provider_as_default(self, legacy_config):
        file_data = _read_config_file()
        section = get_profile_section(file_data, "default")
        assert section["base_url"] == "http://legacy:8000"
        assert section["model"] == "legacy-model"


# ── Profile names listing ───────────────────────────────────────────


class TestGetProfileNames:
    def test_lists_all_profiles(self, two_profile_config):
        names = get_profile_names()
        assert names == ["default", "vlmrun"]

    def test_legacy_shows_default(self, legacy_config):
        names = get_profile_names()
        assert names == ["default"]

    def test_empty_config_shows_default(self):
        names = get_profile_names()
        assert names == ["default"]


# ── Migration ───────────────────────────────────────────────────────


class TestMigrateToProfiles:
    def test_migrates_provider_to_profile(self):
        data = {"provider": {"base_url": "http://old", "model": "old-m"}}
        migrate_to_profiles(data)
        assert "provider" not in data
        assert data["profile"]["default"]["base_url"] == "http://old"
        assert data["active_profile"] == "default"

    def test_noop_when_profiles_exist(self):
        data = {
            "profile": {"default": {"base_url": "http://new"}},
            "active_profile": "default",
        }
        migrate_to_profiles(data)
        assert data["profile"]["default"]["base_url"] == "http://new"

    def test_noop_when_neither(self):
        data = {}
        migrate_to_profiles(data)
        assert "profile" not in data


# ── Provider resolution with profiles ───────────────────────────────


class TestProviderWithProfiles:
    def test_default_profile_provider(self, two_profile_config):
        cfg = get_provider()
        assert cfg.base_url == "http://localhost:11434"
        assert cfg.model == "qwen3.5:0.8b"

    def test_switched_profile_provider(self, two_profile_config):
        set_cli_overrides(profile="vlmrun")
        cfg = get_provider()
        assert cfg.base_url == "https://api.vlm.run/v1"
        assert cfg.model == "vlm-1"

    def test_env_profile_provider(self, two_profile_config, monkeypatch):
        monkeypatch.setenv("MM_PROFILE", "vlmrun")
        cfg = get_provider()
        assert cfg.base_url == "https://api.vlm.run/v1"

    def test_cli_flag_overrides_profile_value(self, two_profile_config):
        set_cli_overrides(profile="vlmrun", model="override-model")
        cfg = get_provider()
        assert cfg.model == "override-model"
        assert cfg.base_url == "https://api.vlm.run/v1"

    def test_source_label_includes_profile_name(self, two_profile_config):
        set_cli_overrides(profile="vlmrun")
        rows = get_provider_with_sources()
        sources = {r[0]: r[2] for r in rows}
        assert sources["base_url"] == "file (vlmrun)"

    def test_legacy_provider_works(self, legacy_config):
        cfg = get_provider()
        assert cfg.base_url == "http://legacy:8000"
        assert cfg.model == "legacy-model"


# ── Profile CRUD ────────────────────────────────────────────────────


class TestAddProfile:
    def test_add_new_profile(self, two_profile_config):
        add_profile("openai", base_url="https://api.openai.com/v1", model="gpt-4o")
        names = get_profile_names()
        assert "openai" in names
        file_data = _read_config_file()
        assert file_data["profile"]["openai"]["model"] == "gpt-4o"

    def test_add_duplicate_raises(self, two_profile_config):
        with pytest.raises(ValueError, match="already exists"):
            add_profile("vlmrun", base_url="http://dup")

    def test_add_with_defaults(self, two_profile_config):
        add_profile("minimal", base_url="")
        file_data = _read_config_file()
        section = file_data["profile"]["minimal"]
        assert section["base_url"] == DEFAULTS["base_url"]
        assert section["model"] == DEFAULTS["model"]

    def test_add_to_legacy_config(self, legacy_config):
        add_profile("newone", base_url="http://new:9000", model="new-m")
        names = get_profile_names()
        assert "default" in names
        assert "newone" in names


class TestRemoveProfile:
    def test_remove_non_active(self, two_profile_config):
        remove_profile("vlmrun")
        names = get_profile_names()
        assert "vlmrun" not in names

    def test_remove_active_raises(self, two_profile_config):
        with pytest.raises(ValueError, match="Cannot remove the active profile"):
            remove_profile("default")

    def test_remove_nonexistent_raises(self, two_profile_config):
        with pytest.raises(ValueError, match="not found"):
            remove_profile("nope")


class TestSetActiveProfile:
    def test_switch_profile(self, two_profile_config):
        set_active_profile("vlmrun")
        file_data = _read_config_file()
        assert file_data["active_profile"] == "vlmrun"

    def test_switch_nonexistent_raises(self, two_profile_config):
        with pytest.raises(ValueError, match="not found"):
            set_active_profile("nope")

    def test_switch_then_get_provider(self, two_profile_config):
        set_active_profile("vlmrun")
        cfg = get_provider()
        assert cfg.base_url == "https://api.vlm.run/v1"


# ── Write/update with profiles ──────────────────────────────────────


class TestWriteConfigWithProfiles:
    def test_write_preserves_other_profiles(self, two_profile_config):
        write_config("http://new-default", "", "new-model")
        file_data = _read_config_file()
        assert file_data["profile"]["default"]["base_url"] == "http://new-default"
        assert file_data["profile"]["vlmrun"]["base_url"] == "https://api.vlm.run/v1"

    def test_write_to_active_profile(self, two_profile_config):
        set_cli_overrides(profile="vlmrun")
        write_config("http://updated-vlm", "new-key", "new-vlm-model")
        file_data = _read_config_file()
        assert file_data["profile"]["vlmrun"]["base_url"] == "http://updated-vlm"


class TestWriteFullConfig:
    def test_roundtrip(self, tmp_path):
        data = {
            "active_profile": "default",
            "profile": {
                "default": {"base_url": "http://a", "api_key": "", "model": "m1"},
                "other": {"base_url": "http://b", "api_key": "k", "model": "m2"},
            },
            "mode": {
                "fast": {"whisper_model": "tiny", "audio_speed": 2.0},
            },
        }
        write_full_config(data)
        reread = _read_config_file()
        assert reread["active_profile"] == "default"
        assert reread["profile"]["default"]["model"] == "m1"
        assert reread["profile"]["other"]["model"] == "m2"
        assert reread["mode"]["fast"]["whisper_model"] == "tiny"


# ── CLI subcommands ─────────────────────────────────────────────────


class TestProfileCli:
    """Test profile CLI subcommands via typer CliRunner."""

    @pytest.fixture
    def runner(self):
        from typer.testing import CliRunner

        from mm.cli import app

        return CliRunner(), app

    def test_profile_list_exit_zero(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["config", "profile", "list", "--format", "tsv"])
        assert result.exit_code == 0
        assert "default" in result.output
        assert "vlmrun" in result.output

    def test_profile_list_json(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["config", "profile", "list", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["active"] == "default"
        assert "default" in data["profiles"]
        assert "vlmrun" in data["profiles"]
        # api_key should be masked
        assert data["profiles"]["vlmrun"]["api_key"] == "••••"

    def test_profile_list_csv(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["config", "profile", "list", "--format", "csv"])
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        assert lines[0] == "profile,active,base_url,model"
        assert len(lines) == 3  # header + 2 profiles

    def test_profile_add_and_list(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(
            app,
            ["config", "profile", "add", "openai", "--base-url", "https://api.openai.com/v1", "--model", "gpt-4o"],
        )
        assert result.exit_code == 0
        assert "Added" in result.output
        # Verify it shows up
        result2 = cli_runner.invoke(app, ["config", "profile", "list", "--format", "json"])
        data = json.loads(result2.output)
        assert "openai" in data["profiles"]

    def test_profile_add_duplicate_fails(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(
            app, ["config", "profile", "add", "vlmrun", "--base-url", "http://dup"]
        )
        assert result.exit_code == 1

    def test_profile_use(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["config", "profile", "use", "vlmrun"])
        assert result.exit_code == 0
        assert "Switched" in result.output
        # Verify via config show
        result2 = cli_runner.invoke(app, ["config", "show", "--format", "json"])
        data = json.loads(result2.output)
        assert data["active_profile"] == "vlmrun"

    def test_profile_use_nonexistent_fails(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["config", "profile", "use", "nope"])
        assert result.exit_code == 1

    def test_profile_remove(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["config", "profile", "remove", "vlmrun"])
        assert result.exit_code == 0
        assert "Removed" in result.output
        result2 = cli_runner.invoke(app, ["config", "profile", "list", "--format", "json"])
        data = json.loads(result2.output)
        assert "vlmrun" not in data["profiles"]

    def test_profile_remove_active_fails(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["config", "profile", "remove", "default"])
        assert result.exit_code == 1

    def test_profile_flag_override(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["--profile", "vlmrun", "config", "show", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["active_profile"] == "vlmrun"
        assert data["provider"]["base_url"]["source"] == "file (vlmrun)"

    def test_profile_workflow_add_use_remove(self, runner, two_profile_config):
        """Full lifecycle: add -> use -> remove (after switching away)."""
        cli_runner, app = runner
        # Add
        r = cli_runner.invoke(
            app, ["config", "profile", "add", "test-p", "--base-url", "http://test:9000", "--model", "test-m"]
        )
        assert r.exit_code == 0
        # Use
        r = cli_runner.invoke(app, ["config", "profile", "use", "test-p"])
        assert r.exit_code == 0
        # Verify active
        r = cli_runner.invoke(app, ["config", "show", "--format", "json"])
        data = json.loads(r.output)
        assert data["active_profile"] == "test-p"
        # Switch back before removing
        r = cli_runner.invoke(app, ["config", "profile", "use", "default"])
        assert r.exit_code == 0
        # Remove
        r = cli_runner.invoke(app, ["config", "profile", "remove", "test-p"])
        assert r.exit_code == 0
        # Gone
        r = cli_runner.invoke(app, ["config", "profile", "list", "--format", "json"])
        data = json.loads(r.output)
        assert "test-p" not in data["profiles"]


# ── MM_PROFILE env var via CLI ──────────────────────────────────────


class TestEnvProfileCli:
    @pytest.fixture
    def runner(self):
        from typer.testing import CliRunner

        from mm.cli import app

        return CliRunner(), app

    def test_env_profile_selects_provider(self, runner, two_profile_config, monkeypatch):
        monkeypatch.setenv("MM_PROFILE", "vlmrun")
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["config", "show", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["active_profile"] == "vlmrun"
        assert data["provider"]["base_url"]["source"] == "file (vlmrun)"
