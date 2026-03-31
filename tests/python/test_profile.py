"""Tests for mm profile management.

Covers: profile CRUD (including update), active profile resolution, backward-compat
migration, CLI subcommands (list/use/add/update/remove), --profile flag, MM_PROFILE env.
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
    PROFILE_KEYS,
    add_profile,
    get_active_profile_name,
    get_profile_names,
    get_profile_section,
    migrate_to_profiles,
    remove_profile,
    set_active_profile,
    update_profile,
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

    set_cli_overrides(None)

    monkeypatch.delenv("MM_PROFILE", raising=False)

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
        new_data = migrate_to_profiles(data)
        assert "provider" not in data
        assert new_data["profile"]["default"]["base_url"] == "http://old"
        assert new_data["active_profile"] == "default"

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


# ── Profile keys constant ──────────────────────────────────────────


class TestProfileKeys:
    def test_contains_expected_keys(self):
        assert PROFILE_KEYS == {"base_url", "api_key", "model"}


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

    def test_source_label_includes_profile_name(self, two_profile_config):
        set_cli_overrides(profile="vlmrun")
        rows = get_provider_with_sources()
        sources = {r[0]: r[2] for r in rows}
        assert sources["base_url"] == "file (vlmrun)"

    def test_empty_api_key_source_is_file_not_default(self, two_profile_config):
        """api_key = '' in profile should show source as 'file', not 'default'."""
        rows = get_provider_with_sources()
        sources = {r[0]: r[2] for r in rows}
        assert sources["api_key"].startswith("file")

    def test_nonexistent_profile_raises(self, two_profile_config):
        """--profile with a typo should fail, not silently use defaults."""
        set_cli_overrides(profile="typo-profile")
        with pytest.raises(ValueError, match="not found"):
            get_provider()

    def test_nonexistent_profile_via_env_raises(self, two_profile_config, monkeypatch):
        monkeypatch.setenv("MM_PROFILE", "doesnt-exist")
        with pytest.raises(ValueError, match="not found"):
            get_provider()

    def test_default_without_config_file_uses_builtins(self):
        """No config file at all — default profile resolves to built-in defaults."""
        cfg = get_provider()
        assert cfg.base_url == DEFAULTS["base_url"]
        assert cfg.model == DEFAULTS["model"]

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
            add_profile("vlmrun", base_url="http://dup", model="dup-m")

    def test_add_requires_base_url(self, two_profile_config):
        with pytest.raises(ValueError, match="base_url is required"):
            add_profile("broken", base_url="", model="some-model")

    def test_add_requires_model(self, two_profile_config):
        with pytest.raises(ValueError, match="model is required"):
            add_profile("broken", base_url="http://localhost:8000", model="")

    def test_add_rejects_dots_in_name(self, two_profile_config):
        with pytest.raises(ValueError, match="Invalid profile name"):
            add_profile("my.provider", base_url="http://x", model="m")

    def test_add_rejects_spaces_in_name(self, two_profile_config):
        with pytest.raises(ValueError, match="Invalid profile name"):
            add_profile("my provider", base_url="http://x", model="m")

    def test_add_rejects_empty_name(self, two_profile_config):
        with pytest.raises(ValueError, match="Invalid profile name"):
            add_profile("", base_url="http://x", model="m")

    def test_add_allows_hyphens_and_underscores(self, two_profile_config):
        add_profile("my-provider_v2", base_url="http://x", model="m")
        assert "my-provider_v2" in get_profile_names()

    def test_add_to_legacy_config(self, legacy_config):
        add_profile("newone", base_url="http://new:9000", model="new-m")
        names = get_profile_names()
        assert "default" in names
        assert "newone" in names


class TestUpdateProfile:
    def test_update_single_field(self, two_profile_config):
        update_profile("vlmrun", model="vlm-2")
        file_data = _read_config_file()
        assert file_data["profile"]["vlmrun"]["model"] == "vlm-2"
        # Other fields preserved
        assert file_data["profile"]["vlmrun"]["base_url"] == "https://api.vlm.run/v1"
        assert file_data["profile"]["vlmrun"]["api_key"] == "sk-vlm-test"

    def test_update_multiple_fields(self, two_profile_config):
        update_profile("vlmrun", base_url="http://new-vlm:8000", model="vlm-3")
        file_data = _read_config_file()
        assert file_data["profile"]["vlmrun"]["base_url"] == "http://new-vlm:8000"
        assert file_data["profile"]["vlmrun"]["model"] == "vlm-3"
        assert file_data["profile"]["vlmrun"]["api_key"] == "sk-vlm-test"

    def test_update_api_key(self, two_profile_config):
        update_profile("vlmrun", api_key="sk-new-key")
        file_data = _read_config_file()
        assert file_data["profile"]["vlmrun"]["api_key"] == "sk-new-key"

    def test_update_all_fields(self, two_profile_config):
        update_profile("default", base_url="http://x", api_key="k", model="m")
        file_data = _read_config_file()
        p = file_data["profile"]["default"]
        assert p["base_url"] == "http://x"
        assert p["api_key"] == "k"
        assert p["model"] == "m"

    def test_update_rejects_empty_base_url(self, two_profile_config):
        with pytest.raises(ValueError, match="base_url cannot be empty"):
            update_profile("vlmrun", base_url="")

    def test_update_rejects_empty_model(self, two_profile_config):
        with pytest.raises(ValueError, match="model cannot be empty"):
            update_profile("vlmrun", model="")

    def test_update_allows_empty_api_key(self, two_profile_config):
        """api_key can be set to empty (e.g. local Ollama needs no key)."""
        update_profile("vlmrun", api_key="")
        file_data = _read_config_file()
        assert file_data["profile"]["vlmrun"]["api_key"] == ""

    def test_update_nonexistent_raises(self, two_profile_config):
        with pytest.raises(ValueError, match="not found"):
            update_profile("nope", model="x")

    def test_update_no_fields_raises(self, two_profile_config):
        with pytest.raises(ValueError, match="No fields to update"):
            update_profile("vlmrun")

    def test_update_preserves_other_profiles(self, two_profile_config):
        update_profile("vlmrun", model="vlm-2")
        file_data = _read_config_file()
        # Default profile unchanged
        assert file_data["profile"]["default"]["model"] == "qwen3.5:0.8b"

    def test_update_reflects_in_provider(self, two_profile_config):
        set_cli_overrides(profile="vlmrun")
        update_profile("vlmrun", model="vlm-updated")
        cfg = get_provider()
        assert cfg.model == "vlm-updated"


class TestRemoveProfile:
    def test_remove_non_active(self, two_profile_config):
        remove_profile("vlmrun")
        names = get_profile_names()
        assert "vlmrun" not in names

    def test_remove_default_always_fails(self, two_profile_config):
        """'default' cannot be removed even when it's not the active profile."""
        set_active_profile("vlmrun")
        with pytest.raises(ValueError, match="cannot be removed"):
            remove_profile("default")

    def test_remove_default_shows_alternatives(self, two_profile_config):
        with pytest.raises(ValueError, match="mm profile update default"):
            remove_profile("default")

    def test_remove_active_non_default_raises(self, two_profile_config):
        set_active_profile("vlmrun")
        with pytest.raises(ValueError, match="Cannot remove the active profile"):
            remove_profile("vlmrun")

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


