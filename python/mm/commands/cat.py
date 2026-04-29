"""mm cat -- unified content extraction with pipeline-driven modes.

Behaviour is driven by (file type × pipeline mode). Default is ``--mode fast``
which runs local extraction (no LLM). Use ``--mode accurate`` for LLM-powered
descriptions.

File-type behaviour:
  Images     fast: dimensions, MIME, hash, EXIF metadata.
             accurate: VLM caption via vision model.
  Videos     fast: resolution, duration, FPS, codecs (metadata only).
             accurate: keyframe mosaic → VLM description.
  Audio      fast: duration, codec, bitrate (metadata only).
             accurate: transcript → LLM summary.
  PDFs       fast: text extraction via pypdfium2.
             accurate: LLM summary of extracted text.
  Code/text  raw content passthrough (no pipeline, no LLM in either mode).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated, Optional

import typer

from mm.cat_utils.accurate_audio import accurate_audio
from mm.cat_utils.accurate_image import accurate_image
from mm.cat_utils.accurate_video import accurate_video
from mm.cat_utils.base_utils import (
    CatOpts,
    coerce_opt_value,
    collect_overrides,
    format_footer,
    format_generate_verbose,
    maybe_confirm_large_cat_batch,
    override_extra,
)
from mm.cat_utils.extract_local import extract_local
from mm.cat_utils.run_encoder import run_encoder
from mm.encoders.encoders_utils import do_list_encoders
from mm.pipe import read_paths_from_stdin
from mm.pipelines.pipelines_utils import (
    do_list_pipelines,
    do_print_pipeline,
    load_pipeline_args,
    resolve_pipeline,
)
from mm.pipelines.schema import PipelineSpec
from mm.utils import BinaryFileKind, FileKind, Format, file_kind

# Track total bytes processed for throughput calculation
_total_bytes_processed = 0
# Track whether the result was served from cache
_was_cached = False


def cat_cmd(
    # -- Most important options first (Typer renders in declaration order) --
    mode: Annotated[
        str,
        typer.Option("--mode", "-m", help="Processing mode: fast or accurate [default: fast]"),
    ] = "fast",
    pipeline: Annotated[
        Optional[list[str]],
        typer.Option(
            "--pipeline",
            "-p",
            help="Pipeline: YAML path or registered encoder name. Repeatable.",
        ),
    ] = None,
    list_pipelines: Annotated[
        bool,
        typer.Option("--list-pipelines", help="List built-in pipelines and exit"),
    ] = False,
    list_encoders: Annotated[
        bool,
        typer.Option("--list-encoders", help="List registered encoders and exit"),
    ] = False,
    print_pipeline: Annotated[
        Optional[str],
        typer.Option(
            "--print-pipeline",
            metavar="PIPELINE",
            help="Print the YAML for a pipeline and exit. Takes '<kind>/<mode>' (e.g. 'image/accurate').",
        ),
    ] = None,
    # -- Positional argument --
    files: Annotated[Optional[list[Path]], typer.Argument(help="Files to display")] = None,
    n: Annotated[
        Optional[int],
        typer.Option("-n", help="Line limit: +N = head, -N = tail"),
    ] = None,
    output_dir: Annotated[
        Optional[Path],
        typer.Option("--output-dir", "-o", help="Output directory for generated artifacts"),
    ] = None,
    no_cache: Annotated[
        bool, typer.Option("--no-cache", help="Bypass cache, force fresh run")
    ] = False,
    format: Annotated[
        Optional[Format],
        typer.Option(
            "--format", "-f", help="Output format: json, tsv, csv, dataset-jsonl, dataset-hf"
        ),
    ] = None,
    # -- Surviving encode overrides --
    encode_strategy: Annotated[
        Optional[str],
        typer.Option("--encode.strategy", help="Override encoder name"),
    ] = None,
    encode_pyfunc: Annotated[
        Optional[str],
        typer.Option("--encode.pyfunc", help="Custom Python transform (.py file or inline code)"),
    ] = None,
    encode_strategy_opts: Annotated[
        Optional[list[str]],
        typer.Option(
            "--encode.strategy_opts",
            metavar="KEY=VALUE",
            help=(
                "Override entries in encode.strategy_opts. Repeatable. "
                "Values are coerced to int/float/bool when possible. "
                "e.g. --encode.strategy_opts max_width=768 --encode.strategy_opts fps=5"
            ),
        ),
    ] = None,
    # -- Surviving generate overrides --
    generate_prompt: Annotated[
        Optional[str],
        typer.Option("--generate.prompt", help="Override LLM prompt template"),
    ] = None,
    generate_max_tokens: Annotated[
        Optional[str],
        typer.Option("--generate.max-tokens", help="Override max completion tokens"),
    ] = None,
    generate_temperature: Annotated[
        Optional[str],
        typer.Option("--generate.temperature", help="Override sampling temperature"),
    ] = None,
    generate_json_mode: Annotated[
        Optional[str],
        typer.Option("--generate.json-mode", help="Override JSON mode (true/false)"),
    ] = None,
    # -- Utility --
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show progress bars")] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Confirm when path count ≥ threshold (default 9; env MM_CAT_BATCH_CONFIRM_THRESHOLD)",
        ),
    ] = False,
) -> None:
    """Extract and describe file content.

    \b
    Behavior auto-detects from file type. Default mode is 'fast' (local
    extraction). Use '-m accurate' for LLM-powered descriptions.

    \b
    Images:   fast = metadata.  accurate = VLM caption.
    Videos:   fast = metadata.  accurate = mosaic → VLM description.
    Audio:    fast = metadata.  accurate = transcript → LLM summary.
    Docs:     fast = text extraction.  accurate = LLM summary.
    Code:     fast = raw text.  accurate = LLM summary.

    \b
    Examples:
      mm cat paper.pdf                      # text extraction (fast)
      mm cat photo.png -m accurate          # VLM description
      mm cat video.mp4 -m accurate          # mosaic → VLM
      mm cat photo.png -p tile              # use named encoder
      mm cat photo.png -p my-pipeline.yaml  # custom pipeline YAML
      mm cat photo.png -m accurate --encode.strategy_opts max_width=768
                                            # override a single strategy_opts entry
      mm cat --print-pipeline image/accurate
                                            # inspect the pipeline YAML source
    """
    if list_pipelines:
        do_list_pipelines()
        return
    if list_encoders:
        do_list_encoders()
        return
    if print_pipeline is not None:
        do_print_pipeline(print_pipeline)
        return

    paths: list[str] = []

    stdin_paths = read_paths_from_stdin()
    if stdin_paths:
        paths.extend(stdin_paths)
    if files:
        paths.extend(str(f) for f in files)

    if not paths:
        typer.echo("Error: No files specified.", err=True)
        raise typer.Exit(1)

    maybe_confirm_large_cat_batch(len(paths), assume_yes=yes)

    if mode not in ("fast", "accurate"):
        typer.echo(f"Error: Unknown mode {mode!r}. Use 'fast' or 'accurate'.", err=True)
        raise typer.Exit(1)

    enc_overrides: dict[str, str | dict[str, str]] = {
        **collect_overrides(
            strategy=encode_strategy,
            pyfunc=encode_pyfunc,
        )
    }
    if encode_strategy_opts:
        for opt_entry in encode_strategy_opts:
            key, sep, val = opt_entry.partition("=")
            if not sep or not key:
                typer.echo(
                    f"Error: --encode.strategy_opts expects KEY=VALUE, got {opt_entry!r}.",
                    err=True,
                )
                raise typer.Exit(1)
            if "strategy_opts" not in enc_overrides:
                enc_overrides["strategy_opts"] = {}
            if isinstance(enc_overrides["strategy_opts"], dict):
                enc_overrides["strategy_opts"][key] = coerce_opt_value(val)

    gen_overrides = collect_overrides(
        prompt=generate_prompt,
        max_tokens=generate_max_tokens,
        temperature=generate_temperature,
        json_mode=generate_json_mode,
    )

    # -- Load explicit pipeline/-p args (YAML files or named encoders) keyed by kind --
    pipeline_specs: dict[str, PipelineSpec] = {}
    if pipeline:
        pipeline_specs = load_pipeline_args(pipeline)

    from mm.display import resolve_format

    fmt = resolve_format(format.value if format else None)

    opts = CatOpts(
        n=n,
        output_dir=output_dir,
        mode=mode,
        no_cache=no_cache,
        format=fmt,
        encode_overrides=enc_overrides,
        generate_overrides=gen_overrides,
        pipelines=pipeline_specs,
        verbose=verbose,
    )

    multi_file = len(paths) > 1
    results: list[dict] = []
    _emitted = 0

    global _total_bytes_processed, _was_cached
    _total_bytes_processed = 0
    _was_cached = False

    for file_path in paths:
        p = Path(file_path)
        if not p.exists():
            typer.echo(f"Error: {file_path} not found.", err=True)
            from mm.store.utils import prune_missing

            prune_missing(uris=[str(p.resolve())])
            continue

        # Track bytes for throughput calculation
        _total_bytes_processed += p.stat().st_size

        content = _extract(p, opts)

        if n is not None:
            all_lines = content.splitlines()
            content = "\n".join(all_lines[:n] if n >= 0 else all_lines[n:])

        if fmt in ("json", "dataset-jsonl", "dataset-hf"):
            if fmt == "json":
                entry: dict = {"path": str(p), "mode": mode, "content": content}
            else:
                entry = {
                    "path": str(p),
                    "mode": mode,
                    "content": content,
                    "name": p.name,
                    "type": file_kind(p),
                    "size": p.stat().st_size,
                }
            results.append(entry)
        elif fmt == "rich":
            if multi_file:
                from mm.display import output_console

                if _emitted > 0:
                    output_console.print("\n====")
                output_console.print(f"<{p.name}>")
            _display_rich(p, content, mode, n)
            _emitted += 1
        else:
            if multi_file:
                if _emitted > 0:
                    print("\n====")
                print(f"<{p.name}>")
            _dim_prefix = "[dim]"
            lines = content.split("\n")
            plain_lines: list[str] = []
            rich_lines: list[str] = []
            for ln in lines:
                if _dim_prefix in ln:
                    rich_lines.append(ln)
                else:
                    plain_lines.append(ln)
            if plain_lines:
                print("\n".join(plain_lines))
            if rich_lines:
                from mm.display import output_console

                output_console.print("\n".join(rich_lines))
            _emitted += 1

    if fmt in ("json", "dataset-jsonl", "dataset-hf"):
        from mm.display import emit_rows

        emit_rows(fmt, results, output_dir=str(output_dir) if output_dir else "mm_dataset")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _extract(path: Path, opts: CatOpts) -> str:
    """Pipeline-driven extraction dispatch with unified accurate-mode caching.

    1. Auto-detect kind from file extension
    2. Check accurate-result cache (applies to both fast and accurate modes)
    3. Resolve pipeline (explicit -p > toml override > built-in)
    4. Apply CLI overrides
    5. Run encode step (kind-specific local extraction)
    6. If generate is not None: run LLM call
    7. If generate is None: output encode result directly
    8. Store content + verbose metadata in the accurate-result cache
    """
    kind = file_kind(path)

    # Text-like kinds (code, config, plain text) bypass caching — they're passthrough.
    if kind == "text":
        return extract_local(path, kind, no_cache=opts.no_cache)

    from mm.profile import get_profile
    from mm.store.db import MmDatabase
    from mm.store.utils import get_content_hash

    db = MmDatabase()
    profile = get_profile()
    content_hash = get_content_hash(path)

    extra = override_extra(
        opts.encode_overrides,
        opts.generate_overrides,
        opts.pipelines,
    )

    accurate_id: str | None = None
    if content_hash:
        from mm.store.utils import get_accurate_id

        accurate_id = get_accurate_id(
            content_hash,
            profile.name,
            profile.model,
            opts.mode,
            False,
            extra=extra,
        )

        if not opts.no_cache:
            cached = db.get_accurate(accurate_id)
            if cached is not None:
                global _was_cached
                _was_cached = True
                if opts.verbose:
                    meta = db.get_accurate_metadata(accurate_id)
                    suffix = (meta or {}).get("verbose_suffix") if meta else None
                    if suffix:
                        return f"{cached}\n\n{suffix}"
                return cached
        else:
            db.evict_accurate(accurate_id)

    opts._verbose_suffix = None

    # Dispatch to mode-specific execution. Each branch sets opts._verbose_suffix
    # to the rendered verbose tail (regardless of opts.verbose) so we can cache
    # it for replay on a future verbose run.
    if opts.mode == "accurate":
        content = _run_accurate(path, kind, opts)
    else:
        content = _run_fast(path, kind, opts)

    suffix = opts._verbose_suffix

    if content_hash and content and not content.startswith("["):
        # TODO: confirm we actually need to run extract_local below
        # extract_local(path, kind)
        uri = str(path.resolve())
        meta = {"verbose_suffix": suffix} if suffix else None
        try:
            db.put_accurate(
                uri=uri,
                content_hash=content_hash,
                profile=profile.name,
                model=profile.model,
                content=content,
                mode=opts.mode,
                detail=False,
                extra=extra,
                metadata=meta,
            )
        except RuntimeError:
            return _with_suffix(content, suffix, opts.verbose)
        if accurate_id:
            try:
                from mm.store.embed import embed_file_chunks

                embed_file_chunks(accurate_id)
            except Exception:
                pass
    return _with_suffix(content, suffix, opts.verbose)


def _with_suffix(content: str, suffix: str | None, verbose: bool) -> str:
    """Append a cached verbose suffix to ``content`` when *verbose* is set."""
    if verbose and suffix:
        return f"{content}\n\n{suffix}"
    return content


def _run_fast(path: Path, kind: FileKind, opts: CatOpts) -> str:
    """Fast mode: local extraction only (no LLM unless pipeline says otherwise).

    For image/video/audio/document kinds this loads a YAML pipeline and
    may invoke an encoder or, if the pipeline defines a ``generate``
    stage, a short LLM call.
    """
    if kind == "text":
        return extract_local(path, kind, no_cache=opts.no_cache)

    from mm.pipelines import apply_overrides

    spec = resolve_pipeline(opts, kind)
    spec = apply_overrides(spec, opts.encode_overrides or None, opts.generate_overrides or None)

    if spec.encode.strategy:
        return run_encoder(path, kind, spec, opts)

    content = extract_local(path, kind, no_cache=opts.no_cache)

    if spec.generate is not None:
        from mm.llm import LlmBackend
        from mm.profile import get_active_profile_name

        t0 = time.monotonic()
        llm = LlmBackend()
        result = llm.generate(
            kind,
            "fast",
            context={"filename": path.name, "content": content[:4000]},
            pipeline_spec=spec,
        )
        elapsed = (time.monotonic() - t0) * 1000
        u = llm.last_usage
        footer = format_footer(path, "fast", elapsed, u.prompt_tokens, u.completion_tokens)

        profile_name = get_active_profile_name()
        generate_output = format_generate_verbose(
            profile_name, elapsed, u.prompt_tokens, u.completion_tokens
        )
        suffix_parts = [generate_output]
        if footer:
            suffix_parts.append(footer)
        opts._verbose_suffix = "\n\n".join(suffix_parts)
        return result

    return content


def _run_accurate(path: Path, kind: BinaryFileKind, opts: CatOpts) -> str:
    """Accurate mode: LLM-powered semantic extraction."""
    from mm.pipelines import apply_overrides

    spec = resolve_pipeline(opts, kind)
    spec = apply_overrides(spec, opts.encode_overrides or None, opts.generate_overrides or None)

    extract_local(path, kind)

    return _accurate_dispatch(path, kind, spec, opts)


def _accurate_dispatch(path: Path, kind: BinaryFileKind, spec: PipelineSpec, opts: CatOpts) -> str:
    """Dispatch accurate-mode extraction based on file kind."""
    if kind == "image":
        return accurate_image(path, spec, opts)
    if kind == "video":
        return accurate_video(path, spec, opts)
    if kind == "audio":
        return accurate_audio(path, spec, opts)

    if spec.encode.strategy:
        return run_encoder(path, kind, spec, opts)

    content = extract_local(path, kind)
    if spec.generate is None:
        return content

    from mm.llm import LlmBackend

    llm = LlmBackend()
    return llm.generate(
        kind,
        "accurate",
        context={"filename": path.name, "content": content[:4000]},
        pipeline_spec=spec,
    )


def _display_rich(
    path: Path,
    content: str,
    mode: str,
    n: int | None,
) -> None:
    from mm.display import output_console

    ext = path.suffix.lstrip(".")
    kind = file_kind(path)
    is_binary = kind in ("image", "document", "video", "audio") or "\x00" in content[:512]

    if not is_binary and ext in (
        "py",
        "rs",
        "js",
        "ts",
        "tsx",
        "jsx",
        "go",
        "java",
        "c",
        "cpp",
        "h",
        "hpp",
        "rb",
        "sh",
        "bash",
        "zsh",
        "yaml",
        "yml",
        "toml",
        "json",
        "md",
        "html",
        "css",
        "sql",
        "xml",
    ):
        from rich.syntax import Syntax

        syntax = Syntax(
            content,
            ext
            if ext
            in (
                "py",
                "rs",
                "js",
                "ts",
                "go",
                "java",
                "c",
                "cpp",
                "rb",
                "bash",
                "yaml",
                "json",
                "md",
                "html",
                "css",
                "sql",
                "xml",
            )
            else "text",
            theme="monokai",
            line_numbers=True,
        )
        output_console.print(syntax)
    else:
        output_console.print(content)
