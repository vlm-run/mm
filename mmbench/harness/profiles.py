"""Profile specs for a run: named mm profiles or ad-hoc CLI-provided backends.

A named spec points at a profile in the user's mm config. An ad-hoc spec carries
a model/base_url/api_key given on the CLI (``--profile.model`` etc.) and is
materialized into a throwaway mm config dir, so a run can be provisioned without
creating a global ``mm profile``. The ad-hoc dir is wired into the agent via
``MM_CONFIG_DIR`` (see ``Assistant._env``) and never touches the user's config.
"""

from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProfileSpec:
    """One with_mm backend to benchmark.

    Attributes:
        name: cell/profile name recorded in results and shown in the dashboard.
        config_dir: ``MM_CONFIG_DIR`` for the agent; set only for ad-hoc profiles.
        base_url, model, api_key: known directly for ad-hoc profiles; ``None`` for
            named profiles (resolved from the user's mm config at run time).
    """

    name: str
    config_dir: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None

    @property
    def is_adhoc(self) -> bool:
        return self.config_dir is not None


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def adhoc_name(model: str, base_url: str) -> str:
    """Stable 8-char id for an ad-hoc backend (hash of model + base_url)."""
    return hashlib.sha256(f"{model}\n{base_url}".encode()).hexdigest()[:8]


def materialize_adhoc(*, model: str, base_url: str, api_key: str = "") -> ProfileSpec:
    """Write a throwaway mm config holding one profile and return its spec."""
    name = adhoc_name(model, base_url)
    config_dir = Path(tempfile.mkdtemp(prefix="mmbench-profile-"))
    (config_dir / "mm.toml").write_text(
        f'active_profile = "{name}"\n\n'
        f"[profile.{name}]\n"
        f'base_url = "{_toml_escape(base_url)}"\n'
        f'api_key = "{_toml_escape(api_key)}"\n'
        f'model = "{_toml_escape(model)}"\n'
    )
    return ProfileSpec(
        name=name,
        config_dir=str(config_dir),
        base_url=base_url,
        model=model,
        api_key=api_key,
    )
