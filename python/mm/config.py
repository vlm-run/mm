"""Configuration management for mm.

Config file locations (checked in order, first found wins):
  1. ~/.config/mm/mm.toml   (XDG-compliant, preferred)
  2. ~/.mm/config.toml          (legacy, still supported)


The config file also supports [mode.fast] and [mode.accurate] sections
for per-mode defaults (whisper model, audio speed, etc.).
"""

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal, TypedDict, cast

from mm.common.audio._base import BackendLabel
from mm.settings import get_settings

# ── Config paths ────────────────────────────────────────────────────

CONFIG_DIR_LEGACY = Path.home() / ".mm"
CONFIG_PATH_LEGACY = CONFIG_DIR_LEGACY / "config.toml"


def __getattr__(name: str) -> Path:
    """Resolve the XDG config paths live from :class:`~mm.settings.MmSettings`."""
    if name in ("CONFIG_DIR_XDG", "CONFIG_DIR"):
        return get_settings().config_dir
    if name in ("CONFIG_PATH_XDG", "CONFIG_PATH"):
        return get_settings().config_dir / "mm.toml"
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _find_config_path() -> Path:
    """Return the first existing config path, or the XDG path as default."""
    xdg_path = sys.modules[__name__].CONFIG_PATH_XDG
    if xdg_path.exists():
        return xdg_path
    if CONFIG_PATH_LEGACY.exists():
        return CONFIG_PATH_LEGACY
    return xdg_path


# ── Defaults ────────────────────────────────────────────────────────


class ProfileData(TypedDict):
    base_url: str
    api_key: str
    model: str


class ModeData(TypedDict, total=False):
    whisper_model: str
    audio_speed: float
    beam_size: int


class TranscriptionData(TypedDict, total=False):
    backend: BackendLabel
    base_url: str
    api_key: str


class ConfigData(TypedDict, total=False):
    active_profile: str
    profile: dict[str, ProfileData]
    mode: dict[str, ModeData]
    pipelines: dict[str, dict[str, str]]
    transcription: TranscriptionData


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
class TranscriptionConfig:
    """Transcription backend settings.

    Resolved from ``[transcription]`` in mm.toml.  All fields are
    ``None`` by default, meaning auto-detect / not configured.

    Set via::

        mm config set transcription.backend openai
        mm config set transcription.base_url http://localhost:11434/v1
    """

    backend: BackendLabel | None = None
    base_url: str | None = None
    api_key: str | None = None


@dataclass
class VlmctxConfig:
    """Full resolved configuration."""

    mode_fast: ModeConfig = field(default_factory=lambda: replace(_MODE_DEFAULTS["fast"]))
    mode_accurate: ModeConfig = field(default_factory=lambda: replace(_MODE_DEFAULTS["accurate"]))
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)


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


def get_transcription_config() -> TranscriptionConfig:
    """Resolve transcription settings from ``[transcription]`` in mm.toml.

    Returns:
        TranscriptionConfig with backend, base_url, and api_key.
    """
    file_data = _read_config_file()
    section = file_data.get("transcription", {})
    backend: BackendLabel | None = section.get("backend") or None
    return TranscriptionConfig(
        backend=backend,
        base_url=section.get("base_url") or None,
        api_key=section.get("api_key") or None,
    )


def get_pipeline_path(kind: str, mode: str) -> str | None:
    """Return a user-configured pipeline YAML path from ``[pipelines]`` in mm.toml.

    Example TOML section::

        [pipelines]
        image.fast = "~/.config/mm/pipelines/image/fast.yaml"

    Returns:
        Expanded absolute path string, or ``None`` if not configured.
    """
    file_data = _read_config_file()
    pipelines_section = file_data.get("pipelines", {})
    kind_section = pipelines_section.get(kind, {})
    raw_path = kind_section.get(mode)
    if raw_path:
        return str(Path(raw_path).expanduser().resolve())
    return None


def get_full_config() -> VlmctxConfig:
    """Return the full resolved configuration."""
    return VlmctxConfig(
        mode_fast=get_mode_config("fast"),
        mode_accurate=get_mode_config("accurate"),
        transcription=get_transcription_config(),
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

    # [transcription] section
    tx = file_data.get("transcription", {})
    if tx:
        lines.append("[transcription]")
        for tk in ("backend", "base_url", "api_key"):
            if val := tx.get(tk):
                lines.append(f'{tk} = "{_toml_str(str(val))}"')
        lines.append("")

    path = _find_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


def write_platform_config() -> Path:
    """Write the default config with built-in profiles and mode sections."""
    from mm.profile import DEFAULT_PROFILE, get_default_profiles

    return write_full_config(
        cast(
            ConfigData,
            {
                "active_profile": DEFAULT_PROFILE,
                "profile": get_default_profiles(),
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


def update_config_key(key: str, value: str) -> Path:
    """Update a config key (e.g. ``mode.fast.whisper_model``, ``transcription.backend``).

    Supports:
      - ``mode.<fast|accurate>.<field>`` — per-mode settings
      - ``transcription.<backend|base_url|api_key>`` — transcription backend settings

    Returns the path to the written config file.
    """
    from mm.profile import load_profile_config

    file_data = load_profile_config()
    parts = key.split(".")

    if parts[0] == "mode" and len(parts) == 3:
        mode_name, fld = parts[1], parts[2]
        if mode_name not in ("fast", "accurate"):
            raise ValueError(f"Invalid mode key: {key}")

        if "mode" not in file_data:
            file_data["mode"] = {}
        if mode_name not in file_data["mode"]:
            file_data["mode"][mode_name] = {}

        mode_data = file_data["mode"][mode_name]
        if fld == "audio_speed":
            mode_data["audio_speed"] = float(value)
        elif fld == "beam_size":
            mode_data["beam_size"] = int(value)
        elif fld == "whisper_model":
            mode_data["whisper_model"] = value
        else:
            raise ValueError(f"Invalid mode key: {key}")

    elif parts[0] == "transcription" and len(parts) == 2:
        fld = parts[1]
        if fld not in ("backend", "base_url", "api_key"):
            raise ValueError(f"Invalid transcription key: {key}")

        if "transcription" not in file_data:
            file_data["transcription"] = {}
        tx = file_data["transcription"]
        if fld == "backend":
            tx["backend"] = cast(BackendLabel, value)
        elif fld == "base_url":
            tx["base_url"] = value
        elif fld == "api_key":
            tx["api_key"] = value

    else:
        raise ValueError(f"Invalid config key: {key}")

    return write_full_config(file_data)


def update_mode_config(key: str, value: str) -> Path:
    """Update a mode-specific key (e.g. mode.fast.whisper_model) and return path.

    .. deprecated:: Use :func:`update_config_key` instead.
    """
    return update_config_key(key, value)
