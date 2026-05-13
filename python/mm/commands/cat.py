"""mm cat -- unified content extraction with pipeline-driven modes."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Optional

import typer

from mm.cat_utils.base_utils import (
    CatOpts,
    RunResult,
    coerce_opt_value,
    collect_overrides,
    effective_model,
    format_footer,
    format_generate_verbose,
    make_llm_from_spec,
    maybe_confirm_large_cat_batch,
    override_extra,
    spec_extra_body,
)
from mm.cat_utils.extract_meta import extract_meta
from mm.common.audio._base import BackendLabel
from mm.pipe import read_paths_from_stdin
from mm.utils import Format, file_kind

if TYPE_CHECKING:
    from mm.constants import BinaryFileKind
    from mm.pipelines.schema import PipelineSpec

# Track total bytes processed for throughput calculation
_total_bytes_processed = 0
# Track whether the result was served from cache
_was_cached: bool = False


def _validate_extra_body_json(raw: str | None) -> str | None:
    """Validate ``--generate.extra-body`` is a JSON object before pipeline coercion.

    Returns the original string (so ``apply_overrides``'s ``_coerce_generate``
    can parse it once); raises ``typer.Exit(1)`` with a friendly error
    message if the string is not valid JSON or does not decode to a dict.
    """
    if raw is None:
        return None

    import json

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        typer.echo(f"Error: --generate.extra-body must be a JSON object: {e}", err=True)
        raise typer.Exit(1) from e
    if not isinstance(parsed, dict):
        typer.echo(
            f"Error: --generate.extra-body must decode to a JSON object, "
            f"got {type(parsed).__name__}",
            err=True,
        )
        raise typer.Exit(1)
    return raw


def cat_cmd(
    # -- Most important options first (Typer renders in declaration order) --
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            "-m",
            help=(
                "Processing mode: fast or accurate [default: fast]. "
                "For raw file metadata, use ``mm peek <file_path>``."
            ),
        ),
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
    no_generate: Annotated[
        bool,
        typer.Option(
            "--no-generate",
            help=(
                "Skip the generate (LLM) step — emit only the encoder's text "
                "parts. Useful for snapshotting encoder behaviour and offline tests."
            ),
        ),
    ] = False,
    format: Annotated[
        Optional[Format],
        typer.Option(
            "--format",
            "-f",
            help=(
                "Output format: json (compact in pipes / indented in TTY), "
                "pretty-json (always indented -- ideal for piping into "
                "markdown / docs / recordings), tsv, csv, dataset-jsonl, "
                "dataset-hf."
            ),
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
    encode_backend: Annotated[
        Optional[BackendLabel],
        typer.Option(
            "--encode.backend",
            help="Override encoder backend (mlx, ctranslate2, or openai)",
        ),
    ] = None,
    encode_model: Annotated[
        Optional[str],
        typer.Option(
            "--encode.model",
            help="Override encoder model (e.g. nvidia/parakeet-tdt-0.6b-v3, whisper-1)",
        ),
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
    # -- Generate overrides (CLI > pipeline YAML > profile default) --
    prompt: Annotated[
        Optional[str],
        typer.Option(
            "--prompt",
            "--generate.prompt",
            help="Override LLM prompt template (alias: --generate.prompt)",
        ),
    ] = None,
    model: Annotated[
        Optional[str],
        typer.Option(
            "--model",
            "--generate.model",
            help=(
                "Override the model for this call, taking precedence over the "
                "pipeline's `generate.model` and the active profile's default "
                "(e.g. 'moondream2', 'qwen3.5-0.8b', 'paddleocr-v5'). "
                "Alias: --generate.model"
            ),
        ),
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
    generate_extra_body: Annotated[
        Optional[str],
        typer.Option(
            "--generate.extra-body",
            help=(
                "JSON object forwarded to the OpenAI SDK's `extra_body` arg, "
                "deep-merged onto the pipeline's `generate.extra_body` (CLI keys win). "
                "Use for provider-specific knobs like vlmrt's "
                "method/method_params/video_fps/image_resolution."
            ),
        ),
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
    Behavior auto-detects from file type. Default mode is 'fast'. For raw
    file metadata (dimensions / EXIF / codec / mime / hash), use ``mm peek``.

    \b
                                fast (default)                  accurate
    Images:                     short VLM caption               full VLM caption + tags
    Videos:                     mosaic → short VLM              mosaic + transcript → VLM
    Audio:                      Whisper transcript              transcript → LLM summary
    PDFs:                       page-text extraction            text → LLM markdown
    Non-PDF docs (.docx/.pptx): passthrough text (no LLM)       passthrough text (no LLM)
    Code / text:                passthrough text (no LLM)       passthrough text (no LLM)

    Non-PDF docs and code/text always passthrough; ``--mode`` is a no-op
    for those kinds. Chunks are written on first sight.

    \b
    Examples:
      mm cat main.py                        # passthrough text (kind=text)
      mm cat notes.docx                     # passthrough text (kind=document, non-PDF)
      mm cat paper.pdf                      # PDF page-text extraction (fast pipeline)
      mm cat photo.png                      # short VLM caption (fast pipeline)
      mm cat photo.png -m accurate          # full VLM description
      mm cat video.mp4 -m accurate          # mosaic → VLM
      mm cat photo.png -p tile              # use named encoder
      mm cat photo.png -m accurate -p my-pipeline.yaml
                                            # custom pipeline YAML
      mm cat photo.png -m accurate --encode.strategy_opts max_width=768
                                            # override a single strategy_opts entry
      mm cat photo.png -m accurate --prompt "<new_prompt>"
                                            # override the default pipeline prompt
      mm cat --print-pipeline image/accurate
                                            # inspect the pipeline YAML source

    \b
    Override surfaces (right-most layer wins on conflict):
      profile (mm.toml)  ->  pipeline YAML (generate.*)  ->  CLI flags
        base_url              prompt                          --prompt / --generate.prompt
        api_key               model                           --model  / --generate.model
        model (default)       max_tokens                      --generate.max-tokens
                              temperature                     --generate.temperature
                              json_mode                       --generate.json-mode
                              extra_body (deep-merged)        --generate.extra-body

    \b
    Per-call provider/model/extra-body overrides (e.g. vlmrt deployments):
      # Florence-2 OCR on a scanned page
      mm --profile vlmrt cat page.png -m accurate \\
        --model florence-2-base-ft \\
        --generate.extra-body '{"method":"ocr"}'

      # Moondream2 object detection
      mm --profile vlmrt cat photo.jpg -m accurate \\
        --model moondream2 \\
        --generate.extra-body '{"method":"detect","method_params":{"object":"fish"}}'

      # PaddleOCR scene-text recognition (Chinese, custom score threshold)
      mm --profile vlmrt cat storefront.jpg -m accurate \\
        --model paddleocr-v5 \\
        --generate.extra-body '{"method":"ocr","method_params":{"lang":"ch","score_threshold":0.6}}'

      # Qwen3.5 video summarization with frame sampling knobs
      mm --profile vlmrt cat clip.mp4 -m accurate \\
        --model qwen3.5-0.8b \\
        --prompt "Summarize this clip in two sentences." \\
        --generate.extra-body '{"video_fps":1.0,"video_max_frames":8}'
    """
    if list_pipelines:
        from mm.pipelines.pipelines_utils import do_list_pipelines

        do_list_pipelines()
        return
    if list_encoders:
        from mm.encoders.encoders_utils import do_list_encoders

        do_list_encoders()
        return
    if print_pipeline is not None:
        from mm.pipelines.pipelines_utils import do_print_pipeline

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
        typer.echo(
            f"Error: Unknown mode {mode!r}. Use 'fast' or 'accurate'. ",
            err=True,
        )
        raise typer.Exit(1)

    enc_overrides: dict[str, str | dict[str, str]] = {
        **collect_overrides(
            strategy=encode_strategy,
            pyfunc=encode_pyfunc,
            backend=encode_backend,
            model=encode_model,
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

    gen_overrides: dict[str, Any] = collect_overrides(
        prompt=prompt,
        model=model,
        max_tokens=generate_max_tokens,
        temperature=generate_temperature,
        json_mode=generate_json_mode,
    )
    validated_extra_body = _validate_extra_body_json(generate_extra_body)
    if validated_extra_body is not None:
        gen_overrides["extra_body"] = validated_extra_body

    # -- Load explicit pipeline/-p args (YAML files or named encoders) keyed by kind --
    pipeline_specs: dict[str, PipelineSpec] = {}
    if pipeline:
        from mm.pipelines.pipelines_utils import load_pipeline_args

        pipeline_specs = load_pipeline_args(pipeline)

    from mm.display import resolve_format

    fmt = resolve_format(format.value if format else None)

    opts = CatOpts(
        n=n,
        output_dir=output_dir,
        mode=mode,
        no_cache=no_cache,
        no_generate=no_generate,
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

    valid_paths: list[Path] = []
    for file_path in paths:
        p = Path(file_path)
        if not p.exists():
            typer.echo(f"Error: {file_path} not found.", err=True)
            from mm.store.utils import prune_missing

            prune_missing(uris=[str(p.resolve())])
            continue
        valid_paths.append(p)
        _total_bytes_processed += p.stat().st_size

    def _process(p: Path) -> str:
        content = _extract(p, opts)
        if n is not None:
            lines = content.splitlines()
            content = "\n".join(lines[:n] if n >= 0 else lines[n:])
        return content

    def _render(p: Path, content: str) -> None:
        nonlocal _emitted
        if fmt in ("json", "pretty-json", "dataset-jsonl", "dataset-hf"):
            if fmt in ("json", "pretty-json"):
                # ``pretty-json`` shares the wire shape with ``json`` --
                # only the serializer indentation differs (always
                # indented vs TTY-conditional). Same {path, mode,
                # content} envelope so downstream parsers don't have
                # to special-case the format flag.
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

    if valid_paths:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=min(8, len(valid_paths))) as pool:
            futures = [pool.submit(_process, p) for p in valid_paths]
            for p, fut in zip(valid_paths, futures, strict=True):
                try:
                    content = fut.result()
                except Exception as exc:
                    typer.echo(f"Error processing {p}: {exc}", err=True)
                    continue
                _render(p, content)

    if fmt in ("json", "pretty-json", "dataset-jsonl", "dataset-hf") and results:
        from mm.display import emit_rows

        emit_rows(fmt, results, output_dir=str(output_dir) if output_dir else "mm_dataset")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _extract(path: Path, opts: CatOpts) -> str:
    """Pipeline-driven extraction dispatch with unified extraction caching."""
    from mm.constants import OFFICE_EXTS

    global _was_cached
    kind = file_kind(path)
    ext = path.suffix.lower()

    if kind == "text" or (
        kind == "document"
        and (
            (ext != ".pdf" and ext not in OFFICE_EXTS)
            or (ext in OFFICE_EXTS and opts.mode != "accurate")
        )
    ):
        from mm.cat_utils.extract_meta import extract_text

        content, cached = extract_text(path, kind)
        if cached:
            _was_cached = True
        return content

    if opts.no_generate:
        return _no_generate_preview(path, kind, ext, opts)

    from mm.pipelines import apply_overrides
    from mm.pipelines.pipelines_utils import resolve_pipeline
    from mm.profile import get_profile
    from mm.store.utils import get_content_hash, shared_db

    db = shared_db()
    profile = get_profile()

    # Resolve & merge the pipeline spec exactly once so the cache key reflects
    # the effective model and the merged extra_body — required for correct
    # invalidation on `--model` / `--generate.extra-body` changes.
    spec = resolve_pipeline(opts, kind)
    spec = apply_overrides(spec, opts.encode_overrides or None, opts.generate_overrides or None)
    eff_model = effective_model(spec, profile.model)

    content_hash = get_content_hash(path)

    extra = override_extra(
        opts.encode_overrides,
        opts.generate_overrides,
        opts.pipelines,
    )

    extraction_id: str | None = None
    if content_hash:
        from mm.store.utils import get_extraction_id

        extraction_id = get_extraction_id(
            content_hash,
            profile.name,
            eff_model,
            opts.mode,
            False,
            extra=extra,
        )

        if not opts.no_cache:
            cached = db.get_extraction(extraction_id)
            if cached is not None:
                _was_cached = True
                if opts.verbose:
                    meta = db.get_extraction_metadata(extraction_id)
                    suffix = meta.get("verbose_suffix") if meta else None
                    if suffix:
                        return f"{cached}\n\n{suffix}"
                return cached
        else:
            db.evict_extraction(extraction_id)

    # Each branch returns a RunResult carrying the rendered verbose tail
    # (regardless of opts.verbose) so we can persist it for replay on a
    # future cached + verbose run. The merged ``spec`` is threaded down so
    # the LLM call sites read ``spec.generate.{model, extra_body}`` directly.
    if ext in OFFICE_EXTS and opts.mode == "accurate":
        with tempfile.TemporaryDirectory(prefix="mm-office-") as tmpdir:
            from mm._mm import office_to_pdf

            tmp_pdf = Path(tmpdir) / f"{path.stem}.pdf"
            office_to_pdf(str(path), str(tmp_pdf))
            run = _run_accurate(tmp_pdf, kind, spec, opts, meta_path=path)
    elif opts.mode == "accurate":
        run = _run_accurate(path, kind, spec, opts)
    else:
        run = _run_fast(path, kind, spec, opts)

    if content_hash and run.content and not run.content.startswith("["):
        extract_meta(path, kind)
        uri = str(path.resolve())
        meta = {"verbose_suffix": run.verbose_suffix} if run.verbose_suffix else None
        try:
            db.put_extraction(
                uri=uri,
                content_hash=content_hash,
                profile=profile.name,
                model=eff_model,
                content=run.content,
                mode=opts.mode,
                detail=False,
                extra=extra,
                metadata=meta,
            )
        except RuntimeError:
            return _format_run(run, opts.verbose)
    return _format_run(run, opts.verbose)


def _format_run(run: RunResult, verbose: bool) -> str:
    """Render a :class:`RunResult` for display, conditionally including the suffix."""
    if verbose and run.verbose_suffix:
        return f"{run.content}\n\n{run.verbose_suffix}"
    return run.content


def _no_generate_preview(path: Path, kind: str, ext: str, opts: CatOpts) -> str:
    """Render the resolved pipeline for ``path × opts.mode`` without invoking it."""
    from mm.constants import OFFICE_EXTS
    from mm.pipelines import apply_overrides
    from mm.pipelines.pipelines_utils import resolve_pipeline
    from mm.profile import get_profile

    spec = resolve_pipeline(opts, kind)
    spec = apply_overrides(spec, opts.encode_overrides or None, opts.generate_overrides or None)
    header = f"\n# {path} (kind={kind}, mode={opts.mode}) — pipeline preview (--no-generate)"

    encode = spec.encode
    strategy = encode.strategy or "<unspecified>"
    enc_opts = encode.strategy_opts or {}
    enc_opts_str = (
        ", ".join(f"{k}={v}" for k, v in sorted(enc_opts.items())) if enc_opts else "<defaults>"
    )

    if spec.generate is not None:
        gen = spec.generate
        lines = (gen.prompt or "").strip().splitlines()
        first_line = lines[0] if lines else ""
        if len(first_line) > 60:
            first_line = first_line[:60] + "…"

        prompt_part = f' · prompt="{first_line}"' if first_line else ""
        eff = gen.model or get_profile().model
        gen_line = f"generate: model={eff}{prompt_part}  [skipped via --no-generate]"
    else:
        gen_line = "generate: <none>  [encode-only pipeline]"

    if ext in OFFICE_EXTS and opts.mode == "accurate":
        header += " [routes through office→PDF before encode]"

    middle: list[str] = [f"  ├─ encode: {strategy} · {enc_opts_str}"]
    if encode.pyfunc:
        middle.append(f"  ├─ pyfunc: {encode.pyfunc}")

    return "\n".join([header, "pipeline", *middle, f"  └─ {gen_line}"])


def _run_fast(path: Path, kind: BinaryFileKind, spec: PipelineSpec, opts: CatOpts) -> RunResult:
    """Fast mode: run the kind's fast pipeline."""
    if spec.encode.strategy:
        from mm.cat_utils.run_encoder import run_encoder

        return run_encoder(path, kind, spec, opts)

    content = extract_meta(path, kind, no_cache=opts.no_cache)
    if spec.generate is None:
        return RunResult(content=content)

    from mm.profile import get_active_profile_name

    t0 = time.monotonic()
    llm = make_llm_from_spec(spec)
    result = llm.generate(
        kind,
        "fast",
        context={"filename": path.name, "content": content[:4000]},
        pipeline_spec=spec,
        extra_body=spec_extra_body(spec),
    )

    elapsed = (time.monotonic() - t0) * 1000
    u = llm.last_usage
    footer = format_footer(path, "fast", elapsed, u.prompt_tokens, u.completion_tokens)

    profile_name = get_active_profile_name()
    generate_output = format_generate_verbose(
        profile_name, elapsed, u.prompt_tokens, u.completion_tokens
    )
    suffix = "\n\n".join([generate_output, footer])

    return RunResult(content=result, verbose_suffix=suffix)


def _run_accurate(
    path: Path,
    kind: BinaryFileKind,
    spec: PipelineSpec,
    opts: CatOpts,
    *,
    meta_path: Path | None = None,
) -> RunResult:
    """Accurate mode: LLM-powered semantic extraction.

    ``spec`` is the merged (YAML + CLI) pipeline spec resolved by
    ``_extract``; this function does no further override application
    ``meta_path`` reference to the original office file
    """
    extract_meta(meta_path or path, kind, no_cache=opts.no_cache)

    return _accurate_dispatch(path, kind, spec, opts)


def _accurate_dispatch(
    path: Path, kind: BinaryFileKind, spec: PipelineSpec, opts: CatOpts
) -> RunResult:
    """Dispatch accurate-mode extraction based on file kind."""
    from mm.cat_utils.accurate_audio import accurate_audio
    from mm.cat_utils.accurate_image import accurate_image
    from mm.cat_utils.accurate_video import accurate_video

    if kind == "image":
        return accurate_image(path, spec, opts)
    if kind == "video":
        return accurate_video(path, spec, opts)
    if kind == "audio":
        return accurate_audio(path, spec, opts)

    if spec.encode.strategy:
        from mm.cat_utils.run_encoder import run_encoder

        return run_encoder(path, kind, spec, opts)

    content = extract_meta(path, kind)
    if spec.generate is None:
        return RunResult(content=content)

    from mm.profile import get_active_profile_name

    t0 = time.monotonic()
    llm = make_llm_from_spec(spec)
    result = llm.generate(
        kind,
        "accurate",
        context={"filename": path.name, "content": content[:4000]},
        pipeline_spec=spec,
        extra_body=spec_extra_body(spec),
    )
    elapsed = (time.monotonic() - t0) * 1000
    u = llm.last_usage

    profile_name = get_active_profile_name()
    generate_output = format_generate_verbose(
        profile_name, elapsed, u.prompt_tokens, u.completion_tokens
    )
    footer = format_footer(path, "accurate", elapsed, u.prompt_tokens, u.completion_tokens)
    suffix = "\n\n".join([generate_output, footer])

    return RunResult(content=result, verbose_suffix=suffix)


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