# ── Write with profiles ────────────────────────────────────────────


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
        from mm.cli import app
        from typer.testing import CliRunner

        return CliRunner(), app

    def test_profile_list_exit_zero(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile","list", "--format", "tsv"])
        assert result.exit_code == 0
        assert "default" in result.output
        assert "vlmrun" in result.output

    def test_profile_list_json(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile","list", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["active"] == "default"
        assert "default" in data["profiles"]
        assert "vlmrun" in data["profiles"]
        # api_key should be masked
        assert data["profiles"]["vlmrun"]["api_key"] == "••••"

    def test_profile_list_csv(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile","list", "--format", "csv"])
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        assert lines[0] == "profile,active,base_url,model"
        assert len(lines) == 3  # header + 2 profiles

    def test_profile_add_and_list(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(
            app,
            [
                "profile",
                "add",
                "openai",
                "--base-url",
                "https://api.openai.com/v1",
                "--model",
                "gpt-4o",
            ],
        )
        assert result.exit_code == 0
        assert "Added" in result.output
        # Verify it shows up
        result2 = cli_runner.invoke(app, ["profile","list", "--format", "json"])
        data = json.loads(result2.output)
        assert "openai" in data["profiles"]

    def test_profile_add_duplicate_fails(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(
            app, ["profile","add", "vlmrun", "--base-url", "http://dup", "--model", "dup-m"]
        )
        assert result.exit_code == 1

    def test_profile_use(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile","use", "vlmrun"])
        assert result.exit_code == 0
        assert "Switched" in result.output
        # Verify via config show
        result2 = cli_runner.invoke(app, ["config", "show", "--format", "json"])
        data = json.loads(result2.output)
        assert data["active_profile"] == "vlmrun"

    def test_profile_use_nonexistent_fails(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile","use", "nope"])
        assert result.exit_code == 1

    def test_profile_update_single_field(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(
            app, ["profile","update", "vlmrun", "--model", "vlm-2"]
        )
        assert result.exit_code == 0
        assert "Updated" in result.output
        assert "model=vlm-2" in result.output
        # Verify change persisted
        result2 = cli_runner.invoke(app, ["profile","list", "--format", "json"])
        data = json.loads(result2.output)
        assert data["profiles"]["vlmrun"]["model"] == "vlm-2"

    def test_profile_update_multiple_fields(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(
            app,
            [
                "profile",
                "update",
                "vlmrun",
                "--model",
                "vlm-3",
                "--base-url",
                "http://new:9000",
            ],
        )
        assert result.exit_code == 0
        assert "model=vlm-3" in result.output
        assert "base_url=http://new:9000" in result.output

    def test_profile_update_api_key_masked(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(
            app, ["profile","update", "vlmrun", "--api-key", "sk-secret"]
        )
        assert result.exit_code == 0
        assert "api_key=••••" in result.output
        assert "sk-secret" not in result.output

    def test_profile_update_nonexistent_fails(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile","update", "nope", "--model", "x"])
        assert result.exit_code == 1

    def test_profile_update_no_fields_fails(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile","update", "vlmrun"])
        assert result.exit_code == 1

    def test_profile_remove(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile","remove", "vlmrun"])
        assert result.exit_code == 0
        assert "Removed" in result.output
        result2 = cli_runner.invoke(app, ["profile","list", "--format", "json"])
        data = json.loads(result2.output)
        assert "vlmrun" not in data["profiles"]

    def test_profile_remove_default_fails_with_guidance(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile","remove", "default"])
        assert result.exit_code == 1
        assert "cannot be removed" in result.output
        assert "mm profile update default" in result.output

    def test_profile_flag_override(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(
            app, ["--profile", "vlmrun", "config", "show", "--format", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["active_profile"] == "vlmrun"
        assert data["provider"]["base_url"] == "https://api.vlm.run/v1"

    def test_no_top_level_base_url_flag(self, runner):
        """--base-url is no longer a top-level flag."""
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["--base-url", "http://x", "config", "show"])
        assert result.exit_code != 0

    def test_no_top_level_model_flag(self, runner):
        """--model is no longer a top-level flag."""
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["--model", "x", "config", "show"])
        assert result.exit_code != 0

    def test_config_set_rejects_provider_keys(self, runner, two_profile_config):
        """config set should reject provider keys and point to profile update."""
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["config", "set", "base_url", "http://x"])
        assert result.exit_code == 1
        assert "profile" in result.output.lower()

    def test_config_set_accepts_mode_keys(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["config", "set", "mode.fast.whisper_model", "medium"])
        assert result.exit_code == 0
        assert "Set" in result.output

    def test_profile_workflow_add_update_use_remove(self, runner, two_profile_config):
        """Full lifecycle: add -> update -> use -> remove (after switching away)."""
        cli_runner, app = runner
        # Add
        r = cli_runner.invoke(
            app,
            [
                "profile",
                "add",
                "test-p",
                "--base-url",
                "http://test:9000",
                "--model",
                "test-m",
            ],
        )
        assert r.exit_code == 0
        # Update
        r = cli_runner.invoke(
            app,
            [
                "profile",
                "update",
                "test-p",
                "--api-key",
                "sk-test",
                "--model",
                "test-m-v2",
            ],
        )
        assert r.exit_code == 0
        # Use
        r = cli_runner.invoke(app, ["profile","use", "test-p"])
        assert r.exit_code == 0
        # Verify active + updated values
        r = cli_runner.invoke(app, ["config", "show", "--format", "json"])
        data = json.loads(r.output)
        assert data["active_profile"] == "test-p"
        assert data["provider"]["model"] == "test-m-v2"
        # Switch back before removing
        r = cli_runner.invoke(app, ["profile","use", "default"])
        assert r.exit_code == 0
        # Remove
        r = cli_runner.invoke(app, ["profile","remove", "test-p"])
        assert r.exit_code == 0
        # Gone
        r = cli_runner.invoke(app, ["profile","list", "--format", "json"])
        data = json.loads(r.output)
        assert "test-p" not in data["profiles"]

    def test_profile_help_shows_all_subcommands(self, runner):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile","--help"])
        assert result.exit_code == 0
        for cmd in ("list", "use", "add", "update", "remove"):
            assert cmd in result.output


# ── MM_PROFILE env var via CLI ──────────────────────────────────────


class TestEnvProfileCli:
    @pytest.fixture
    def runner(self):
        from mm.cli import app
        from typer.testing import CliRunner

        return CliRunner(), app

    def test_env_profile_selects_provider(self, runner, two_profile_config, monkeypatch):
        monkeypatch.setenv("MM_PROFILE", "vlmrun")
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["config", "show", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["active_profile"] == "vlmrun"
        assert data["provider"]["base_url"] == "https://api.vlm.run/v1"
