"""Tests for mm profile management.

Covers: profile CRUD (including update), active profile resolution,
builtin normalization, CLI subcommands (list/use/add/update/remove), --profile flag, MM_PROFILE env.
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
    GEMINI_DEFAULTS,
    OLLAMA_DEFAULTS,
    PROFILE_KEYS,
    RESERVED_PROFILES,
    VLMRUN_DEFAULTS,
    Profile,
    add_profile,
    get_active_profile_name,
    get_profile,
    get_profile_names,
    get_profile_section,
    remove_profile,
    set_active_profile,
    update_profile,
)

# Convenience: a non-default reserved profile for "switch-to" tests
OTHER_PROFILE = "gemini"
OTHER_DEFAULTS = GEMINI_DEFAULTS

# Profile data as stored on disk (write_full_config only writes base_url, api_key, model).
# RESERVED_DEFAULTS include "name" but TOML serialization drops it, so _read_config_file
# returns dicts without "name".
_OLLAMA_DATA = {k: v for k, v in OLLAMA_DEFAULTS.items() if k != "name"}
_GEMINI_DATA = {k: v for k, v in GEMINI_DEFAULTS.items() if k != "name"}
_VLMRUN_DATA = {k: v for k, v in VLMRUN_DEFAULTS.items() if k != "name"}


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
    """Write a config file with ollama + gemini profiles and return the path."""
    toml = """\
active_profile = "ollama"

[profile.ollama]
base_url = "http://localhost:11434"
api_key = ""
model = "qwen3.5:0.8"

[profile.gemini]
base_url = "https://openrouter.ai/api/v1"
api_key = ""
model = "google/gemini-2.5-flash-lite"
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
        monkeypatch.setenv("MM_PROFILE", OTHER_PROFILE)
        assert get_active_profile_name() == OTHER_PROFILE

    def test_cli_overrides_env(self, two_profile_config, monkeypatch):
        monkeypatch.setenv("MM_PROFILE", OTHER_PROFILE)
        set_cli_overrides(profile=DEFAULT_PROFILE)
        assert get_active_profile_name() == DEFAULT_PROFILE

    def test_cli_profile_flag(self):
        set_cli_overrides(profile="custom")
        assert get_active_profile_name() == "custom"


# ── Profile section reading ─────────────────────────────────────────


class TestGetProfileSection:
    def test_reads_named_profile(self, two_profile_config):
        file_data = _read_config_file()
        section = get_profile_section(file_data, "ollama")
        assert section["base_url"] == OLLAMA_DEFAULTS["base_url"]
        assert section["model"] == OLLAMA_DEFAULTS["model"]
        assert section["api_key"] == OLLAMA_DEFAULTS["api_key"]

    def test_returns_empty_for_missing(self, two_profile_config):
        file_data = _read_config_file()
        assert get_profile_section(file_data, "nonexistent") == {}

    def test_reads_gemini_profile(self, two_profile_config):
        file_data = _read_config_file()
        section = get_profile_section(file_data, "gemini")
        assert section["base_url"] == GEMINI_DEFAULTS["base_url"]
        assert section["model"] == GEMINI_DEFAULTS["model"]


# ── Profile names listing ───────────────────────────────────────────


class TestGetProfileNames:
    def test_lists_all_profiles(self, two_profile_config):
        names = get_profile_names()
        assert "ollama" in names
        assert "gemini" in names
        assert "vlmrun" in names

    def test_empty_config_shows_all_reserved(self):
        names = get_profile_names()
        for name in RESERVED_PROFILES:
            assert name in names


class TestBuiltinNormalization:
    def test_default_profile_is_forced_to_builtin_values(self, two_profile_config):
        profile = get_profile()
        assert profile == Profile(
            name=DEFAULT_PROFILE,
            base_url=OLLAMA_DEFAULTS["base_url"],
            api_key=OLLAMA_DEFAULTS["api_key"],
            model=OLLAMA_DEFAULTS["model"],
        )

    def test_missing_vlmrun_profile_is_added_with_defaults(self, tmp_path: Path):
        (tmp_path / "config.toml").write_text(
            """\
active_profile = "ollama"

[profile.ollama]
base_url = "http://localhost:11434"
api_key = ""
model = "qwen3.5:0.8"
"""
        )

        profile_names = get_profile_names()
        assert "vlmrun" in profile_names
        assert "gemini" in profile_names

        file_data = _read_config_file()
        assert _profiles(file_data)["vlmrun"]["base_url"] == VLMRUN_DEFAULTS["base_url"]
        assert _profiles(file_data)["vlmrun"]["model"] == VLMRUN_DEFAULTS["model"]

    def test_all_reserved_profiles_present_after_normalization(self):
        """No config file at all — all reserved profiles are created."""
        names = get_profile_names()
        for name in RESERVED_PROFILES:
            assert name in names


