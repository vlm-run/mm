"""Configuration management for mm.

Config file locations (checked in order, first found wins):
  1. ~/.config/mm/mm.toml   (XDG-compliant, preferred)
  2. ~/.mm/config.toml          (legacy, still supported)

Resolution order for provider settings (highest priority first):
  1. CLI flags (--base-url, --api-key, --model, --profile)
  2. Environment variables (MM_BASE_URL, MM_PROFILE, etc.)
  3. Config file [profile.<name>] section (active profile)
  4. Built-in defaults (local Ollama)

Profiles allow multiple provider configurations in a single config file.
See mm.profile for profile management (CRUD, migration, resolution).

Legacy [provider] sections are treated as [profile.default] for backward
compatibility.

The config file also supports [mode.fast] and [mode.accurate] sections
for per-mode defaults (whisper model, audio speed, etc.).
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

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

_SYSTEM = platform.system().lower()  # "darwin", "linux", "windows"

DEFAULTS = {
    "base_url": "http://localhost:11434",
    "api_key": "",
    "model": "qwen3.5:0.8b",
}

ENV_VARS = {
    "base_url": "MM_BASE_URL",
    "api_key": "MM_API_KEY",
    "model": "MM_MODEL",
}

ENV_PROFILE = "MM_PROFILE"


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
class ProviderConfig:
    base_url: str = DEFAULTS["base_url"]
    api_key: str = DEFAULTS["api_key"]
    model: str = DEFAULTS["model"]


@dataclass
class VlmctxConfig:
    """Full resolved configuration."""

    provider: ProviderConfig = field(default_factory=ProviderConfig)
    mode_fast: ModeConfig = field(default_factory=lambda: replace(_MODE_DEFAULTS["fast"]))
    mode_accurate: ModeConfig = field(default_factory=lambda: replace(_MODE_DEFAULTS["accurate"]))


# ── Template ────────────────────────────────────────────────────────

TEMPLATE_DARWIN = """\
# mm configuration — macOS
# Docs: https://github.com/autonomi-ai/mm
#
# Profiles let you store multiple provider configs in one file.
# Switch with: mm config profile use <name>
# Or per-command: mm --profile vlmrun cat photo.png -l 2

active_profile = "default"

[profile.default]
base_url = "http://localhost:11434"   # Ollama default
api_key = ""
model = "qwen3.5:0.8b"               # Ollama model tag

# [profile.vlmrun]
# base_url = "https://api.vlm.run/v1"
# api_key = ""
# model = "vlm-1"

# [profile.openai]
# base_url = "https://api.openai.com/v1"
# api_key = ""
# model = "gpt-4o"

[mode.fast]
whisper_model = "tiny"                # faster-whisper model size
audio_speed = 2.0                     # 2x speedup for fast transcription
beam_size = 1                         # greedy decoding (fastest)

[mode.accurate]
whisper_model = "medium"              # higher quality transcription
audio_speed = 1.0                     # no speedup
beam_size = 5                         # beam search (best quality)
"""

TEMPLATE_LINUX = """\
# mm configuration — Linux (vLLM)
# Docs: https://github.com/autonomi-ai/mm
#
# Profiles let you store multiple provider configs in one file.
# Switch with: mm config profile use <name>
# Or per-command: mm --profile vlmrun cat photo.png -l 2

active_profile = "default"

[profile.default]
base_url = "http://localhost:8000"    # vLLM default
api_key = ""
model = "Qwen/Qwen3.5-0.8B"          # HuggingFace model ID

# [profile.vlmrun]
# base_url = "https://api.vlm.run/v1"
# api_key = ""
# model = "vlm-1"

[mode.fast]
whisper_model = "tiny"                # faster-whisper model size
audio_speed = 2.0                     # 2x speedup for fast transcription
beam_size = 1                         # greedy decoding (fastest)

