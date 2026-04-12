"""YAML-based MLLM generation pipelines.

Load and cache validated ``PipelineSpec`` objects keyed by
``(kind, mode)`` — e.g. ``("video", "fast")``.

Each pipeline YAML configures a 2-stage pipeline:

    file → encode → generate (LLM) → text output

Pipelines are resolved from:
  1. ``~/.config/mm/pipelines/{kind}/{mode}.yaml``  (user override)
  2. ``python/mm/pipelines/{kind}/{mode}.yaml``     (built-in)
"""

from __future__ import annotations

import types
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from mm.pipelines.schema import Encode, Generate, PipelineSpec

_PIPELINES_DIR = Path(__file__).parent


def _user_pipelines_dir() -> Path:
    return Path.home() / ".config" / "mm" / "pipelines"


@lru_cache(maxsize=32)
def load(kind: str, mode: str = "fast") -> PipelineSpec:
    """Load and validate a pipeline for ``(kind, mode)``.

    Checks user overrides first, then falls back to built-in pipelines.
    Results are cached for the process lifetime.

    Args:
        kind: Media kind (image, video, audio, document).
        mode: Processing mode (fast, accurate).

    Returns:
        A validated ``PipelineSpec``.

    Raises:
        FileNotFoundError: No pipeline found for this combination.
        pydantic.ValidationError: Pipeline YAML is malformed.
    """
    rel = f"{kind}/{mode}.yaml"
    user_path = _user_pipelines_dir() / rel
    builtin_path = _PIPELINES_DIR / rel

    path = user_path if user_path.is_file() else builtin_path
    if not path.is_file():
        raise FileNotFoundError(
            f"No pipeline for kind={kind!r}, mode={mode!r}. "
            f"Looked in: {user_path}, {builtin_path}"
        )

    data: dict[str, Any] = yaml.safe_load(path.read_text())
    return PipelineSpec.model_validate(data)


def render_prompt(template: PipelineSpec, context: dict[str, Any]) -> str:
    """Interpolate the pipeline's prompt with runtime context.

    Missing keys are replaced with empty strings so pipelines are
    resilient to absent optional context (e.g. ``{duration_ctx}``
    when processing an image).
    """

    class _DefaultDict(dict):  # type: ignore[type-arg]
        def __missing__(self, key: str) -> str:
            return ""

    return template.generate.prompt.format_map(_DefaultDict(context))


def run_pyfunc(
    template: PipelineSpec, parts: list[dict[str, Any]], context: dict[str, Any]
) -> list[dict[str, Any]]:
    """Execute the pipeline's custom ``pyfunc`` transform, if defined."""
    if not template.encode.pyfunc:
        return parts

    ns: dict[str, Any] = {}
    exec(  # noqa: S102
        "def transform(parts, context):\n"
        + "\n".join(f"    {line}" for line in template.encode.pyfunc.splitlines()),
        ns,
    )
    result: list[dict[str, Any]] = ns["transform"](parts, context)
    return result


def _coerce(model: type[Encode] | type[Generate], key: str, value: str) -> Any:
    """Cast a CLI string value to the type expected by the Pydantic field."""
    field_info = model.model_fields.get(key)
    if field_info is None:
        raise ValueError(f"Unknown field {key!r} on {model.__name__}")

    annotation = field_info.annotation
    # Unwrap Optional (Union[X, None]) to get the inner type
    if isinstance(annotation, types.UnionType):
        args = [a for a in annotation.__args__ if a is not type(None)]
        annotation = args[0] if args else str

    if annotation is bool:
        return value.lower() in ("true", "1", "yes")
    if annotation is int:
        return int(value)
    if annotation is float:
        return float(value)
    return value


def apply_overrides(
    spec: PipelineSpec,
    encode_overrides: dict[str, str] | None = None,
    generate_overrides: dict[str, str] | None = None,
) -> PipelineSpec:
    """Return a new PipelineSpec with field-level overrides applied.

    Values are coerced from strings to the correct Python type based
    on the Pydantic field annotation (int, float, bool, str).
    """
    if not encode_overrides and not generate_overrides:
        return spec

    data = spec.model_dump()
    if encode_overrides:
        for k, v in encode_overrides.items():
            data["encode"][k] = _coerce(Encode, k, v)
    if generate_overrides:
        for k, v in generate_overrides.items():
            data["generate"][k] = _coerce(Generate, k, v)
    return PipelineSpec.model_validate(data)
