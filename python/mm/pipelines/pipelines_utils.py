from pathlib import Path
from typing import Any

import typer

from mm.cat_utils.base_utils import KIND_ORDER, CatOpts
from mm.pipelines.schema import PipelineSpec


def resolve_pipeline(opts: CatOpts, kind: str) -> PipelineSpec:
    """Return a PipelineSpec from explicit -p pipelines or auto-resolve.

    If -p specified a named encoder (stored under key '_encoder'), that
    overrides for any kind. Validates that the encoder supports the
    target media kind before applying it.
    """
    from mm.pipelines import load

    if opts.pipelines:
        spec = opts.pipelines.get(kind)
        if spec is not None:
            return spec
        encoder_spec = opts.pipelines.get("_encoder")
        if encoder_spec is not None and encoder_spec.encode.strategy:
            from mm.encoders import get

            enc = get(encoder_spec.encode.strategy)
            if enc is not None:
                supported = getattr(enc, "media_types", ())
                if supported and kind not in supported:
                    typer.echo(
                        f"Warning: encoder '{encoder_spec.encode.strategy}' "
                        f"supports {supported}, not '{kind}'. Falling back to default.",
                        err=True,
                    )
                else:
                    base = load(kind, opts.mode)
                    generate = base.generate
                    if generate is None:
                        generate = getattr(enc, opts.mode, None)
                    return PipelineSpec(
                        kind=base.kind,
                        mode=base.mode,
                        encode=encoder_spec.encode,
                        generate=generate,
                    )

    return load(kind, opts.mode)


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
        else:
            from mm.encoders import list_strategies
            from mm.pipelines.schema import Encode

            known = list_strategies()
            if arg in known:
                specs["_encoder"] = PipelineSpec(
                    kind="_encoder",
                    mode="fast",
                    encode=Encode(strategy=arg),
                    generate=None,
                )
            else:
                if p.is_file():
                    from mm.pipelines import load_file

                    for spec in load_file(p):
                        specs[spec.kind] = spec
                else:
                    typer.echo(f"Warning: '{arg}' is not a known encoder or YAML file.", err=True)

    return specs


def do_list_pipelines() -> None:
    """Print a Rich panel of all built-in and user-override pipelines."""
    import yaml as _yaml
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    pipelines_dir = Path(__file__).resolve().parent.parent / "pipelines"
    user_dir = Path.home() / ".config" / "mm" / "pipelines"

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
