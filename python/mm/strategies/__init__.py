"""YAML-based MLLM generation strategies.

Load and cache validated ``TemplateSpec`` objects keyed by
``(kind, mode)`` — e.g. ``("video", "fast")``.

Each strategy YAML configures a 2-stage pipeline:

    file → encode → generate (LLM) → text output

Strategies are resolved from:
  1. ``~/.config/mm/strategies/{kind}/{mode}.yaml``  (user override)
  2. ``python/mm/strategies/{kind}/{mode}.yaml``     (built-in)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from mm.strategies.schema import TemplateSpec

_STRATEGIES_DIR = Path(__file__).parent


def _user_strategies_dir() -> Path:
    return Path.home() / ".config" / "mm" / "strategies"


@lru_cache(maxsize=32)
def load(kind: str, mode: str = "fast") -> TemplateSpec:
    """Load and validate a strategy for ``(kind, mode)``.

    Checks user overrides first, then falls back to built-in strategies.
    Results are cached for the process lifetime.

    Args:
        kind: Media kind (image, video, audio, document).
        mode: Processing mode (fast, accurate).

    Returns:
        A validated ``TemplateSpec``.

    Raises:
        FileNotFoundError: No strategy found for this combination.
        pydantic.ValidationError: Strategy YAML is malformed.
    """
    rel = f"{kind}/{mode}.yaml"
    user_path = _user_strategies_dir() / rel
    builtin_path = _STRATEGIES_DIR / rel

    path = user_path if user_path.is_file() else builtin_path
    if not path.is_file():
        raise FileNotFoundError(
            f"No strategy for kind={kind!r}, mode={mode!r}. "
            f"Looked in: {user_path}, {builtin_path}"
        )

    data: dict[str, Any] = yaml.safe_load(path.read_text())
    return TemplateSpec.model_validate(data)


def render_prompt(template: TemplateSpec, context: dict[str, Any]) -> str:
    """Interpolate the strategy's prompt with runtime context.

    Missing keys are replaced with empty strings so strategies are
    resilient to absent optional context (e.g. ``{duration_ctx}``
    when processing an image).
    """

    class _DefaultDict(dict):  # type: ignore[type-arg]
        def __missing__(self, key: str) -> str:
            return ""

    return template.generate.prompt.format_map(_DefaultDict(context))


def run_pyfunc(
    template: TemplateSpec, parts: list[dict[str, Any]], context: dict[str, Any]
) -> list[dict[str, Any]]:
    """Execute the strategy's custom ``pyfunc`` transform, if defined."""
    if not template.encode.pyfunc:
        return parts

    ns: dict[str, Any] = {}
    exec(  # noqa: S102
        f"def transform(parts, context):\n"
        + "\n".join(f"    {line}" for line in template.encode.pyfunc.splitlines()),
        ns,
    )
    return ns["transform"](parts, context)
