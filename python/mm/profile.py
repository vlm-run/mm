"""Profile management for mm.

Profile resolution order:
    --profile CLI flag > MM_PROFILE env > active_profile in file > ollama (default)

Profiles allow multiple model/API configurations in a single config file.
Each profile stores name, base_url, api_key, and model.
Use ``mm profile add|update|remove`` to manage profiles, and
``mm profile use <name>``, ``mm --profile <name>``, or ``MM_PROFILE=<name>`` to select one.

Profiles allow multiple LLM provider configurations in a single config file.
Each profile stores base_url, api_key, and model. One profile is active at a
time, resolved via: CLI --profile > MM_PROFILE env > active_profile in file > ollama (default).

TOML layout:

    active_profile = "gateway"

    [profile.ollama]
    base_url = "http://localhost:11434/v1"
    model = "gemma4:e2b"
    api_key = ""

    [profile.gateway]
    base_url = "https://gateway.vlm.run/v1/openai"
    model = "qwen/qwen3.5-0.8b"
    api_key = ""

    [profile.openrouter]
    base_url = "https://openrouter.ai/api/v1"
    model = "google/gemma-4-26b-a4b-it:free"
    api_key = ""
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
RESERVED_PROFILES = ("ollama", "gateway", "openrouter")
IMMUTABLE_PROFILES = frozenset({"gateway"})
DEFAULT_PROFILE = "gateway"


OLLAMA_DEFAULTS = {
    "name": "ollama",
    "base_url": "http://localhost:11434/v1",
    "api_key": "",
    "model": "gemma4:e2b",
}

GATEWAY_DEFAULTS = {
    "name": "gateway",
    "base_url": "https://gateway.vlm.run/v1/openai",
    "api_key": "",
    "model": "qwen/qwen3.5-0.8b",
}

OPENROUTER_DEFAULTS = {
    "name": "openrouter",
    "base_url": "https://openrouter.ai/api/v1",
    "api_key": "",
    "model": "google/gemma-4-26b-a4b-it:free",
}

RESERVED_DEFAULTS = {
    "ollama": OLLAMA_DEFAULTS,
    "gateway": GATEWAY_DEFAULTS,
    "openrouter": OPENROUTER_DEFAULTS,
}

GATEWAY_BASE_URL = "https://gateway.vlm.run/v1"
EMBEDDING_BASE_URL = os.getenv("MM_EMBEDDING_BASE_URL", GATEWAY_BASE_URL)
TRANSCRIPTION_BASE_URL = os.getenv("MM_TRANSCRIPTION_BASE_URL", GATEWAY_BASE_URL)


class ProfileUpdateData(TypedDict, total=False):
    base_url: str
    api_key: str
    model: str


@dataclass
class Profile:
    name: str = RESERVED_DEFAULTS[DEFAULT_PROFILE]["name"]
    base_url: str = RESERVED_DEFAULTS[DEFAULT_PROFILE]["base_url"]
    api_key: str = RESERVED_DEFAULTS[DEFAULT_PROFILE]["api_key"]
    model: str = RESERVED_DEFAULTS[DEFAULT_PROFILE]["model"]


# ── Resolution ─────────────────────────────────────────────────────


def _profiles(file_data: ConfigData) -> dict[str, ProfileData]:
    """Return the mutable profile mapping from config data."""
    return cast(dict[str, ProfileData], file_data.setdefault("profile", {}))


def get_profile_defaults(profile_name: str) -> dict[str, str]:
    """Return built-in defaults for a profile."""
    if profile_name in RESERVED_PROFILES:
        return dict(RESERVED_DEFAULTS[profile_name])
    return dict(RESERVED_DEFAULTS[DEFAULT_PROFILE])


def get_default_profiles() -> dict[str, dict[str, str]]:
    """Return built-in/default profiles written into new configs."""
    return dict(RESERVED_DEFAULTS)


def ensure_builtin_profiles(file_data: ConfigData) -> bool:
    """Normalize built-in profiles and report whether config data changed."""
    profiles = _profiles(file_data)
    changed = False

    for name in RESERVED_PROFILES:
        expected = {k: v for k, v in RESERVED_DEFAULTS[name].items() if k != "name"}

        if name in IMMUTABLE_PROFILES:
            if profiles.get(name) != expected:
                profiles[name] = cast(ProfileData, expected)
                changed = True
        elif name not in profiles:
            profiles[name] = cast(ProfileData, expected)
            changed = True

    if "active_profile" not in file_data:
        file_data["active_profile"] = DEFAULT_PROFILE
        changed = True

    return changed


def load_profile_config() -> ConfigData:
    """Read config, migrate any legacy flat config, and ensure built-ins exist."""
    file_data = _read_config_file()
    did_normalize = ensure_builtin_profiles(file_data)
    if did_normalize:
        write_full_config(file_data)
    return file_data


def get_active_profile_name() -> str:
    """Resolve active profile: CLI --profile > MM_PROFILE env > active_profile > 'ollama'."""
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
            f"The '{name}' profile is managed by mm and cannot be modified. "
            f"You can modify other profiles or add a new one."
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
            "No fields to update. Provide at least one of --base-url, --model, and --api-key."
        )

    profiles[name].update(updates)
    return write_full_config(file_data)


def reset_profiles() -> Path:
    """Reset all profiles to built-in defaults.

    Removes custom profiles, restores reserved profiles to default values,
    and sets the active profile back to DEFAULT_PROFILE. Mode settings are preserved.
    Returns the config file path.
    """
    file_data = load_profile_config()
    # Replace profile section with only reserved defaults
    file_data["profile"] = {
        name: cast(ProfileData, dict(RESERVED_DEFAULTS[name])) for name in RESERVED_PROFILES
    }
    file_data["active_profile"] = DEFAULT_PROFILE
    return write_full_config(file_data)


def remove_profile(name: str) -> Path:
    """Remove a profile from the config file. Returns path."""
    if name in RESERVED_PROFILES:
        removable = [p for p in RESERVED_PROFILES if p not in IMMUTABLE_PROFILES]
        useable = [p for p in RESERVED_PROFILES if p != name]
        raise ValueError(
            f"The '{name}' profile cannot be removed.\n\n"
            "You can:\n"
            f"  mm profile use {'|'.join(useable)}                                  # switch back to the default profile\n"
            f"  mm profile update {'|'.join(removable)} --base-url <url> --model <model>   # update a reserved profile\n"
            "  mm profile add <name> --base-url <url>                           # create a removable profile"
        )

    file_data = load_profile_config()
    profiles = _profiles(file_data)
    if name not in profiles:
        raise ValueError(f"Profile '{name}' not found.")
    if name == file_data.get("active_profile", DEFAULT_PROFILE):
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
    return defaults.get(key, RESERVED_DEFAULTS[DEFAULT_PROFILE][key])


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
