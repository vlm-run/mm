import dataclasses
from pathlib import Path
from typing import Any

import typer

from mm.cat_utils.base_utils import KIND_ORDER, CatOpts
from mm.pipelines.schema import PipelineSpec


def _encoder_exists(strategy: str, kind: str) -> bool:
    from mm.encoders import get

    try:
        get(strategy, kind)
    except KeyError:
        return False
    return True


def _apply_encoder_generate(spec: PipelineSpec, opts: CatOpts) -> PipelineSpec:
    """Apply encoder-level generate override to the resolved pipeline spec.

    If the encoder declares a ``generate`` field with an entry for *mode*,
    that value replaces ``spec.generate`` regardless of what the YAML had.
    A ``None`` entry is an *absolute* suppression of the LLM call: the
    encoder's output is the final answer (e.g. ``transcribe`` → transcript,
    ``page-text`` → extracted text), so the pipeline stays encode-only even
    when the user passes ``--generate.*`` overrides.
    A ``Generate`` instance replaces the YAML's generate block
    entirely. Encoders with an empty ``generate`` field (the default) are
    left unchanged.
    """
    if not spec.encode.strategy:
        return spec
    from mm.encoders import get

    enc = get(spec.encode.strategy, spec.kind)
    generate_map = getattr(enc, "generate", {})
    if not isinstance(generate_map, dict) or opts.mode not in generate_map:
        return spec

    if generate_map[opts.mode] is None:
        return dataclasses.replace(spec, generate=None)
    _generate = dataclasses.replace(generate_map[opts.mode], **opts.generate_overrides)
    return dataclasses.replace(spec, generate=_generate)


def _get_override_strategy(opts: CatOpts) -> str | None:
    override = (opts.encode_overrides or {}).get("strategy")
    return override if isinstance(override, str) and override else None


def _apply_encode_strategy_override(spec: PipelineSpec, opts: CatOpts) -> PipelineSpec:
    """Overlay a concrete ``--encode.strategy`` override before generate is derived.

    This mirrors ``-p <encoder>`` so the *chosen* encoder — not the base YAML
    strategy — governs prompt handling in :func:`_apply_encoder_generate`.
    Without this, for e.g., ``--encode.strategy base64`` would run generate resolution
    against the YAML's ``transcribe`` (which suppresses generate), wiping the
    prompt. ``"auto"`` is left untouched for :func:`resolve_auto_strategy`.
    """
    strategy = _get_override_strategy(opts)
    if strategy is None or strategy == "auto" or not _encoder_exists(strategy, spec.kind):
        return spec
    encode = dataclasses.replace(spec.encode, strategy=strategy)
    return dataclasses.replace(spec, encode=encode)


def resolve_pipeline(opts: CatOpts, kind: str) -> PipelineSpec:
    """Return a PipelineSpec from explicit -p pipelines or auto-resolve.

    Resolution order:
      1. ``-p <YAML file>`` keyed by kind
      2. ``-p <encoder name>`` (stored under ``_encoder``): merges the
         named encoder's encode config onto the base YAML pipeline
      3. Built-in ``pipelines/{kind}/{mode}.yaml``

    After resolving the YAML, encoder-level ``generate`` overrides are
    applied via :func:`_apply_encoder_generate` so each encoder can
    suppress or customise the generate step without touching the YAML.
    """
    from mm.pipelines import load

    if opts.pipelines:
        spec = opts.pipelines.get(kind)
        if spec is not None:
            return _apply_encoder_generate(spec, opts)

        encoder_spec = opts.pipelines.get("_encoder")
        if encoder_spec is not None and encoder_spec.encode.strategy:
            if not _encoder_exists(encoder_spec.encode.strategy, kind):
                typer.echo(
                    f"Warning: encoder '{encoder_spec.encode.strategy}' "
                    f"not available for kind '{kind}'. Falling back to default.",
                    err=True,
                )
            else:
                from mm.pipelines import deep_merge
                from mm.pipelines.schema import Encode

                base = load(kind, opts.mode)
                encode = Encode.from_dict(
                    deep_merge(base.encode.to_dict(), encoder_spec.encode.to_dict())
                )
                spec = PipelineSpec(
                    kind=base.kind,
                    mode=base.mode,
                    encode=encode,
                    generate=base.generate,
                )
                return _apply_encoder_generate(spec, opts)

    spec = load(kind, opts.mode)
    spec = _apply_encode_strategy_override(spec, opts)
    if _get_override_strategy(opts) == "auto":
        # Defer generate derivation: the real encoder is chosen later by
        # resolve_auto_strategy, which applies *that* encoder's generate map.
        # Deriving it now (against the base YAML strategy) would wrongly wipe
        # the prompt before auto picks an encoder that keeps it (e.g. base64).
        return spec
    return _apply_encoder_generate(spec, opts)


def build_pipeline_help() -> str:
    """Build the --pipeline / -p help string with dynamically discovered encoder names."""
    try:
        from mm.encoders import list_strategies

        names = list_strategies()
        names_str = ", ".join(names) if names else "none discovered"
    except Exception:
        names_str = "(run --list-pipelines to see)"
    return f"Pipeline: YAML path or encoder name ({names_str}). Repeatable."


