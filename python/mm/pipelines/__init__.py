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
import typing
from dataclasses import fields
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from mm.pipelines.schema import Encode, Generate, PipelineSpec, PipelineValidationError

__all__ = [
    "Encode",
    "Generate",
    "PipelineSpec",
    "PipelineValidationError",
    "apply_overrides",
    "deep_merge",
    "load",
    "load_file",
    "render_prompt",
    "run_pyfunc",
]

_PIPELINES_DIR = Path(__file__).parent


def _user_pipelines_dir() -> Path:
    return Path.home() / ".config" / "mm" / "pipelines"


@lru_cache(maxsize=32)
def load(kind: str, mode: str = "fast") -> PipelineSpec:
    """Load and validate a pipeline for ``(kind, mode)``.

    Resolution order:

    1. ``[pipelines]`` path in ``mm.toml``  (e.g. ``image.fast = "/my/path.yaml"``)
    2. ``~/.config/mm/pipelines/{kind}/{mode}.yaml``  (user override dir)
    3. Built-in ``python/mm/pipelines/{kind}/{mode}.yaml``

    Results are cached for the process lifetime.

    Args:
        kind: Media kind (image, video, audio, document, text, code).
        mode: Processing mode (fast, accurate).

    Returns:
        A validated ``PipelineSpec``.

    Raises:
        FileNotFoundError: No pipeline found for this combination.
        PipelineValidationError: Pipeline YAML is malformed.
    """
    from mm.config import get_pipeline_path

    toml_path_str = get_pipeline_path(kind, mode)
    if toml_path_str:
        toml_path = Path(toml_path_str)
        if toml_path.is_file():
            data: dict[str, Any] = yaml.safe_load(toml_path.read_text())
            return PipelineSpec.from_dict(data)

    rel = f"{kind}/{mode}.yaml"
    user_path = _user_pipelines_dir() / rel
    builtin_path = _PIPELINES_DIR / rel

    path = user_path if user_path.is_file() else builtin_path
    if not path.is_file():
        raise FileNotFoundError(
            f"No pipeline for kind={kind!r}, mode={mode!r}. Looked in: {user_path}, {builtin_path}"
        )

    data = yaml.safe_load(path.read_text())
    return PipelineSpec.from_dict(data)


def load_file(path: str | Path) -> list[PipelineSpec]:
    """Load and validate pipeline(s) from an arbitrary YAML path.

    Supports multi-document YAML (``---`` separated).  Returns one
    ``PipelineSpec`` per document found in the file.
    """
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Pipeline file not found: {p}")
    text = p.read_text()
    docs = list(yaml.safe_load_all(text))
    specs: list[PipelineSpec] = []
    for doc in docs:
        if doc is not None:
            specs.append(PipelineSpec.from_dict(doc))
    if not specs:
        raise ValueError(f"No valid pipeline documents in {p}")
    return specs


def render_prompt(template: PipelineSpec, context: dict[str, Any]) -> str:
    """Interpolate the pipeline's prompt with runtime context.

    Missing keys are replaced with empty strings so pipelines are
    resilient to absent optional context (e.g. ``{duration_ctx}``
    when processing an image).
    """

    class _DefaultDict(dict):  # type: ignore[type-arg]
        def __missing__(self, key: str) -> str:
            return ""

    if template.generate is None:
        return ""
    return template.generate.prompt.format_map(_DefaultDict(context))


def run_pyfunc(
    template: PipelineSpec, parts: list[dict[str, Any]], context: dict[str, Any]
) -> list[dict[str, Any]]:
    """Execute the pipeline's custom ``pyfunc`` transform, if defined.

    The ``pyfunc`` value can be:

    * A ``.py`` file path (single-line, ends with ``.py``) — loaded and
      executed.  The file must define ``def transform(parts, context)``.
    * Inline Python code containing ``def transform(parts, context)`` —
      executed directly.
    * Legacy inline function *body* (no ``def`` line) — wrapped in
      ``def transform(parts, context):`` for backward compatibility.
    """
    if not template.encode.pyfunc:
        return parts

    import logging
    import os

    if os.environ.get("MM_ALLOW_PYFUNC", "").lower() not in ("1", "true", "yes"):
        logging.getLogger(__name__).warning(
            "Pipeline pyfunc ignored: set MM_ALLOW_PYFUNC=1 to enable. "
            "pyfunc executes arbitrary Python code from pipeline YAML files."
        )
        return parts

    code = template.encode.pyfunc

    if code.rstrip().endswith(".py") and "\n" not in code:
        p = Path(code).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(f"pyfunc file not found: {p}")
        code = p.read_text()

    ns: dict[str, Any] = {}
    if "def transform" in code:
        exec(code, ns)  # noqa: S102
    else:
        exec(  # noqa: S102
            "def transform(parts, context):\n"
            + "\n".join(f"    {line}" for line in code.splitlines()),
            ns,
        )
    result: list[dict[str, Any]] = ns["transform"](parts, context)
    return result


def _coerce_generate(key: str, value: Any) -> Any:
    """Cast a CLI string override value to the ``Generate`` field type.

    ``extra_body`` is special-cased: a string value is parsed as JSON,
    a mapping value is taken verbatim. Anything else raises ``ValueError``.
    """
    if key == "extra_body":
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str):
            import json

            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as e:
                raise ValueError(f"--generate.extra-body must be a JSON object: {e}") from e
            if not isinstance(parsed, dict):
                raise ValueError(
                    f"--generate.extra-body must decode to a JSON object, got {type(parsed).__name__}"
                )
            return parsed
        raise ValueError(
            f"--generate.extra-body must be a mapping or JSON string, got {type(value).__name__}"
        )

    if not isinstance(value, str):
        return value

    try:
        hints = typing.get_type_hints(Generate)
    except Exception:
        hints = {}
    annotation = hints.get(key)
    if annotation is None:
        return value

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


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Return a new dict with ``overlay`` deep-merged on top of ``base``.

    For overlapping keys: nested dicts are merged recursively, all other
    values are replaced by ``overlay``. Neither input is mutated.
    """
    out = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


_ENCODE_TOP_LEVEL: frozenset[str] = frozenset({"strategy", "strategy_opts", "pyfunc", "backend"})


def apply_overrides(
    spec: PipelineSpec,
    encode_overrides: dict[str, str | dict[str, str]] | None = None,
    generate_overrides: dict[str, Any] | None = None,
) -> PipelineSpec:
    """Return a new ``PipelineSpec`` with field-level overrides applied.

    Encode overrides:
      * ``strategy``, ``strategy_opts``, ``pyfunc`` and ``backend`` replace the
        top-level fields (the encoder handles its own type coercion).

    Generate overrides are coerced to the dataclass field type. The
    ``extra_body`` override accepts a JSON string or a dict; it is
    deep-merged on top of any pipeline-level ``extra_body`` (override
    values win on conflicts).
    """
    if not encode_overrides and not generate_overrides:
        return spec

    data = spec.to_dict()

    if encode_overrides:
        encode_section = data.setdefault("encode", {})
        strategy_opts = dict(encode_section.get("strategy_opts") or {})
        for k, v in encode_overrides.items():
            if k == "strategy_opts" and isinstance(v, dict):
                strategy_opts.update(v)
            elif k in _ENCODE_TOP_LEVEL:
                encode_section[k] = v
        encode_section["strategy_opts"] = strategy_opts

    if generate_overrides:
        if data.get("generate") is None:
            empty_gen: dict[str, Any] = {"prompt": ""}
            data["generate"] = empty_gen
        gen: dict[str, Any] = data["generate"]
        known = {f.name for f in fields(Generate)}
        for k, v in generate_overrides.items():
            if k not in known:
                continue
            coerced = _coerce_generate(k, v)
            if k == "extra_body":
                raw_existing = gen.get("extra_body")
                existing: dict[str, Any] = raw_existing if isinstance(raw_existing, dict) else {}
                overlay: dict[str, Any] = coerced if isinstance(coerced, dict) else {}
                gen[k] = deep_merge(existing, overlay)
            else:
                gen[k] = coerced

    return PipelineSpec.from_dict(data)
