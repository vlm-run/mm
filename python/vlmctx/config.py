"""Configuration management for vlmctx.

Reads ~/.vlmctx/config.toml and merges with env vars and CLI flags.

Resolution order (highest priority first):
  1. CLI flags (--base-url, --api-key, --model)
  2. Environment variables (VLMCTX_BASE_URL, etc.)
  3. Config file (~/.vlmctx/config.toml [provider] section)
  4. Built-in defaults (local Ollama)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

CONFIG_DIR = Path.home() / ".vlmctx"
CONFIG_PATH = CONFIG_DIR / "config.toml"

DEFAULTS = {
    "base_url": "http://localhost:11434",
    "api_key": "",
    "model": "qwen3.5:0.8b",
}

ENV_VARS = {
    "base_url": "VLMCTX_BASE_URL",
    "api_key": "VLMCTX_API_KEY",
    "model": "VLMCTX_MODEL",
}

TEMPLATE = """\
# vlmctx configuration
# Docs: https://github.com/autonomi-ai/vlmctx

[provider]
base_url = "{base_url}"
api_key = "{api_key}"
model = "{model}"
"""


@dataclass
class ProviderConfig:
    base_url: str = DEFAULTS["base_url"]
    api_key: str = DEFAULTS["api_key"]
    model: str = DEFAULTS["model"]


@dataclass
class _CliOverrides:
    """Mutable store for CLI-level --base-url / --api-key / --model flags."""

    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None


_cli_overrides = _CliOverrides()


def set_cli_overrides(
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> None:
    _cli_overrides.base_url = base_url
    _cli_overrides.api_key = api_key
    _cli_overrides.model = model


def _read_config_file() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return tomllib.loads(CONFIG_PATH.read_text())
    except Exception:
        return {}


def _resolve(key: str, file_cfg: dict[str, Any]) -> tuple[str, str]:
    """Return (value, source) for a provider key."""
    if val := getattr(_cli_overrides, key, None):
        return val, "cli"
    if val := os.environ.get(ENV_VARS[key]):
        return val, "env"
    if val := file_cfg.get(key):
        return str(val), "file"
    return DEFAULTS[key], "default"


def get_provider() -> ProviderConfig:
    """Resolve provider settings: CLI flags > env vars > config.toml > defaults."""
    file_cfg = _read_config_file().get("provider", {})
    return ProviderConfig(
        base_url=_resolve("base_url", file_cfg)[0],
        api_key=_resolve("api_key", file_cfg)[0],
        model=_resolve("model", file_cfg)[0],
    )


def get_provider_with_sources() -> list[tuple[str, str, str, str]]:
    """Return [(key, value, source, env_var), ...] for display."""
    file_cfg = _read_config_file().get("provider", {})
    rows = []
    for key in ("base_url", "api_key", "model"):
        val, src = _resolve(key, file_cfg)
        display_val = "••••" if key == "api_key" and val and src != "default" else val
        rows.append((key, display_val, src, ENV_VARS[key]))
    return rows


def write_config(base_url: str, api_key: str, model: str) -> Path:
    """Write config.toml and return path."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    content = TEMPLATE.format(base_url=base_url, api_key=api_key, model=model)
    CONFIG_PATH.write_text(content)
    return CONFIG_PATH


def update_config(key: str, value: str) -> Path:
    """Update a single key in [provider] and return path.

    Creates the file with defaults if it doesn't exist.
    """
    file_data = _read_config_file()
    provider = file_data.get("provider", dict(DEFAULTS))
    provider[key] = value
    return write_config(
        base_url=provider.get("base_url", DEFAULTS["base_url"]),
        api_key=provider.get("api_key", DEFAULTS["api_key"]),
        model=provider.get("model", DEFAULTS["model"]),
    )
