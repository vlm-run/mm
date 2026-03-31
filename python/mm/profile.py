"""Profile management for mm.

Profiles allow multiple LLM provider configurations in a single config file.
Each profile stores base_url, api_key, and model. One profile is active at a
time, resolved via: CLI --profile > MM_PROFILE env > active_profile in file > "default".

TOML layout:

  active_profile = "default"

  [profile.default]
  base_url = "http://localhost:11434"
  model = "qwen3.5:0.8b"

  [profile.vlmrun]
  base_url = "https://api.vlm.run/v1"
  api_key = "sk-..."
  model = "vlm-1"

Legacy [provider] sections are treated as [profile.default] for backward
compatibility.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mm.config import (
    ENV_PROFILE,
    _cli_overrides,
    _find_config_path,
    _read_config_file,
)

# ── Resolution ─────────────────────────────────────────────────────


def get_active_profile_name() -> str:
    """Resolve active profile: CLI --profile > MM_PROFILE env > file active_profile > 'default'."""
    if _cli_overrides.profile:
        return _cli_overrides.profile
    if env_profile := os.environ.get(ENV_PROFILE):
        return env_profile
    file_data = _read_config_file()
    return str(file_data.get("active_profile", "default"))


def get_profile_section(file_data: dict[str, Any], profile_name: str) -> dict[str, Any]:
    """Get provider settings for a named profile.

    Falls back to [provider] as 'default' for backward compatibility.
    """
    profiles = file_data.get("profile", {})
    if profile_name in profiles:
        return dict(profiles[profile_name])
    # Backward compat: treat [provider] as the default profile
    if profile_name == "default" and "provider" in file_data:
        return dict(file_data["provider"])
    return {}


def get_profile_names() -> list[str]:
    """Return sorted list of all profile names in the config file."""
    file_data = _read_config_file()
    profiles = file_data.get("profile", {})
    names = set(profiles.keys())
    # Backward compat: if [provider] exists and no profiles, show "default"
    if not names and "provider" in file_data:
        names.add("default")
    if not names:
        names.add("default")
    return sorted(names)


# ── Migration ──────────────────────────────────────────────────────


def migrate_to_profiles(file_data: dict[str, Any]) -> dict[str, Any]:
    """If config has [provider] but no [profile.*], migrate in-place."""
    if "provider" in file_data and "profile" not in file_data:
        file_data["profile"] = {"default": dict(file_data.pop("provider"))}
        file_data.setdefault("active_profile", "default")
    return file_data


# ── Serialization ──────────────────────────────────────────────────


def _toml_str(value: str) -> str:
    """Escape a string for TOML double-quoted format."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def write_full_config(file_data: dict[str, Any]) -> Path:
    """Serialize full config dict back to TOML and write to disk. Returns path."""
    lines: list[str] = []

    # Top-level active_profile
    active = file_data.get("active_profile", "default")
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
                    lines.append(f'{mk} = "{_toml_str(mv)}"')
            lines.append("")

    path = _find_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


# ── CRUD ───────────────────────────────────────────────────────────


def set_active_profile(name: str) -> Path:
    """Set the active profile in the config file. Returns path."""
    file_data = _read_config_file()
    migrate_to_profiles(file_data)
    profiles = file_data.get("profile", {})
    if name not in profiles:
        raise ValueError(f"Profile '{name}' not found. Available: {', '.join(sorted(profiles))}")
    file_data["active_profile"] = name
    return write_full_config(file_data)


def add_profile(
    name: str,
    *,
    base_url: str,
    model: str,
    api_key: str = "",
) -> Path:
    """Add a new profile to the config file. Returns path."""
    file_data = _read_config_file()
    migrate_to_profiles(file_data)
    file_data.setdefault("active_profile", "default")
    file_data.setdefault("profile", {})

    if name in file_data["profile"]:
        raise ValueError(
            f"Profile '{name}' already exists. Use 'mm config profile update' to modify it"
        )

    if not base_url:
        raise ValueError("base_url is required to add a new profile.")
    if not model:
        raise ValueError("model is required to add a new profile.")

    file_data["profile"][name] = {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
    }
    return write_full_config(file_data)


PROFILE_KEYS = frozenset({"base_url", "api_key", "model"})


def update_profile(
    name: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> Path:
    """Update one or more fields of an existing profile. Returns path.

    Only the provided (non-None) fields are updated; others are preserved.
    """
    file_data = _read_config_file()
    migrate_to_profiles(file_data)
    file_data.setdefault("profile", {})

    if name not in file_data.get("profile", {}):
        raise ValueError(
            f"Profile '{name}' not found. Available: {', '.join(sorted(file_data['profile']))}"
        )

    updates: dict[str, str] = {}
    if base_url is not None:
        if not base_url:
            raise ValueError("base_url cannot be empty.")
        updates["base_url"] = base_url
    if api_key is not None:
        updates["api_key"] = api_key
    if model is not None:
        if not model:
            raise ValueError("model cannot be empty.")
        updates["model"] = model

    if not updates:
        raise ValueError(
            "No fields to update. Provide at least one of: --base-url, --api-key, --model"
        )

    file_data["profile"][name].update(updates)
    return write_full_config(file_data)


def remove_profile(name: str) -> Path:
    """Remove a profile from the config file. Returns path."""
    if name == "default":
        raise ValueError(
            "The 'default' profile cannot be removed.\n\n"
            "You can:\n"
            "  mm config profile update default --base-url <url> --model <model>   # change its settings\n"
            "  mm config profile use <other>                                        # switch to a different profile\n"
            "  mm config profile add <name> --base-url <url>                        # create a new profile"
        )

    file_data = _read_config_file()
    migrate_to_profiles(file_data)
    profiles = file_data.get("profile", {})

    if name not in profiles:
        raise ValueError(f"Profile '{name}' not found.")
    if name == file_data.get("active_profile", "default"):
        raise ValueError(
            f"Cannot remove the active profile '{name}'. Switch to another profile first."
        )

    del profiles[name]
    return write_full_config(file_data)