# ── Profile keys constant ──────────────────────────────────────────


class TestProfileKeys:
    def test_contains_expected_keys(self):
        assert PROFILE_KEYS == {"base_url", "api_key", "model"}


# ── Profile resolution with profiles ───────────────────────────────


class TestProfileResolutionWithProfiles:
    def test_default_profile_matches_actual_profile(self, two_profile_config):
        profile = get_profile()
        assert profile == Profile(
            name=DEFAULT_PROFILE,
            base_url=OLLAMA_DEFAULTS["base_url"],
            api_key=OLLAMA_DEFAULTS["api_key"],
            model=OLLAMA_DEFAULTS["model"],
        )

    def test_switched_profile_matches_actual_profile(self, two_profile_config):
        set_cli_overrides(profile=OTHER_PROFILE)
        profile = get_profile()
        assert profile == Profile(
            name=OTHER_PROFILE,
            base_url=GEMINI_DEFAULTS["base_url"],
            api_key=GEMINI_DEFAULTS["api_key"],
            model=GEMINI_DEFAULTS["model"],
        )

    def test_env_profile_matches_actual_profile(self, two_profile_config, monkeypatch):
        monkeypatch.setenv("MM_PROFILE", OTHER_PROFILE)
        profile = get_profile()
        assert profile == Profile(
            name=OTHER_PROFILE,
            base_url=GEMINI_DEFAULTS["base_url"],
            api_key=GEMINI_DEFAULTS["api_key"],
            model=GEMINI_DEFAULTS["model"],
        )

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
        assert profile == Profile(
            name=DEFAULT_PROFILE,
            base_url=OLLAMA_DEFAULTS["base_url"],
            api_key=OLLAMA_DEFAULTS["api_key"],
            model=OLLAMA_DEFAULTS["model"],
        )


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
            add_profile("gemini", base_url="http://dup", model="dup-m")

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

    def test_add_to_empty_config(self, tmp_path: Path):
        add_profile("newone", base_url="http://new:9000", model="new-m")
        names = get_profile_names()
        for name in RESERVED_PROFILES:
            assert name in names
        assert "newone" in names


class TestUpdateProfile:
    def test_update_single_field(self, two_profile_config):
        update_profile("gemini", model="gemini-2.0-flash")
        file_data = _read_config_file()
        assert _profiles(file_data)["gemini"]["model"] == "gemini-2.0-flash"
        # Other fields preserved
        assert _profiles(file_data)["gemini"]["base_url"] == GEMINI_DEFAULTS["base_url"]
        assert _profiles(file_data)["gemini"]["api_key"] == ""

    def test_update_multiple_fields(self, two_profile_config):
        update_profile("gemini", base_url="http://new-gemini:8000", model="gemini-2.0")
        file_data = _read_config_file()
        assert _profiles(file_data)["gemini"]["base_url"] == "http://new-gemini:8000"
        assert _profiles(file_data)["gemini"]["model"] == "gemini-2.0"
        assert _profiles(file_data)["gemini"]["api_key"] == ""

    def test_update_api_key(self, two_profile_config):
        update_profile("gemini", api_key="sk-new-key")
        file_data = _read_config_file()
        assert _profiles(file_data)["gemini"]["api_key"] == "sk-new-key"

    def test_update_immutable_rejected(self, two_profile_config):
        with pytest.raises(ValueError, match="cannot be modified"):
            update_profile("vlmrun", model="other-model")

    def test_update_ollama_allowed(self, two_profile_config):
        """ollama is reserved but mutable — update should succeed."""
        update_profile("ollama", model="qwen3.5:1.7b")
        file_data = _read_config_file()
        assert _profiles(file_data)["ollama"]["model"] == "qwen3.5:1.7b"

    def test_update_all_fields(self, two_profile_config):
        update_profile("gemini", base_url="http://x", api_key="k", model="m")
        file_data = _read_config_file()
        p = _profiles(file_data)["gemini"]
        assert p["base_url"] == "http://x"
        assert p["api_key"] == "k"
        assert p["model"] == "m"

    def test_update_rejects_empty_base_url(self, two_profile_config):
        with pytest.raises(ValueError, match="base_url cannot be empty"):
            update_profile("gemini", base_url="")

    def test_update_rejects_empty_model(self, two_profile_config):
        with pytest.raises(ValueError, match="model cannot be empty"):
            update_profile("gemini", model="")

    def test_update_allows_empty_api_key(self, two_profile_config):
        """api_key can be set to empty (e.g. local Ollama needs no key)."""
        update_profile("gemini", api_key="")
        file_data = _read_config_file()
        assert _profiles(file_data)["gemini"]["api_key"] == ""

    def test_update_nonexistent_raises(self, two_profile_config):
        with pytest.raises(ValueError, match="not found"):
            update_profile("nope", model="x")

    def test_update_no_fields_raises(self, two_profile_config):
        with pytest.raises(ValueError, match="No fields to update"):
            update_profile("gemini")

    def test_update_preserves_other_profiles(self, two_profile_config):
        update_profile("gemini", model="gemini-2.0")
        file_data = _read_config_file()
        assert _profiles(file_data)["ollama"]["model"] == OLLAMA_DEFAULTS["model"]

    def test_update_reflects_in_profile(self, two_profile_config):
        set_cli_overrides(profile="gemini")
        update_profile("gemini", model="gemini-updated")
        profile = get_profile()
        assert profile.model == "gemini-updated"


class TestRemoveProfile:
    def test_remove_non_reserved(self, two_profile_config):
        add_profile("scratch", base_url="http://scratch", model="scratch-model")
        remove_profile("scratch")
        names = get_profile_names()
        assert "scratch" not in names

    def test_remove_ollama_fails(self, two_profile_config):
        """Reserved profiles cannot be removed."""
        with pytest.raises(ValueError, match="cannot be removed"):
            remove_profile("ollama")

    def test_remove_gemini_fails(self, two_profile_config):
        with pytest.raises(ValueError, match="cannot be removed"):
            remove_profile("gemini")

    def test_remove_vlmrun_fails(self, two_profile_config):
        with pytest.raises(ValueError, match="cannot be removed"):
            remove_profile("vlmrun")

    def test_remove_active_non_reserved_raises(self, two_profile_config):
        add_profile("scratch", base_url="http://scratch", model="scratch-model")
        set_active_profile("scratch")
        with pytest.raises(ValueError, match="Cannot remove the active profile"):
            remove_profile("scratch")

    def test_remove_nonexistent_raises(self, two_profile_config):
        with pytest.raises(ValueError, match="not found"):
            remove_profile("nope")


class TestSetActiveProfile:
    def test_switch_profile(self, two_profile_config):
        set_active_profile("gemini")
        file_data = _read_config_file()
        assert _active_profile(file_data) == "gemini"

    def test_switch_nonexistent_raises(self, two_profile_config):
        with pytest.raises(ValueError, match="not found"):
            set_active_profile("nope")

    def test_switch_then_get_profile(self, two_profile_config):
        set_active_profile("gemini")
        profile = get_profile()
        assert profile.base_url == GEMINI_DEFAULTS["base_url"]


# ── Write with profiles ────────────────────────────────────────────


class TestWriteFullConfigWithProfiles:
    def test_write_preserves_default_profile_when_gemini_is_active(self, two_profile_config):
        write_full_config(
            cast(
                ConfigData,
                {
                    "active_profile": "gemini",
                    "profile": {
                        "gemini": cast(
                            ProfileData,
                            {"base_url": "http://new-gemini", "api_key": "", "model": "new-model"},
                        )
                    },
                },
            )
        )
        file_data = _read_config_file()
        assert _profiles(file_data)["ollama"]["base_url"] == OLLAMA_DEFAULTS["base_url"]
        assert _profiles(file_data)["gemini"]["base_url"] == "http://new-gemini"

    def test_write_to_active_profile(self, two_profile_config):
        write_full_config(
            cast(
                ConfigData,
                {
                    "active_profile": "gemini",
                    "profile": {
                        "gemini": cast(
                            ProfileData,
                            {
                                "base_url": "http://updated-gemini",
                                "api_key": "new-key",
                                "model": "new-gemini-model",
                            },
                        )
                    },
                },
            )
        )
        file_data = _read_config_file()
        assert _profiles(file_data)["gemini"]["base_url"] == "http://updated-gemini"