[mode.accurate]
whisper_model = "medium"              # higher quality transcription
audio_speed = 1.0                     # no speedup
beam_size = 5                         # beam search (best quality)
"""


def _platform_template() -> str:
    if _SYSTEM == "linux":
        return TEMPLATE_LINUX
    return TEMPLATE_DARWIN


def _platform_defaults() -> dict[str, str]:
    """Return platform-specific provider defaults."""
    if _SYSTEM == "linux":
        return {
            "base_url": "http://localhost:8000",
            "api_key": "",
            "model": "Qwen/Qwen3.5-0.8B",
        }
    return dict(DEFAULTS)


# ── CLI overrides ───────────────────────────────────────────────────


@dataclass
class _CliOverrides:
    """Mutable store for CLI-level --base-url / --api-key / --model / --profile flags."""

    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    profile: str | None = None


_cli_overrides = _CliOverrides()


def set_cli_overrides(
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    profile: str | None = None,
) -> None:
    _cli_overrides.base_url = base_url
    _cli_overrides.api_key = api_key
    _cli_overrides.model = model
    _cli_overrides.profile = profile


# ── File reading ────────────────────────────────────────────────────


def _read_config_file() -> dict[str, Any]:
    try:
        if (path := _find_config_path()) and path.exists():
            return dict(tomllib.loads(path.read_text()))
    except Exception:
        pass
    return {}


def _resolve(key: str, file_cfg: dict[str, Any]) -> tuple[str, str]:
    """Return (value, source) for a provider key."""
    if val := getattr(_cli_overrides, key, None):
        return val, "cli"
    if val := os.environ.get(ENV_VARS[key]):
        return val, "env"
    if val := file_cfg.get(key):
        return str(val), "file"
    # Platform-specific defaults
    return _platform_defaults().get(key, DEFAULTS[key]), "default"


# ── Public API ──────────────────────────────────────────────────────


def get_provider() -> ProviderConfig:
    """Resolve provider settings: CLI flags > env vars > active profile > defaults."""
    from mm.profile import get_active_profile_name, get_profile_section

    file_data = _read_config_file()
    profile_name = get_active_profile_name()
    file_cfg = get_profile_section(file_data, profile_name)
    return ProviderConfig(
        base_url=_resolve("base_url", file_cfg)[0],
        api_key=_resolve("api_key", file_cfg)[0],
        model=_resolve("model", file_cfg)[0],
    )


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
        whisper_model=mode_section.get("whisper_model", defaults.whisper_model),
        audio_speed=float(mode_section.get("audio_speed", defaults.audio_speed)),
        beam_size=int(mode_section.get("beam_size", defaults.beam_size)),
    )


def get_full_config() -> VlmctxConfig:
    """Return the full resolved configuration."""
    return VlmctxConfig(
        provider=get_provider(),
        mode_fast=get_mode_config("fast"),
        mode_accurate=get_mode_config("accurate"),
    )


def get_provider_with_sources() -> list[tuple[str, str, str, str]]:
    """Return [(key, value, source, env_var), ...] for display."""
    from mm.profile import get_active_profile_name, get_profile_section

    file_data = _read_config_file()
    profile_name = get_active_profile_name()
    file_cfg = get_profile_section(file_data, profile_name)
    rows = []
    for key in ("base_url", "api_key", "model"):
        val, src = _resolve(key, file_cfg)
        # Annotate file source with profile name
        if src == "file":
            src = f"file ({profile_name})"
        display_val = "••••" if key == "api_key" and val and src != "default" else val
        rows.append((key, display_val, src, ENV_VARS[key]))
    return rows


# ── Write / update ──────────────────────────────────────────────────


def write_config(base_url: str, api_key: str, model: str) -> Path:
    """Write config.toml with a default profile. Returns path."""
    from mm.profile import get_active_profile_name, migrate_to_profiles, write_full_config

    file_data = _read_config_file()
    migrate_to_profiles(file_data)
    file_data.setdefault("active_profile", "default")
    file_data.setdefault("profile", {})
    profile_name = get_active_profile_name()
    file_data["profile"][profile_name] = {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
    }
    return write_full_config(file_data)


def write_platform_config() -> Path:
    """Write a platform-aware config with mode sections. Returns path."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH_XDG.write_text(_platform_template())
    return CONFIG_PATH_XDG


def update_config(key: str, value: str) -> Path:
    """Update a single key in the active profile and return path.

    Creates the file with defaults if it doesn't exist.
    """
    from mm.profile import get_active_profile_name, migrate_to_profiles, write_full_config

    file_data = _read_config_file()
    migrate_to_profiles(file_data)
    file_data.setdefault("active_profile", "default")
    file_data.setdefault("profile", {})

    profile_name = get_active_profile_name()
    profile = file_data["profile"].get(profile_name, dict(_platform_defaults()))
    profile[key] = value
    file_data["profile"][profile_name] = profile
    return write_full_config(file_data)
