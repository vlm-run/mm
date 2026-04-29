from pathlib import Path

import typer

from mm.cat_utils import CatOpts
from mm.pipelines.schema import PipelineSpec


def resolve_pipeline(opts: CatOpts, kind: str) -> PipelineSpec:
    """Return a PipelineSpec from explicit -p pipelines or auto-resolve.

    If -p specified a named encoder (stored under key '_encoder'), that
    overrides for any kind.  Validates that the encoder supports the
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
                    return PipelineSpec(
                        kind=base.kind,
                        mode=base.mode,
                        encode=encoder_spec.encode,
                        generate=base.generate,
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
