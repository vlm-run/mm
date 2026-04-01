"""Tests for mm profile management.

Covers: profile CRUD (including update), active profile resolution,
migration, CLI subcommands (list/use/add/update/remove), --profile flag, MM_PROFILE env.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from mm.config import (
    ConfigData,
    ProfileData,
    _read_config_file,
    set_cli_overrides,
    write_full_config,
)
from mm.profile import (
    DEFAULT_PROFILE,
    DEFAULTS,
    OLLAMA_DEFAULTS,
    OLLAMA_PROFILE,
    PROFILE_KEYS,
    Profile,
    add_profile,
    get_active_profile_name,
    get_profile,
    get_profile_names,
    get_profile_section,
    migrate_to_profiles,
    remove_profile,
    set_active_profile,
    update_profile,
)


def _profiles(file_data: ConfigData) -> dict[str, ProfileData]:
    return cast(dict[str, ProfileData], file_data.get("profile", {}))


def _active_profile(file_data: ConfigData) -> str:
    return cast(str, file_data.get("active_profile", DEFAULT_PROFILE))


def _mode_whisper_model(file_data: ConfigData, mode_name: str) -> str:
    mode_data = file_data.get("mode", {})
    return cast(str, mode_data.get(mode_name, {}).get("whisper_model", ""))


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


@pytest.fixture
def two_profile_config(tmp_path: Path) -> Path:
    """Write a config file with two profiles and return the path."""
    toml = """\
active_profile = "default"

[profile.default]
base_url = "https://mm-ctx.ngrok.io/v1"
api_key = "sk-vlm-test"
model = "Qwen/Qwen3.5-0.8B"

[profile.ollama]
base_url = "http://localhost:11434"
api_key = ""
model = "qwen3.5:0.8"
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
        assert get_active_profile_name() == DEFAULT_PROFILE

    def test_file_active_profile(self, two_profile_config):
        assert get_active_profile_name() == DEFAULT_PROFILE

    def test_env_overrides_file(self, two_profile_config, monkeypatch):
        monkeypatch.setenv("MM_PROFILE", OLLAMA_PROFILE)
        assert get_active_profile_name() == OLLAMA_PROFILE

    def test_cli_overrides_env(self, two_profile_config, monkeypatch):
        monkeypatch.setenv("MM_PROFILE", OLLAMA_PROFILE)
        set_cli_overrides(profile=DEFAULT_PROFILE)
        assert get_active_profile_name() == DEFAULT_PROFILE

    def test_cli_profile_flag(self):
        set_cli_overrides(profile="custom")
        assert get_active_profile_name() == "custom"


# ── Profile section reading ─────────────────────────────────────────


class TestGetProfileSection:
    def test_reads_named_profile(self, two_profile_config):
        file_data = _read_config_file()
        section = get_profile_section(file_data, "default")
        assert section["base_url"] == DEFAULTS["base_url"]
        assert section["model"] == DEFAULTS["model"]
        assert section["api_key"] == DEFAULTS["api_key"]

    def test_returns_empty_for_missing(self, two_profile_config):
        file_data = _read_config_file()
        assert get_profile_section(file_data, "nonexistent") == {}

    def test_legacy_config_is_migrated_before_section_reads(self, legacy_config):
        profile = get_profile()
        assert profile.name == OLLAMA_PROFILE
        file_data = _read_config_file()
        section = get_profile_section(file_data, OLLAMA_PROFILE)
        assert section["base_url"] == "http://legacy:8000"
        assert section["model"] == "legacy-model"
        assert "provider" not in file_data


# ── Profile names listing ───────────────────────────────────────────


class TestGetProfileNames:
    def test_lists_all_profiles(self, two_profile_config):
        names = get_profile_names()
        assert names == ["default", "ollama"]

    def test_legacy_shows_default(self, legacy_config):
        names = get_profile_names()
        assert names == ["default", "ollama"]

    def test_empty_config_shows_default(self):
        names = get_profile_names()
        assert names == ["default", "ollama"]


class TestBuiltinNormalization:
    def test_default_profile_is_forced_to_builtin_values(self, two_profile_config):
        profile = get_profile()
        assert profile == Profile(name=DEFAULT_PROFILE, **DEFAULTS)

        file_data = _read_config_file()
        assert _profiles(file_data)[DEFAULT_PROFILE] == DEFAULTS

    def test_missing_ollama_profile_is_added_with_defaults(self, tmp_path: Path):
        (tmp_path / "config.toml").write_text(
            """\
active_profile = \"default\"

[profile.default]
base_url = \"http://wrong\"
api_key = \"bad\"
model = \"wrong-model\"
"""
        )

        profile_names = get_profile_names()
        assert profile_names == ["default", "ollama"]

        file_data = _read_config_file()
        assert _profiles(file_data)[DEFAULT_PROFILE] == DEFAULTS
        assert _profiles(file_data)[OLLAMA_PROFILE] == OLLAMA_DEFAULTS


# ── Migration ───────────────────────────────────────────────────────


class TestMigrateToProfiles:
    def test_migrates_provider_to_profile(self):
        data: ConfigData = cast(
            ConfigData,
            {"provider": {"base_url": "http://old", "api_key": "", "model": "old-m"}},
        )
        migrated = migrate_to_profiles(data)
        assert migrated is True
        assert "provider" not in data
        assert _profiles(data)[OLLAMA_PROFILE]["base_url"] == "http://old"
        assert _active_profile(data) == OLLAMA_PROFILE

    def test_noop_when_profiles_exist(self):
        data: ConfigData = cast(
            ConfigData,
            {
                "profile": {
                    DEFAULT_PROFILE: {
                        "base_url": "http://new",
                        "api_key": "",
                        "model": "Qwen/Qwen3.5-0.8B",
                    }
                },
                "active_profile": DEFAULT_PROFILE,
            },
        )
        migrated = migrate_to_profiles(data)
        assert migrated is False
        assert _profiles(data)[DEFAULT_PROFILE]["base_url"] == "http://new"

    def test_noop_when_neither(self):
        data: ConfigData = cast(ConfigData, {})
        migrated = migrate_to_profiles(data)
        assert migrated is False
        assert "profile" not in data


# ── Profile keys constant ──────────────────────────────────────────


class TestProfileKeys:
    def test_contains_expected_keys(self):
        assert PROFILE_KEYS == {"base_url", "api_key", "model"}


# ── Profile resolution with profiles ───────────────────────────────


class TestProfileResolutionWithProfiles:
    def test_default_profile_matches_actual_profile(self, two_profile_config):
        profile = get_profile()
        assert profile == Profile(name=DEFAULT_PROFILE, **DEFAULTS)

    def test_switched_profile_matches_actual_profile(self, two_profile_config):
        set_cli_overrides(profile=OLLAMA_PROFILE)
        profile = get_profile()
        assert profile == Profile(name=OLLAMA_PROFILE, **OLLAMA_DEFAULTS)

    def test_env_profile_matches_actual_profile(self, two_profile_config, monkeypatch):
        monkeypatch.setenv("MM_PROFILE", OLLAMA_PROFILE)
        profile = get_profile()
        assert profile == Profile(name=OLLAMA_PROFILE, **OLLAMA_DEFAULTS)

    def test_nonexistent_profile_raises(self, two_profile_config):
        """--profile with a typo should fail, not silently use defaults."""
        set_cli_overrides(profile="typo-profile")
        with pytest.raises(ValueError, match="not found"):
            get_profile()

    def test_nonexistent_profile_via_env_raises(self, two_profile_config, monkeypatch):
        monkeypatch.setenv("MM_PROFILE", "doesnt-exist")
        with pytest.raises(ValueError, match="not found"):
            get_profile()

    def test_default_without_config_file_uses_builtins(self):
        """No config file at all — default profile resolves to built-in defaults."""
        profile = get_profile()
        assert profile == Profile(name=DEFAULT_PROFILE, **DEFAULTS)

    def test_legacy_config_uses_migrated_profile(self, legacy_config):
        profile = get_profile()
        assert profile == Profile(
            name=OLLAMA_PROFILE,
            base_url="http://legacy:8000",
            api_key="legacy-key",
            model="legacy-model",
        )

        file_data = _read_config_file()
        assert _profiles(file_data)[OLLAMA_PROFILE]["base_url"] == "http://legacy:8000"
        assert _profiles(file_data)[DEFAULT_PROFILE] == DEFAULTS


# ── Profile CRUD ────────────────────────────────────────────────────


class TestAddProfile:
    def test_add_new_profile(self, two_profile_config):
        add_profile("openai", base_url="https://api.openai.com/v1", model="gpt-4o")
        names = get_profile_names()
        assert "openai" in names
        file_data = _read_config_file()
        assert _profiles(file_data)["openai"]["model"] == "gpt-4o"

    def test_add_duplicate_raises(self, two_profile_config):
        with pytest.raises(ValueError, match="already exists"):
            add_profile(OLLAMA_PROFILE, base_url="http://dup", model="dup-m")

    def test_add_requires_base_url(self, two_profile_config):
        with pytest.raises(ValueError, match="base_url is required"):
            add_profile("broken", base_url="", model="some-model")

    def test_add_requires_model(self, two_profile_config):
        with pytest.raises(ValueError, match="model is required"):
            add_profile("broken", base_url="http://localhost:8000", model="")

    def test_add_rejects_dots_in_name(self, two_profile_config):
        with pytest.raises(ValueError, match="Invalid profile name"):
            add_profile("profile.name", base_url="http://x", model="m")

    def test_add_rejects_spaces_in_name(self, two_profile_config):
        with pytest.raises(ValueError, match="Invalid profile name"):
            add_profile("profile name", base_url="http://x", model="m")

    def test_add_rejects_empty_name(self, two_profile_config):
        with pytest.raises(ValueError, match="Invalid profile name"):
            add_profile("", base_url="http://x", model="m")

    def test_add_allows_hyphens_and_underscores(self, two_profile_config):
        add_profile("profile-name_v2", base_url="http://x", model="m")
        assert "profile-name_v2" in get_profile_names()

    def test_add_to_legacy_config(self, legacy_config):
        add_profile("newone", base_url="http://new:9000", model="new-m")
        names = get_profile_names()
        assert DEFAULT_PROFILE in names
        assert OLLAMA_PROFILE in names
        assert "newone" in names


class TestUpdateProfile:
    def test_update_single_field(self, two_profile_config):
        update_profile(OLLAMA_PROFILE, model="qwen3.5:latest")
        file_data = _read_config_file()
        assert _profiles(file_data)[OLLAMA_PROFILE]["model"] == "qwen3.5:latest"
        # Other fields preserved
        assert _profiles(file_data)[OLLAMA_PROFILE]["base_url"] == OLLAMA_DEFAULTS["base_url"]
        assert _profiles(file_data)[OLLAMA_PROFILE]["api_key"] == ""

    def test_update_multiple_fields(self, two_profile_config):
        update_profile(OLLAMA_PROFILE, base_url="http://new-ollama:11434", model="qwen3.5:1.7b")
        file_data = _read_config_file()
        assert _profiles(file_data)[OLLAMA_PROFILE]["base_url"] == "http://new-ollama:11434"
        assert _profiles(file_data)[OLLAMA_PROFILE]["model"] == "qwen3.5:1.7b"
        assert _profiles(file_data)[OLLAMA_PROFILE]["api_key"] == ""

    def test_update_api_key(self, two_profile_config):
        update_profile(OLLAMA_PROFILE, api_key="sk-new-key")
        file_data = _read_config_file()
        assert _profiles(file_data)[OLLAMA_PROFILE]["api_key"] == "sk-new-key"

    def test_update_default_rejected(self, two_profile_config):
        with pytest.raises(ValueError, match="cannot be updated"):
            update_profile(DEFAULT_PROFILE, model="other-model")

    def test_update_all_fields(self, two_profile_config):
        update_profile(OLLAMA_PROFILE, base_url="http://x", api_key="k", model="m")
        file_data = _read_config_file()
        p = _profiles(file_data)[OLLAMA_PROFILE]
        assert p["base_url"] == "http://x"
        assert p["api_key"] == "k"
        assert p["model"] == "m"

    def test_update_rejects_empty_base_url(self, two_profile_config):
        with pytest.raises(ValueError, match="base_url cannot be empty"):
            update_profile(OLLAMA_PROFILE, base_url="")

    def test_update_rejects_empty_model(self, two_profile_config):
        with pytest.raises(ValueError, match="model cannot be empty"):
            update_profile(OLLAMA_PROFILE, model="")

    def test_update_allows_empty_api_key(self, two_profile_config):
        """api_key can be set to empty (e.g. local Ollama needs no key)."""
        update_profile(OLLAMA_PROFILE, api_key="")
        file_data = _read_config_file()
        assert _profiles(file_data)[OLLAMA_PROFILE]["api_key"] == ""

    def test_update_nonexistent_raises(self, two_profile_config):
        with pytest.raises(ValueError, match="not found"):
            update_profile("nope", model="x")

    def test_update_no_fields_raises(self, two_profile_config):
        with pytest.raises(ValueError, match="No fields to update"):
            update_profile(OLLAMA_PROFILE)

    def test_update_preserves_other_profiles(self, two_profile_config):
        update_profile(OLLAMA_PROFILE, model="qwen3.5:1.7b")
        file_data = _read_config_file()
        assert _profiles(file_data)[DEFAULT_PROFILE]["model"] == DEFAULTS["model"]

    def test_update_reflects_in_profile(self, two_profile_config):
        set_cli_overrides(profile=OLLAMA_PROFILE)
        update_profile(OLLAMA_PROFILE, model="qwen3.5:updated")
        profile = get_profile()
        assert profile.model == "qwen3.5:updated"


class TestRemoveProfile:
    def test_remove_non_active(self, two_profile_config):
        add_profile("scratch", base_url="http://scratch", model="scratch-model")
        remove_profile("scratch")
        names = get_profile_names()
        assert "scratch" not in names

    def test_remove_default_always_fails(self, two_profile_config):
        """'default' cannot be removed even when it's not the active profile."""
        set_active_profile(OLLAMA_PROFILE)
        with pytest.raises(ValueError, match="cannot be removed"):
            remove_profile(DEFAULT_PROFILE)

    def test_remove_default_shows_alternatives(self, two_profile_config):
        with pytest.raises(ValueError, match="mm profile update ollama"):
            remove_profile(DEFAULT_PROFILE)

    def test_remove_ollama_always_fails(self, two_profile_config):
        with pytest.raises(ValueError, match="cannot be removed"):
            remove_profile(OLLAMA_PROFILE)

    def test_remove_active_non_default_raises(self, two_profile_config):
        add_profile("scratch", base_url="http://scratch", model="scratch-model")
        set_active_profile("scratch")
        with pytest.raises(ValueError, match="Cannot remove the active profile"):
            remove_profile("scratch")

    def test_remove_nonexistent_raises(self, two_profile_config):
        with pytest.raises(ValueError, match="not found"):
            remove_profile("nope")


class TestSetActiveProfile:
    def test_switch_profile(self, two_profile_config):
        set_active_profile(OLLAMA_PROFILE)
        file_data = _read_config_file()
        assert _active_profile(file_data) == OLLAMA_PROFILE

    def test_switch_nonexistent_raises(self, two_profile_config):
        with pytest.raises(ValueError, match="not found"):
            set_active_profile("nope")

    def test_switch_then_get_profile(self, two_profile_config):
        set_active_profile(OLLAMA_PROFILE)
        profile = get_profile()
        assert profile.base_url == OLLAMA_DEFAULTS["base_url"]


# ── Write with profiles ────────────────────────────────────────────


class TestWriteFullConfigWithProfiles:
    def test_write_preserves_default_profile_when_ollama_is_active(self, two_profile_config):
        write_full_config(
            cast(
                ConfigData,
                {
                    "active_profile": OLLAMA_PROFILE,
                    "profile": {
                        OLLAMA_PROFILE: cast(
                            ProfileData,
                            {"base_url": "http://new-ollama", "api_key": "", "model": "new-model"},
                        )
                    },
                },
            )
        )
        file_data = _read_config_file()
        assert _profiles(file_data)[DEFAULT_PROFILE] == DEFAULTS
        assert _profiles(file_data)[OLLAMA_PROFILE]["base_url"] == "http://new-ollama"

    def test_write_to_active_profile(self, two_profile_config):
        write_full_config(
            cast(
                ConfigData,
                {
                    "active_profile": OLLAMA_PROFILE,
                    "profile": {
                        OLLAMA_PROFILE: cast(
                            ProfileData,
                            {
                                "base_url": "http://updated-ollama",
                                "api_key": "new-key",
                                "model": "new-ollama-model",
                            },
                        )
                    },
                },
            )
        )
        file_data = _read_config_file()
        assert _profiles(file_data)[OLLAMA_PROFILE]["base_url"] == "http://updated-ollama"


class TestWriteFullConfig:
    def test_roundtrip(self, tmp_path):
        data: ConfigData = cast(
            ConfigData,
            {
                "active_profile": DEFAULT_PROFILE,
                "profile": {
                    DEFAULT_PROFILE: {"base_url": "http://a", "api_key": "", "model": "m1"},
                    "other": {"base_url": "http://b", "api_key": "k", "model": "m2"},
                },
                "mode": {
                    "fast": {"whisper_model": "tiny", "audio_speed": 2.0},
                },
            },
        )
        write_full_config(data)
        reread = _read_config_file()
        assert _active_profile(reread) == DEFAULT_PROFILE
        assert _profiles(reread)[DEFAULT_PROFILE] == DEFAULTS
        assert _profiles(reread)[OLLAMA_PROFILE]["model"] == OLLAMA_DEFAULTS["model"]
        assert _profiles(reread)["other"]["model"] == "m2"
        assert _mode_whisper_model(reread, "fast") == "tiny"


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
        result = cli_runner.invoke(app, ["profile", "list", "--format", "tsv"])
        assert result.exit_code == 0
        assert DEFAULT_PROFILE in result.output
        assert OLLAMA_PROFILE in result.output
        assert "default" in result.output

    def test_profile_list_json(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile", "list", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["active"] == DEFAULT_PROFILE
        assert DEFAULT_PROFILE in data["profiles"]
        assert OLLAMA_PROFILE in data["profiles"]
        assert data["profiles"]["default"]["api_key"] == DEFAULTS["api_key"]

    def test_profile_list_csv(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile", "list", "--format", "csv"])
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
        result2 = cli_runner.invoke(app, ["profile", "list", "--format", "json"])
        data = json.loads(result2.output)
        assert "openai" in data["profiles"]

    def test_profile_add_duplicate_fails(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(
            app, ["profile", "add", DEFAULT_PROFILE, "--base-url", "http://dup", "--model", "dup-m"]
        )
        assert result.exit_code == 1

    def test_profile_use(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile", "use", OLLAMA_PROFILE])
        assert result.exit_code == 0
        assert "Switched" in result.output
        # Verify via profile list
        result2 = cli_runner.invoke(app, ["profile", "list", "--format", "json"])
        data = json.loads(result2.output)
        assert data["active"] == OLLAMA_PROFILE

    def test_profile_use_nonexistent_fails(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile", "use", "nope"])
        assert result.exit_code == 1

    def test_profile_update_single_field(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(
            app, ["profile", "update", OLLAMA_PROFILE, "--model", "qwen3.5:latest"]
        )
        assert result.exit_code == 0
        assert "Updated" in result.output
        assert "model=qwen3.5:latest" in result.output
        # Verify change persisted
        result2 = cli_runner.invoke(app, ["profile", "list", "--format", "json"])
        data = json.loads(result2.output)
        assert data["profiles"][OLLAMA_PROFILE]["model"] == "qwen3.5:latest"

    def test_profile_update_multiple_fields(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(
            app,
            [
                "profile",
                "update",
                OLLAMA_PROFILE,
                "--model",
                "qwen3.5:1.7b",
                "--base-url",
                "http://new:11434",
            ],
        )
        assert result.exit_code == 0
        assert "model=qwen3.5:1.7b" in result.output
        assert "base_url=http://new:11434" in result.output

    def test_profile_update_api_key_masked(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(
            app, ["profile", "update", OLLAMA_PROFILE, "--api-key", "sk-secret"]
        )
        assert result.exit_code == 0
        assert "api_key=••••" in result.output
        assert "sk-secret" not in result.output

    def test_profile_update_default_fails(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile", "update", DEFAULT_PROFILE, "--model", "other"])
        assert result.exit_code == 1
        assert "cannot be updated" in result.output

    def test_profile_update_nonexistent_fails(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile", "update", "nope", "--model", "x"])
        assert result.exit_code == 1

    def test_profile_update_no_fields_fails(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile", "update", "default"])
        assert result.exit_code == 1

    def test_profile_remove(self, runner, two_profile_config):
        cli_runner, app = runner
        add_result = cli_runner.invoke(
            app,
            [
                "profile",
                "add",
                "scratch",
                "--base-url",
                "http://scratch",
                "--model",
                "scratch-model",
            ],
        )
        assert add_result.exit_code == 0
        result = cli_runner.invoke(app, ["profile", "remove", "scratch"])
        assert result.exit_code == 0
        assert "Removed" in result.output
        result2 = cli_runner.invoke(app, ["profile", "list", "--format", "json"])
        data = json.loads(result2.output)
        assert "scratch" not in data["profiles"]

    def test_profile_remove_default_fails_with_guidance(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile", "remove", DEFAULT_PROFILE])
        assert result.exit_code == 1
        assert "cannot be removed" in result.output
        assert "mm profile update ollama" in result.output

    def test_profile_flag_override(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(
            app, ["--profile", OLLAMA_PROFILE, "profile", "list", "--format", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["active"] == OLLAMA_PROFILE
        assert data["profiles"][OLLAMA_PROFILE]["base_url"] == OLLAMA_DEFAULTS["base_url"]

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

    def test_config_set_rejects_profile_keys(self, runner, two_profile_config):
        """config set should reject profile fields as unknown keys."""
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["config", "set", "base_url", "http://x"])
        assert result.exit_code == 1
        assert "unknown key" in result.output.lower()

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
        r = cli_runner.invoke(app, ["profile", "use", "test-p"])
        assert r.exit_code == 0
        # Verify active + updated values
        r = cli_runner.invoke(app, ["profile", "list", "--format", "json"])
        data = json.loads(r.output)
        assert data["active"] == "test-p"
        assert data["profiles"]["test-p"]["model"] == "test-m-v2"
        # Switch back before removing
        r = cli_runner.invoke(app, ["profile", "use", DEFAULT_PROFILE])
        assert r.exit_code == 0
        # Remove
        r = cli_runner.invoke(app, ["profile", "remove", "test-p"])
        assert r.exit_code == 0
        # Gone
        r = cli_runner.invoke(app, ["profile", "list", "--format", "json"])
        data = json.loads(r.output)
        assert "test-p" not in data["profiles"]

    def test_profile_help_shows_all_subcommands(self, runner):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile", "--help"])
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

    def test_env_profile_selects_profile(self, runner, two_profile_config, monkeypatch):
        monkeypatch.setenv("MM_PROFILE", OLLAMA_PROFILE)
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile", "list", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["active"] == OLLAMA_PROFILE
        assert data["profiles"][OLLAMA_PROFILE]["base_url"] == OLLAMA_DEFAULTS["base_url"]
