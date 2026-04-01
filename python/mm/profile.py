"""Profile management for mm.

Profile resolution order:
    --profile CLI flag > MM_PROFILE env > active_profile in file > "default"

Profiles allow multiple model/API configurations in a single config file.
Each profile stores name, base_url, api_key, and model.
Use ``mm profile add|update|remove`` to manage profiles, and
``mm profile use <name>``, ``mm --profile <name>``, or ``MM_PROFILE=<name>`` to select one.

Profiles allow multiple LLM provider configurations in a single config file.
Each profile stores base_url, api_key, and model. One profile is active at a
time, resolved via: CLI --profile > MM_PROFILE env > active_profile in file > "default".

TOML layout:

    active_profile = "default"

    [profile.default]
    base_url = "https://mm-ctx.ngrok.io/v1"
    model = "Qwen/Qwen3.5-0.8B"

    [profile.ollama]
    base_url = "http://localhost:11434"
    model = "qwen3.5:0.8"
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

from mm.config import (
    ConfigData,
    ProfileData,
    _cli_overrides,
    _read_config_file,
    write_full_config,
)

# ── Defaults ────────────────────────────────────────────────────────

ENV_PROFILE = "MM_PROFILE"
DEFAULT_PROFILE = "default"
OLLAMA_PROFILE = "ollama"
RESERVED_PROFILES = (DEFAULT_PROFILE, OLLAMA_PROFILE)
IMMUTABLE_PROFILES = frozenset({DEFAULT_PROFILE})

DEFAULTS = {
    "base_url": "https://mm-ctx.ngrok.io/v1",
    "api_key": "",
    "model": "Qwen/Qwen3.5-0.8B",
}

OLLAMA_DEFAULTS = {
    "base_url": "http://localhost:11434",
    "api_key": "",
    "model": "qwen3.5:0.8",
}


class ProfileUpdateData(TypedDict, total=False):
    base_url: str
    api_key: str
    model: str


@dataclass
class Profile:
    name: str = "default"
    base_url: str = DEFAULTS["base_url"]
    api_key: str = DEFAULTS["api_key"]
    model: str = DEFAULTS["model"]


# ── Resolution ─────────────────────────────────────────────────────


def _profiles(file_data: ConfigData) -> dict[str, ProfileData]:
    """Return the mutable profile mapping from config data."""
    return cast(dict[str, ProfileData], file_data.setdefault("profile", {}))


def get_profile_defaults(profile_name: str = DEFAULT_PROFILE) -> dict[str, str]:
    """Return built-in defaults for a profile."""
    if profile_name == OLLAMA_PROFILE:
        return dict(OLLAMA_DEFAULTS)
    return dict(DEFAULTS)


def get_builtin_profile_defaults() -> dict[str, dict[str, str]]:
    """Return built-in profile definitions written into new configs."""
    return {
        DEFAULT_PROFILE: get_profile_defaults(DEFAULT_PROFILE),
        OLLAMA_PROFILE: get_profile_defaults(OLLAMA_PROFILE),
    }


def ensure_builtin_profiles(file_data: ConfigData) -> bool:
    """Normalize built-in profiles and report whether config data changed."""
    profiles = _profiles(file_data)
    changed = False

    default_profile = cast(ProfileData, dict(DEFAULTS))
    if profiles.get(DEFAULT_PROFILE) != default_profile:
        profiles[DEFAULT_PROFILE] = default_profile
        changed = True

    if OLLAMA_PROFILE not in profiles:
        profiles[OLLAMA_PROFILE] = cast(ProfileData, dict(OLLAMA_DEFAULTS))
        changed = True

    if "active_profile" not in file_data:
        file_data["active_profile"] = DEFAULT_PROFILE
        changed = True

    return changed


def load_profile_config() -> ConfigData:
    """Read config, migrate any legacy flat config, and ensure built-ins exist."""
    file_data = _read_config_file()
    did_migrate = migrate_to_profiles(file_data)
    did_normalize = ensure_builtin_profiles(file_data)
    if did_migrate or did_normalize:
        write_full_config(file_data)
    return file_data


def get_active_profile_name() -> str:
    """Resolve active profile: CLI --profile > MM_PROFILE env > active_profile > 'default'."""
    if _cli_overrides.profile:
        return _cli_overrides.profile
    if env_profile := os.environ.get(ENV_PROFILE):
        return env_profile
    file_data = load_profile_config()
    if "active_profile" in file_data:
        return str(file_data["active_profile"])
    return DEFAULT_PROFILE


def get_profile_section(file_data: ConfigData, profile_name: str) -> dict[str, str]:
    """Get the settings for a named profile."""
    ensure_builtin_profiles(file_data)
    profiles = _profiles(file_data)
    if profile_name in profiles:
        return cast(dict[str, str], dict(profiles[profile_name]))
    return {}


def get_profile_names() -> list[str]:
    """Return sorted list of all profile names in the config file."""
    file_data = load_profile_config()
    profiles = _profiles(file_data)
    names = set(profiles.keys())
    names.update(RESERVED_PROFILES)
    if not names:
        names.add(DEFAULT_PROFILE)
    return sorted(names)


# ── Migration ──────────────────────────────────────────────────────


def migrate_to_profiles(file_data: ConfigData) -> bool:
    """Migrate a legacy flat config section into the ollama profile once."""
    if "profile" in file_data:
        return False

    raw_data = cast(dict[str, object], file_data)
    legacy_section = raw_data.get("provider")
    if not isinstance(legacy_section, dict):
        return False

    legacy_values = cast(dict[str, object], legacy_section)
    base_url = legacy_values.get("base_url")
    api_key = legacy_values.get("api_key")
    model = legacy_values.get("model")

    file_data["profile"] = {
        OLLAMA_PROFILE: {
            "base_url": base_url if isinstance(base_url, str) else OLLAMA_DEFAULTS["base_url"],
            "api_key": api_key if isinstance(api_key, str) else OLLAMA_DEFAULTS["api_key"],
            "model": model if isinstance(model, str) else OLLAMA_DEFAULTS["model"],
        }
    }
    raw_data.pop("provider", None)
    file_data.setdefault("active_profile", OLLAMA_PROFILE)
    return True


# ── CRUD ───────────────────────────────────────────────────────────


def _validate_profile_name(name: str) -> None:
    """Ensure profile name is safe for TOML section headers.

    Allows alphanumeric, hyphens, and underscores. Must start with alphanumeric.
    """
    import re

    _PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
    if not name or not _PROFILE_NAME_RE.match(name):
        raise ValueError(
            f"Invalid profile name: '{name}'. "
            "Use only letters, digits, hyphens, and underscores (e.g. 'ollama', 'my-profile', 'openai_v2')."
        )


def set_active_profile(name: str) -> Path:
    """Set the active profile in the config file. Returns path."""
    file_data = load_profile_config()
    profiles = _profiles(file_data)
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
    _validate_profile_name(name)

    file_data = load_profile_config()
    profiles = _profiles(file_data)

    if name in profiles:
        raise ValueError(f"Profile '{name}' already exists. Use 'mm profile update' to modify it")

    if not base_url:
        raise ValueError("base_url is required to add a new profile.")
    if not model:
        raise ValueError("model is required to add a new profile.")

    profiles[name] = {
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
    file_data = load_profile_config()
    profiles = _profiles(file_data)

    if name in IMMUTABLE_PROFILES:
        raise ValueError(
            f"The '{name}' profile is managed by mm and cannot be updated. "
            f"Use '{OLLAMA_PROFILE}' or add a new profile instead."
        )

    if name not in profiles:
        raise ValueError(f"Profile '{name}' not found. Available: {', '.join(sorted(profiles))}")

    updates: ProfileUpdateData = {}
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

    profiles[name].update(updates)
    return write_full_config(file_data)


def remove_profile(name: str) -> Path:
    """Remove a profile from the config file. Returns path."""
    if name in RESERVED_PROFILES:
        raise ValueError(
            f"The '{name}' profile cannot be removed.\n\n"
            "You can:\n"
            f"  mm profile use {DEFAULT_PROFILE}                                  # switch back to the default profile\n"
            f"  mm profile update {OLLAMA_PROFILE} --base-url <url> --model <model>   # change the local ollama profile\n"
            "  mm profile add <name> --base-url <url>                           # create a removable profile"
        )

    file_data = load_profile_config()
    profiles = _profiles(file_data)

    if name not in profiles:
        raise ValueError(f"Profile '{name}' not found.")
    if name == file_data.get("active_profile", "default"):
        raise ValueError(
            f"Cannot remove the active profile '{name}'. Switch to another profile first."
        )

    del profiles[name]
    return write_full_config(file_data)


def _resolve(key: str, file_data: ConfigData, profile_name: str) -> str:
    """Return the resolved value for a profile key: profile > built-in defaults."""
    file_cfg = get_profile_section(file_data, profile_name)

    if key in file_cfg and file_cfg[key] is not None:
        return str(file_cfg[key])
    defaults = get_profile_defaults(profile_name)
    return defaults.get(key, DEFAULTS[key])


def get_profile() -> Profile:
    """Resolve the active profile: active_profile > built-in defaults."""
    file_data = load_profile_config()
    profile_name = get_active_profile_name()
    file_cfg = get_profile_section(file_data, profile_name)

    # If a non-built-in profile was explicitly requested and doesn't exist, fail loudly.
    if not file_cfg and profile_name not in RESERVED_PROFILES:
        available = sorted(set(_profiles(file_data).keys()) | set(RESERVED_PROFILES))
        raise ValueError(f"Profile '{profile_name}' not found. Available: {', '.join(available)}")

    return Profile(
        name=profile_name,
        base_url=_resolve("base_url", file_data, profile_name),
        api_key=_resolve("api_key", file_data, profile_name),
        model=_resolve("model", file_data, profile_name),
    )