def load_pipeline_args(pipeline_args: list[str]) -> dict[str, PipelineSpec]:
    """Resolve -p arguments into a dict of PipelineSpec keyed by kind.

    Each argument can be:
    - A YAML file path (loaded, possibly multi-document)
    - A registered encoder name (wrapped into a PipelineSpec with that strategy)
    """
    specs: dict[str, PipelineSpec] = {}

    for arg in pipeline_args:
        p = Path(arg).expanduser()
        if p.suffix in (".yaml", ".yml") or p.is_file():
            from mm.pipelines import load_file

            for spec in load_file(p):
                specs[spec.kind] = spec
            continue

        from mm.encoders import list_strategies
        from mm.pipelines.schema import Encode

        if arg in list_strategies():
            specs["_encoder"] = PipelineSpec(
                kind="_encoder",
                mode="fast",
                encode=Encode(strategy=arg),
                generate=None,
            )
        else:
            typer.echo(
                f"Warning: '{arg}' is not a known encoder or YAML file. Falling back to the default.",
                err=True,
            )
    return specs


def do_list_pipelines() -> None:
    """Print a Rich panel of all built-in and user-override pipelines."""
    import yaml as _yaml
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    from mm.settings import get_settings

    pipelines_dir = Path(__file__).resolve().parent.parent / "pipelines"
    user_dir = get_settings().config_dir / "pipelines"

    _RESERVED_KEYS = {"strategy", "pyfunc"}

    rows: list[tuple[str, str, str, str, dict[str, Any]]] = []

    for search_dir in (pipelines_dir, user_dir):
        if not search_dir.is_dir():
            continue
        for yaml_file in sorted(search_dir.rglob("*.yaml")):
            if yaml_file.name == "spec.yaml":
                continue
            try:
                data = _yaml.safe_load(yaml_file.read_text()) or {}
            except Exception:
                continue
            kind = data.get("kind", "?")
            mode = data.get("mode", "?")
            enc_data = data.get("encode", {})
            encoder = enc_data.get("strategy") or "—"
            params = {k: v for k, v in enc_data.items() if k not in _RESERVED_KEYS}
            rows.append((str(yaml_file), kind, mode, encoder, params))

    try:
        from mm.config import get_pipeline_path

        for kind in KIND_ORDER:
            for mode in ("fast", "accurate"):
                p = get_pipeline_path(kind, mode)
                if p:
                    rows.insert(0, (p, kind, mode, "—", {}))
    except Exception:
        pass

    kind_rank = {k: i for i, k in enumerate(KIND_ORDER)}
    mode_rank = {"fast": 0, "accurate": 1}
    rows.sort(key=lambda r: (kind_rank.get(r[1], 99), mode_rank.get(r[2], 99), r[0]))

    home = str(Path.home())
    display_rows: list[tuple[str, str, str, str, dict[str, Any]]] = []
    for yaml_path, kind, mode, encoder, params in rows:
        dp = "~" + yaml_path[len(home) :] if yaml_path.startswith(home) else yaml_path
        display_rows.append((dp, kind, mode, encoder, params))

    lines: list[Text] = []
    header = Text(no_wrap=True, overflow="ellipsis")
    header.append("Kind".ljust(10), style="bold")
    header.append("Mode".ljust(10), style="bold")
    header.append("Encoder", style="bold")
    lines.append(header)

    prev_kind = ""
    for dp, kind, mode, encoder, params in display_rows:
        if kind != prev_kind and prev_kind:
            lines.append(Text(""))
        prev_kind = kind

        line = Text(no_wrap=True, overflow="ellipsis")
        line.append(kind.ljust(10))
        line.append(mode.ljust(10))
        line.append(encoder, style="bold")
        if params:
            param_str = ", ".join(f"{k}={v}" for k, v in params.items())
            line.append(f"({param_str})")
        lines.append(line)

        path_line = Text(no_wrap=True, overflow="ellipsis")
        path_line.append(" " * 20)
        path_line.append(dp)
        lines.append(path_line)

    body = Text("\n").join(lines)
    max_line = max((len(line.plain) for line in lines), default=60)
    panel_w = max_line + 8
    console = Console(width=max(panel_w, 80))
    panel = Panel(
        body,
        title="[bold]Pipelines[/bold]",
        title_align="left",
        box=box.ROUNDED,
        padding=(1, 2),
        width=panel_w,
    )
    console.print()
    console.print(panel)
    console.print()


def do_print_pipeline(pipeline_ref: str) -> None:
    """Print the raw YAML source of a ``<kind>/<mode>`` pipeline and exit"""
    kind, _, mode = pipeline_ref.partition("/")
    if not mode or kind not in KIND_ORDER or mode not in ("fast", "accurate"):
        typer.echo(
            f"Error: --print-pipeline expects '<kind>/<mode>' "
            f"(kind in {list(KIND_ORDER)}, mode in ['fast', 'accurate']). Got: {pipeline_ref!r}",
            err=True,
        )
        raise typer.Exit(1)

    from mm.config import get_pipeline_path
    from mm.pipelines import _PIPELINES_DIR, _user_pipelines_dir

    toml_path_str = get_pipeline_path(kind, mode)
    if toml_path_str and Path(toml_path_str).is_file():
        src = Path(toml_path_str)
    else:
        rel = f"{kind}/{mode}.yaml"
        user_path = _user_pipelines_dir() / rel
        src = user_path if user_path.is_file() else _PIPELINES_DIR / rel

    if not src.is_file():
        typer.echo(f"Error: pipeline file not found: {src}", err=True)
        raise typer.Exit(1)

    typer.echo(f"# {src}")
    typer.echo(src.read_text().rstrip())