class TestWriteFullConfig:
    def test_roundtrip(self, tmp_path):
        data: ConfigData = cast(
            ConfigData,
            {
                "active_profile": DEFAULT_PROFILE,
                "profile": {
                    "ollama": {"base_url": "http://a", "api_key": "", "model": "m1"},
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
        # ollama is mutable — user values preserved after roundtrip
        assert _profiles(reread)["ollama"]["model"] == "m1"
        assert _profiles(reread)["vlmrun"]["model"] == VLMRUN_DEFAULTS["model"]
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
        assert "gemini" in result.output
        assert "ollama" in result.output

    def test_profile_list_json(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile", "list", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["active"] == DEFAULT_PROFILE
        assert "ollama" in data["profiles"]
        assert "gemini" in data["profiles"]

    def test_profile_list_csv(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile", "list", "--format", "csv"])
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        assert lines[0] == "profile,active,base_url,model"
        # header + 3 reserved profiles (ollama, gemini, vlmrun)
        assert len(lines) >= 4

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
        result = cli_runner.invoke(app, ["profile", "use", "gemini"])
        assert result.exit_code == 0
        assert "Switched" in result.output
        # Verify via profile list
        result2 = cli_runner.invoke(app, ["profile", "list", "--format", "json"])
        data = json.loads(result2.output)
        assert data["active"] == "gemini"

    def test_profile_use_nonexistent_fails(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile", "use", "nope"])
        assert result.exit_code == 1

    def test_profile_update_single_field(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(
            app, ["profile", "update", "gemini", "--model", "gemini-2.0-flash"]
        )
        assert result.exit_code == 0
        assert "Updated" in result.output
        assert "model=gemini-2.0-flash" in result.output
        # Verify change persisted
        result2 = cli_runner.invoke(app, ["profile", "list", "--format", "json"])
        data = json.loads(result2.output)
        assert data["profiles"]["gemini"]["model"] == "gemini-2.0-flash"

    def test_profile_update_multiple_fields(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(
            app,
            [
                "profile",
                "update",
                "gemini",
                "--model",
                "gemini-2.0",
                "--base-url",
                "http://new:8000",
            ],
        )
        assert result.exit_code == 0
        assert "model=gemini-2.0" in result.output
        assert "base_url=http://new:8000" in result.output

    def test_profile_update_api_key_masked(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile", "update", "gemini", "--api-key", "sk-secret"])
        assert result.exit_code == 0
        assert "api_key=\u2022\u2022\u2022\u2022" in result.output
        assert "sk-secret" not in result.output

    def test_profile_update_immutable_fails(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile", "update", "vlmrun", "--model", "other"])
        assert result.exit_code == 1
        assert "cannot be modified" in result.output

    def test_profile_update_nonexistent_fails(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile", "update", "nope", "--model", "x"])
        assert result.exit_code == 1

    def test_profile_update_no_fields_fails(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile", "update", "gemini"])
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

    def test_profile_remove_reserved_fails_with_guidance(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile", "remove", "ollama"])
        assert result.exit_code == 1
        assert "cannot be removed" in result.output
        assert "mm profile update" in result.output

    def test_profile_flag_override(self, runner, two_profile_config):
        cli_runner, app = runner
        result = cli_runner.invoke(
            app, ["--profile", "gemini", "profile", "list", "--format", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["active"] == "gemini"
        assert data["profiles"]["gemini"]["base_url"] == GEMINI_DEFAULTS["base_url"]

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
        monkeypatch.setenv("MM_PROFILE", "gemini")
        cli_runner, app = runner
        result = cli_runner.invoke(app, ["profile", "list", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["active"] == "gemini"
        assert data["profiles"]["gemini"]["base_url"] == GEMINI_DEFAULTS["base_url"]
