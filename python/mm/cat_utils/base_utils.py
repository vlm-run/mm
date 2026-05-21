import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Literal

import typer

from mm.pipelines.schema import PipelineSpec

KIND_ORDER = ("image", "video", "audio", "document")
CatMode = Literal["fast", "accurate"]


class CatOpts:
    """Bag of resolved options threaded through extraction."""

    __slots__ = (
        "n",
        "output_dir",
        "mode",
        "no_cache",
        "no_generate",
        "format",
        "encode_overrides",
        "generate_overrides",
        "pipelines",
        "verbose",
        "dry_run",
    )

    n: int | None
    output_dir: Path | None
    mode: CatMode
    no_cache: bool
    no_generate: bool
    format: str
    encode_overrides: dict[str, Any]
    generate_overrides: dict[str, str]
    pipelines: dict[str, PipelineSpec]
    verbose: bool
    dry_run: bool

    def __init__(self, **kwargs) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __iter__(self) -> Iterator[str]:
        return iter(self.__slots__)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def keys(self) -> tuple[str, ...]:
        return self.__slots__

    def items(self) -> Iterator[tuple[str, Any]]:
        yield from ((k, getattr(self, k)) for k in self.__slots__)


@dataclass(slots=True)
class RunResult:
    """Result of a pipeline branch — content plus an optional verbose tail.

    The verbose tail is computed and returned regardless of ``opts.verbose``
    so the caller can persist it for replay on a future cached + verbose run.
    """

    content: str
    verbose_suffix: str | None = None


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


def collect_overrides(**kwargs: Any) -> dict[str, Any]:
    """Collect non-None CLI overrides into a ``{field: value}`` dict.

    Values are passed through as-is (string CLI values, parsed JSON
    strings for ``extra_body``, etc.); type coercion happens later in
    ``apply_overrides``/``_coerce_generate``.
    """
    return {k: v for k, v in kwargs.items() if v is not None}


def effective_model(spec: PipelineSpec, profile_model: str) -> str:
    """Resolve the effective model: pipeline ``generate.model`` (CLI-merged) else profile default.

    The profile model is always set (it has a documented hard default per
    profile in ``mm.profile``), so this always returns a non-empty string.
    """
    if spec.generate is not None and spec.generate.model:
        return spec.generate.model
    return profile_model


def spec_extra_body(spec: PipelineSpec) -> dict[str, Any] | None:
    """Return ``spec.generate.extra_body`` if non-empty, else ``None``."""
    if spec.generate is None:
        return None
    return spec.generate.extra_body or None


def make_llm_from_spec(spec: PipelineSpec) -> Any:
    """Build an ``LlmBackend`` honouring any pipeline/CLI-merged model override."""
    from mm.llm import LlmBackend

    model = spec.generate.model if spec.generate is not None else None
    return LlmBackend(model=model)


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


def format_generate_verbose(
    profile_name: str, elapsed_ms: float, prompt_tokens: int, completion_tokens: int
) -> str:
    """Format verbose output for the generate step."""
    from mm.display import format_time

    token_info = (
        f"{prompt_tokens}→{completion_tokens}"
        if (prompt_tokens > 0 or completion_tokens > 0)
        else "no tokens"
    )
    generate_text = f"generate: {profile_name} • {format_time(elapsed_ms)} • {token_info} tokens"
    return f"[dim]{generate_text}[/dim]"


def format_footer(
    path: Path,
    mode: str,
    elapsed_ms: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> str:
    """Format the footer with time, size, mode, profile, and tokens."""
    from mm.display import format_size, format_time

    size_str = format_size(path.stat().st_size)
    parts = [format_time(elapsed_ms), size_str, mode]
    if mode == "accurate":
        from mm.profile import get_active_profile_name

        profile_name = get_active_profile_name()
        parts.append(profile_name)

    if prompt_tokens > 0 or completion_tokens > 0:
        parts.append(f"{prompt_tokens}→{completion_tokens} tokens")

    footer_text = " • ".join(parts)
    # Use Rich markup for dim styling (will work properly with output console)
    return f"[dim]{footer_text}[/dim]"
