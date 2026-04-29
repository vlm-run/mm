import json
import os
import sys
from pathlib import Path
from typing import Any

import typer

from mm.pipelines.schema import PipelineSpec

KIND_ORDER = ("image", "video", "audio", "document")


class CatOpts:
    """Bag of resolved options threaded through extraction."""

    __slots__ = (
        "n",
        "output_dir",
        "mode",
        "no_cache",
        "format",
        "encode_overrides",
        "generate_overrides",
        "pipelines",
        "verbose",
        "_verbose_suffix",
    )

    n: int | None
    output_dir: Path | None
    mode: str
    no_cache: bool
    format: str
    encode_overrides: dict[str, Any]
    generate_overrides: dict[str, str]
    pipelines: dict[str, PipelineSpec]
    verbose: bool
    _verbose_suffix: str | None

    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not hasattr(self, "_verbose_suffix"):
            self._verbose_suffix = None


def override_extra(
    encode_overrides: dict[str, Any] | None,
    generate_overrides: dict[str, Any] | None,
    pipelines: dict[str, Any] | None,
) -> str:
    """Build the order-independent override string used in the -m=accurate cache key.

    Without this, repeating ``--encode.strategy_opts max_width=768 fps=5`` vs. ``fps=5 max_width=768``
    would produce two distinct entries and double the LLM cost.
    """

    def _render(v: Any) -> str:
        if isinstance(v, dict):
            return json.dumps(v, sort_keys=True, separators=(",", ":"))
        return str(v)

    parts: list[str] = []
    if encode_overrides:
        for k in sorted(encode_overrides):
            parts.append(f"{k}={_render(encode_overrides[k])}")
    if generate_overrides:
        for k in sorted(generate_overrides):
            parts.append(f"g.{k}={_render(generate_overrides[k])}")
    for pk in sorted(pipelines or {}):
        parts.append(f"p:{pk}")
    return "|".join(parts)


def collect_overrides(**kwargs: str | None) -> dict[str, str]:
    """Collect non-None CLI overrides into a ``{field: value}`` dict."""
    return {k: v for k, v in kwargs.items() if v is not None}


def cat_batch_confirm_threshold() -> int:
    raw = os.environ.get("MM_CAT_BATCH_CONFIRM_THRESHOLD", "9")
    try:
        n = int(raw)
    except ValueError:
        return 9
    return max(1, n)


def maybe_confirm_large_cat_batch(n_paths: int, *, assume_yes: bool) -> None:
    """Prompt or require ``--yes`` when ``cat`` is given many paths at once."""
    threshold = cat_batch_confirm_threshold()
    if n_paths < threshold:
        return
    if assume_yes:
        return
    if sys.stdin.isatty():
        if not typer.confirm(
            f"You are about to run cat on {n_paths} files "
            f"(confirmation required for {threshold}+ files). "
            "This may take a long time. Continue?",
            default=False,
        ):
            raise typer.Abort()
        return
    typer.echo(
        f"Error: cat on {n_paths} files requires confirmation. "
        f"Pass --yes (-y) to proceed in non-interactive mode, or pass at most "
        f"{threshold - 1} paths without -y.",
        err=True,
    )
    raise typer.Exit(1)


def coerce_opt_value(raw: str) -> Any:
    """Coerce a CLI ``KEY=VALUE`` string into int/float/bool/str"""
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw
