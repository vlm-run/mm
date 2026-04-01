"""Configuration management for mm.

Config file locations (checked in order, first found wins):
  1. ~/.config/mm/mm.toml   (XDG-compliant, preferred)
  2. ~/.mm/config.toml          (legacy, still supported)


The config file also supports [mode.fast] and [mode.accurate] sections
for per-mode defaults (whisper model, audio speed, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal, TypedDict, cast

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

# ── Config paths ────────────────────────────────────────────────────

CONFIG_DIR_XDG = Path.home() / ".config" / "mm"
CONFIG_PATH_XDG = CONFIG_DIR_XDG / "mm.toml"
CONFIG_DIR_LEGACY = Path.home() / ".mm"
CONFIG_PATH_LEGACY = CONFIG_DIR_LEGACY / "config.toml"


def _find_config_path() -> Path:
    """Return the first existing config path, or the XDG path as default."""
    if CONFIG_PATH_XDG.exists():
        return CONFIG_PATH_XDG
    if CONFIG_PATH_LEGACY.exists():
        return CONFIG_PATH_LEGACY
    return CONFIG_PATH_XDG


# Expose for display / init commands
CONFIG_DIR = CONFIG_DIR_XDG
CONFIG_PATH = CONFIG_PATH_XDG

# ── Defaults ────────────────────────────────────────────────────────


class ProfileData(TypedDict):
    base_url: str
    api_key: str
    model: str


class ModeData(TypedDict, total=False):
    whisper_model: str
    audio_speed: float
    beam_size: int


class ConfigData(TypedDict, total=False):
    active_profile: str
    profile: dict[str, ProfileData]
    mode: dict[str, ModeData]


WhisperModel = Literal["tiny", "medium"]  # can extend with more sizes if needed


@dataclass
class ModeConfig:
    """Per-mode extraction settings."""

    whisper_model: WhisperModel = "tiny"
    audio_speed: float = 0.0  # 0 = not set, use default
    beam_size: int = 0  # 0 = not set, use default


Mode = Literal["fast", "accurate"]

# Platform-aware mode defaults
_MODE_DEFAULTS: dict[Mode, ModeConfig] = {
    "fast": ModeConfig(whisper_model="tiny", audio_speed=2.0, beam_size=1),
    "accurate": ModeConfig(whisper_model="medium", audio_speed=1.0, beam_size=5),
}


@dataclass
class VlmctxConfig:
    """Full resolved configuration."""

    mode_fast: ModeConfig = field(default_factory=lambda: replace(_MODE_DEFAULTS["fast"]))
    mode_accurate: ModeConfig = field(default_factory=lambda: replace(_MODE_DEFAULTS["accurate"]))


# ── CLI overrides ───────────────────────────────────────────────────


@dataclass
class _CliOverrides:
    """Mutable store for CLI-level --profile flag."""

    profile: str | None = None


_cli_overrides = _CliOverrides()


def set_cli_overrides(
    profile: str | None = None,
) -> None:
    _cli_overrides.profile = profile


# ── File reading ────────────────────────────────────────────────────


def _read_config_file() -> ConfigData:
    try:
        if (path := _find_config_path()) and path.exists():
            return cast(ConfigData, dict(tomllib.loads(path.read_text())))
    except Exception:
        pass
    return cast(ConfigData, {})


# ── Public API ──────────────────────────────────────────────────────


def get_mode_config(mode: Mode) -> ModeConfig:
    """Resolve mode-specific settings from config file, falling back to defaults.

    Args:
        mode: "fast" or "accurate"

    Returns:
        ModeConfig with whisper_model and audio_speed.
    """
    file_data = _read_config_file()
    mode_section = file_data.get("mode", {}).get(mode, {})
    defaults = _MODE_DEFAULTS.get(mode, ModeConfig())

    return ModeConfig(
        whisper_model=cast(WhisperModel, mode_section.get("whisper_model", defaults.whisper_model)),
        audio_speed=float(mode_section.get("audio_speed", defaults.audio_speed)),
        beam_size=int(mode_section.get("beam_size", defaults.beam_size)),
    )


def get_full_config() -> VlmctxConfig:
    """Return the full resolved configuration."""
    return VlmctxConfig(
        mode_fast=get_mode_config("fast"),
        mode_accurate=get_mode_config("accurate"),
    )


# ── Serialization ──────────────────────────────────────────────────


def _toml_str(value: str) -> str:
    """Escape a string for TOML double-quoted format."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def write_full_config(file_data: ConfigData) -> Path:
    """Serialize full config dict back to TOML and write to disk. Returns path."""
    from mm.profile import DEFAULT_PROFILE, ensure_builtin_profiles

    ensure_builtin_profiles(file_data)
    lines: list[str] = []

    # Top-level active_profile
    active = file_data.get("active_profile", DEFAULT_PROFILE)
    lines.append(f'active_profile = "{_toml_str(active)}"')
    lines.append("")

    # [profile.*] sections
    profiles = file_data.get("profile", {})
    for name in sorted(profiles.keys()):
        p = profiles[name]
        lines.append(f"[profile.{name}]")
        for k in ("base_url", "api_key", "model"):
            if k in p:
                lines.append(f'{k} = "{_toml_str(p[k])}"')
        lines.append("")

    # [mode.*] sections
    for m in ("fast", "accurate"):
        mode_data = file_data.get("mode", {}).get(m, {})
        if mode_data:
            lines.append(f"[mode.{m}]")
            for mk, mv in mode_data.items():
                if isinstance(mv, (int, float)):
                    lines.append(f"{mk} = {mv}")
                else:
                    lines.append(f'{mk} = "{_toml_str(str(mv))}"')
            lines.append("")

    path = _find_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


def write_platform_config() -> Path:
    """Write the default config with built-in profiles and mode sections."""
    from mm.profile import DEFAULT_PROFILE, get_builtin_profile_defaults

    return write_full_config(
        cast(
            ConfigData,
            {
                "active_profile": DEFAULT_PROFILE,
                "profile": get_builtin_profile_defaults(),
                "mode": {
                    "fast": {
                        "whisper_model": _MODE_DEFAULTS["fast"].whisper_model,
                        "audio_speed": _MODE_DEFAULTS["fast"].audio_speed,
                        "beam_size": _MODE_DEFAULTS["fast"].beam_size,
                    },
                    "accurate": {
                        "whisper_model": _MODE_DEFAULTS["accurate"].whisper_model,
                        "audio_speed": _MODE_DEFAULTS["accurate"].audio_speed,
                        "beam_size": _MODE_DEFAULTS["accurate"].beam_size,
                    },
                },
            },
        )
    )


def update_mode_config(key: str, value: str) -> Path:
    """Update a mode-specific key (e.g. mode.fast.whisper_model) and return path."""
    from mm.profile import load_profile_config

    file_data = load_profile_config()

    parts = key.split(".")
    if len(parts) != 3 or parts[0] != "mode":
        raise ValueError(f"Invalid mode key: {key}")

    mode_name, field = parts[1], parts[2]
    if mode_name not in ("fast", "accurate"):
        raise ValueError(f"Invalid mode key: {key}")

    if "mode" not in file_data:
        file_data["mode"] = {}
    if mode_name not in file_data["mode"]:
        file_data["mode"][mode_name] = {}

    mode_data = file_data["mode"][mode_name]

    if field == "audio_speed":
        mode_data["audio_speed"] = float(value)
    elif field == "beam_size":
        mode_data["beam_size"] = int(value)
    elif field == "whisper_model":
        mode_data["whisper_model"] = value
    else:
        raise ValueError(f"Invalid mode key: {key}")

    return write_full_config(file_data)
