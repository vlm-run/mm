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
from typing import Annotated, Any, Optional

import typer

from mm.cat_utils import (
    CatOpts,
    coerce_opt_value,
    collect_overrides,
    maybe_confirm_large_cat_batch,
    override_extra,
)
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
        return _extract_local(path, kind, no_cache=opts.no_cache)

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
        # TODO: confirm we actually need to run _extract_local below
        # _extract_local(path, kind)
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
        return _extract_local(path, kind, no_cache=opts.no_cache)

    from mm.pipelines import apply_overrides

    spec = resolve_pipeline(opts, kind)
    spec = apply_overrides(spec, opts.encode_overrides or None, opts.generate_overrides or None)

    if spec.encode.strategy:
        return _run_encoder(path, kind, spec, opts)

    content = _extract_local(path, kind, no_cache=opts.no_cache)

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
        footer = _format_footer(path, "fast", elapsed, u.prompt_tokens, u.completion_tokens)

        profile_name = get_active_profile_name()
        generate_output = _format_generate_verbose(
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

    _extract_local(path, kind)

    return _accurate_dispatch(path, kind, spec, opts)


def _accurate_dispatch(path: Path, kind: BinaryFileKind, spec: PipelineSpec, opts: CatOpts) -> str:
    """Dispatch accurate-mode extraction based on file kind."""
    if kind == "image":
        return _accurate_image(path, spec, opts)
    if kind == "video":
        return _accurate_video(path, spec, opts)
    if kind == "audio":
        return _accurate_audio(path, spec, opts)

    if spec.encode.strategy:
        return _run_encoder(path, kind, spec, opts)

    content = _extract_local(path, kind)
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


def _format_generate_verbose(
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


def _format_pipeline_tree(encode_info: str, generate_info: str | None = None) -> str:
    """Format pipeline steps as a tree structure."""
    encode_text = (
        encode_info.replace("[dim]", "").replace("[/dim]", "").replace("Encode: ", "encode: ")
    )

    if generate_info:
        generate_text = generate_info.replace("[dim]", "").replace("[/dim]", "")
        pipeline = f"pipeline\n  ├─ {encode_text}\n  └─ {generate_text}"
    else:
        pipeline = f"pipeline\n  └─ {encode_text}"
    return f"[dim]{pipeline}[/dim]"


def _format_footer(
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


def _format_encode_verbose(strategy: str | None, messages: list[dict], elapsed_ms: float) -> str:
    """Format verbose output for the encode step."""
    from mm.display import format_time

    if not strategy:
        strategy = "unknown"

    # Count part types
    text_count = 0
    image_count = 0
    total_parts = 0

    for msg in messages:
        content = msg.get("content", [])
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    total_parts += 1
                    part_type = part.get("type", "unknown")
                    if part_type == "text":
                        text_count += 1
                    elif part_type == "image_url" or "inline_data" in part:
                        image_count += 1

    # Format part summary
    part_details = []
    if text_count > 0:
        part_details.append(f"{text_count} text" if text_count == 1 else f"{text_count} texts")
    if image_count > 0:
        part_details.append(f"{image_count} image" if image_count == 1 else f"{image_count} images")

    part_summary = ", ".join(part_details)
    encode_text = (
        f"Encode: {strategy} • {format_time(elapsed_ms)} → {total_parts} parts ({part_summary})"
    )

    return f"[dim]{encode_text}[/dim]"


def _run_encoder(path: Path, kind: str, spec: PipelineSpec, opts: CatOpts) -> str:
    """Run a named encoder strategy and output JSON messages or pipe to LLM."""
    from mm.encoders import get as get_encoder

    assert spec.encode.strategy is not None
    t_encode = time.monotonic()
    strat = get_encoder(spec.encode.strategy)
    messages = list(strat.encode(path, **spec.encode.strategy_opts))
    encode_elapsed = (time.monotonic() - t_encode) * 1000

    if spec.generate is None:
        text_parts: list[str] = []
        for msg in messages:
            content = msg.get("content", [])
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text = part.get("text", "")
                        if text:
                            text_parts.append(text)
            elif isinstance(content, str):
                if content:
                    text_parts.append(content)

        result = "\n\n".join(text_parts) if text_parts else ""

        encode_output = _format_encode_verbose(spec.encode.strategy, messages, encode_elapsed)
        opts._verbose_suffix = _format_pipeline_tree(encode_output)
        return result

    from mm.llm import LlmBackend
    from mm.profile import get_active_profile_name

    t0 = time.monotonic()
    llm = LlmBackend()
    chunks: list[list[dict]] = []
    for msg in messages:
        parts = _extract_llm_parts(msg)
        if parts:
            chunks.append(parts)

    if not chunks:
        return "[No LLM-compatible content parts from encoder]"

    ctx = {"filename": path.name}
    if len(chunks) == 1:
        result = llm.generate(kind, opts.mode, context=ctx, parts=chunks[0], pipeline_spec=spec)
    else:
        result = llm.generate_chunked(
            kind, opts.mode, context=ctx, chunks=chunks, pipeline_spec=spec
        )

    elapsed = (time.monotonic() - t0) * 1000
    u = llm.last_usage

    encode_output = _format_encode_verbose(spec.encode.strategy, messages, encode_elapsed)
    profile_name = get_active_profile_name()
    generate_output = _format_generate_verbose(
        profile_name, elapsed, u.prompt_tokens, u.completion_tokens
    )
    opts._verbose_suffix = _format_pipeline_tree(encode_output, generate_output)
    return result


def _accurate_image(path: Path, spec: PipelineSpec, opts: CatOpts) -> str:
    """Image extraction with mode-specific LLM prompts."""
    if spec.encode.strategy:
        return _run_encoder(path, "image", spec, opts)

    from mm.llm import LlmBackend, image_part
    from mm.profile import get_active_profile_name

    t0 = time.monotonic()
    llm = LlmBackend()
    parts = [image_part(path)]
    content = llm.generate(
        "image",
        "accurate",
        context={"filename": path.name},
        parts=parts,
        pipeline_spec=spec,
    )
    elapsed = (time.monotonic() - t0) * 1000
    u = llm.last_usage

    profile_name = get_active_profile_name()
    generate_output = _format_generate_verbose(
        profile_name, elapsed, u.prompt_tokens, u.completion_tokens
    )
    footer = _format_footer(path, "accurate", elapsed, u.prompt_tokens, u.completion_tokens)
    suffix_parts = [generate_output]
    if footer:
        suffix_parts.append(footer)
    opts._verbose_suffix = "\n\n".join(suffix_parts)
    return content


def _accurate_video(path: Path, spec: PipelineSpec, opts: CatOpts) -> str:
    """Video extraction with mode-aware mosaic + whisper + LLM pipeline."""
    import shutil

    from mm.ffmpeg import (
        extract_audio,
        extract_frames_at_timestamps,
        extract_uniform_mosaics,
        ffmpeg_available,
        probe_duration,
        tile_frames_to_mosaics,
    )
    from mm.llm import LlmBackend, image_part

    if not ffmpeg_available():
        return f"[ffmpeg not found — cannot process {path.name}]"

    if spec.generate is None:
        return _extract_local(path, "video", no_cache=opts.no_cache)

    # The hard-coded mosaic+whisper fast path only implements a fixed
    # set of strategies. Anything else (e.g. video-gemini, frame-sample)
    # must be routed through the generic encoder runner so we only
    # report stages that actually ran.
    _VIDEO_NATIVE = {"frames-transcript", "video-frames-transcript", "mosaic", "video-mosaic"}
    if spec.encode.strategy and spec.encode.strategy not in _VIDEO_NATIVE:
        return _run_encoder(path, "video", spec, opts)

    timing: dict[str, float] = {}
    t_total = time.monotonic()

    duration = probe_duration(path)
    if duration <= 0:
        return f"[Could not determine duration for {path.name}]"

    from concurrent.futures import Future, ThreadPoolExecutor

    ekw = dict(spec.encode.strategy_opts)
    tile_spec = ekw.get("mosaic_tile") or "4x4"
    tile_cols, tile_rows = _parse_tile(tile_spec)
    num_mosaics = ekw.get("mosaic_count") or 8
    num_frames = _adaptive_num_frames(path, duration, ekw)

    thumb_width = ekw.get("mosaic_image_width") or (1500 // tile_cols)

    use_scenes = True

    def _extract_visual_and_vlm() -> tuple[list[Path], str]:
        t0 = time.monotonic()
        if use_scenes:
            from mm.common.video.shot_detection import (
                detect_scenes,
                sample_scene_timestamps,
                sample_uniform_timestamps,
                scenedetect_available,
            )

            if scenedetect_available():
                t_scene = time.monotonic()
                scene_result = detect_scenes(path)
                timing["scene_detection_ms"] = (time.monotonic() - t_scene) * 1000
                if scene_result.scenes:
                    timestamps = sample_scene_timestamps(scene_result.scenes, num_frames)
                else:
                    timestamps = sample_uniform_timestamps(duration, num_frames)
            else:
                timestamps = sample_uniform_timestamps(duration, num_frames)

            frames = extract_frames_at_timestamps(
                path,
                timestamps,
                thumb_width=thumb_width,
                out_dir=opts.output_dir,
            )
            timing["frame_extraction_ms"] = (time.monotonic() - t0) * 1000

            t_tile = time.monotonic()
            mosaics = tile_frames_to_mosaics(
                frames,
                tile_cols=tile_cols,
                tile_rows=tile_rows,
                stem=path.stem,
                out_dir=opts.output_dir,
            )
            timing["mosaic_assembly_ms"] = (time.monotonic() - t_tile) * 1000
        else:
            result = extract_uniform_mosaics(
                path,
                out_dir=opts.output_dir,
                tile_cols=tile_cols,
                tile_rows=tile_rows,
                thumb_width=thumb_width,
                num_mosaics=num_mosaics,
            )
            mosaics = result.mosaic_paths
            timing["frame_extraction_ms"] = result.elapsed_ms

        if not mosaics:
            return mosaics, ""

        dur_ctx = ""
        if duration > 0:
            mins, secs = divmod(duration, 60)
            dur_ctx = f" Duration: {int(mins)}m{secs:.0f}s."

        t_vlm = time.monotonic()
        llm = LlmBackend()
        img_parts = [image_part(mp, mime="image/jpeg") for mp in mosaics]
        analysis = llm.generate(
            "video",
            "accurate",
            context={"filename": path.name, "duration_ctx": dur_ctx},
            parts=img_parts,
            pipeline_spec=spec,
        )
        timing["vlm_call_ms"] = (time.monotonic() - t_vlm) * 1000
        timing["vlm_prompt_tokens"] = llm.last_usage.prompt_tokens
        timing["vlm_completion_tokens"] = llm.last_usage.completion_tokens
        return mosaics, analysis

    def _extract_audio_transcript() -> str:
        if not ekw.get("transcribe"):
            return ""

        from mm.whisper import whisper_available

        if not whisper_available():
            return ""

        whisper_model = ekw.get("whisper_model") or "medium"
        audio_speed = ekw.get("audio_speed") or 1.0
        beam_size = 5

        t_audio = time.monotonic()
        audio_result = extract_audio(path, speed=audio_speed)
        timing["audio_extraction_ms"] = (time.monotonic() - t_audio) * 1000

        from mm.whisper import transcribe

        whisper_result = transcribe(
            audio_result.path,
            model_size=whisper_model,
            beam_size=beam_size,
            audio_speed=audio_speed,
        )
        timing["audio_transcription_ms"] = whisper_result.elapsed_ms

        try:
            audio_result.path.unlink(missing_ok=True)
        except Exception:
            pass
        return whisper_result.text

    with ThreadPoolExecutor(max_workers=2) as pool:
        visual_future: Future[tuple[list[Path], str]] = pool.submit(_extract_visual_and_vlm)
        audio_future: Future[str] = pool.submit(_extract_audio_transcript)
        mosaic_paths, analysis = visual_future.result()
        transcript = audio_future.result()

    if not mosaic_paths:
        return f"[No frames extracted from {path.name}]"

    timing["total_ms"] = (time.monotonic() - t_total) * 1000

    if opts.output_dir is None:
        for mp in mosaic_paths:
            try:
                parent = mp.parent
                mp.unlink(missing_ok=True)
                if parent.name.startswith("mm_"):
                    shutil.rmtree(parent, ignore_errors=True)
            except Exception:
                pass

    out_parts: list[str] = [analysis]
    if transcript:
        word_count = len(transcript.split())
        out_parts.append(f"\n## Transcript ({word_count} words)\n{transcript}")

    token_keys = {k: v for k, v in timing.items() if "tokens" in k}
    prompt_tokens = int(token_keys.get("vlm_prompt_tokens", 0))
    completion_tokens = int(token_keys.get("vlm_completion_tokens", 0))

    from mm.profile import get_active_profile_name

    profile_name = get_active_profile_name()
    generate_output = _format_generate_verbose(
        profile_name, timing["total_ms"], prompt_tokens, completion_tokens
    )
    footer = _format_footer(path, "accurate", timing["total_ms"], prompt_tokens, completion_tokens)
    suffix_parts = [generate_output]
    if footer:
        suffix_parts.append(footer)
    opts._verbose_suffix = "\n\n".join(suffix_parts)

    return "\n".join(out_parts)


def _accurate_audio(path: Path, spec: PipelineSpec, opts: CatOpts) -> str:
    """Audio extraction with transcription."""
    from mm.ffmpeg import extract_audio, ffmpeg_available
    from mm.whisper import transcribe, whisper_available

    if not ffmpeg_available():
        return f"[ffmpeg not found — cannot process {path.name}]"

    if not whisper_available():
        return (
            "[whisper not available — faster-whisper should be included in core mm install. "
            "For MLX on Apple Silicon: pip install mm-ctx[mlx]]"
        )

    if spec.generate is None:
        return _extract_local(path, "audio", no_cache=opts.no_cache)

    # The hard-coded whisper+LLM fast path only implements `transcribe`.
    # Anything else (e.g. audio-gemini) must be routed through the
    # generic encoder runner so we only report stages that actually ran.
    _AUDIO_NATIVE = {"transcribe", "audio-transcribe"}
    if spec.encode.strategy and spec.encode.strategy not in _AUDIO_NATIVE:
        return _run_encoder(path, "audio", spec, opts)

    timing: dict[str, float] = {}
    t_total = time.monotonic()

    akw = spec.encode.strategy_opts
    whisper_model = akw.get("whisper_model") or "medium"
    audio_speed = akw.get("audio_speed") or 1.0
    beam_size = 5

    t0 = time.monotonic()
    audio_result = extract_audio(path, speed=audio_speed)
    timing["audio_extraction_ms"] = (time.monotonic() - t0) * 1000

    whisper_result = transcribe(
        audio_result.path,
        model_size=whisper_model,
        beam_size=beam_size,
        audio_speed=audio_speed,
    )
    timing["audio_transcription_ms"] = whisper_result.elapsed_ms
    transcript = whisper_result.text

    try:
        audio_result.path.unlink(missing_ok=True)
    except Exception:
        pass

    if not transcript or transcript.startswith("["):
        return transcript or "[No speech detected]"

    from mm.llm import LlmBackend

    t_llm = time.monotonic()
    llm = LlmBackend()
    summary = llm.generate(
        "audio",
        "accurate",
        context={"filename": path.name, "transcript": transcript},
        pipeline_spec=spec,
    )
    timing["llm_call_ms"] = (time.monotonic() - t_llm) * 1000
    timing["total_ms"] = (time.monotonic() - t_total) * 1000
    u = llm.last_usage

    word_count = len(transcript.split())
    result = f"{summary}\n\n[Transcript: {word_count} words]"

    from mm.profile import get_active_profile_name

    profile_name = get_active_profile_name()
    generate_output = _format_generate_verbose(
        profile_name, timing["total_ms"], u.prompt_tokens, u.completion_tokens
    )
    footer = _format_footer(
        path, "accurate", timing["total_ms"], u.prompt_tokens, u.completion_tokens
    )
    suffix_parts = [generate_output]
    if footer:
        suffix_parts.append(footer)
    opts._verbose_suffix = "\n\n".join(suffix_parts)

    return result


def _extract_local(path: Path, kind: str, *, no_cache: bool = False) -> str:
    """Run local content extraction (no LLM) with caching.

    Dispatches to the appropriate extractor based on file kind: image
    metadata, video metadata, PDF text, or raw text passthrough.
    """
    from mm.store.db import MmDatabase
    from mm.store.utils import get_content_hash

    content_hash = get_content_hash(path)
    if not no_cache and content_hash:
        cached = MmDatabase().get_fast(content_hash)
        if cached is not None:
            return cached

    def _handler() -> str:
        if kind == "image":
            return _local_image(path)
        if kind == "video":
            return _local_video(path)
        if kind == "audio":
            return _local_audio(path)
        if kind == "document":
            return _local_document(path)
        return path.read_text(errors="replace")

    result = _handler()
    if content_hash and result and not result.startswith("["):
        MmDatabase().put_fast(str(path.resolve()), content_hash, result)
    return result


def _local_image(path: Path) -> str:
    try:
        from mm._mm import Scanner
        from mm.display import format_size

        scanner = Scanner(str(path.parent))
        scanner.scan()
        r = scanner.extract_fast(path.name)
        parts: list[str] = []
        if r.dimensions:
            parts.append(f"Dimensions: {r.dimensions}")
        if r.magic_mime:
            parts.append(f"MIME:       {r.magic_mime}")
        if size_str := format_size(path.stat().st_size):
            parts.append(f"Size:       {size_str}")
        if r.content_hash:
            parts.append(f"Hash:       {r.content_hash}")
        if r.phash is not None:
            parts.append(f"pHash:      {r.phash:016x}")
        if r.exif_camera:
            parts.append(f"Camera:     {r.exif_camera}")
        if r.exif_date:
            parts.append(f"Date:       {r.exif_date}")
        if r.exif_gps:
            parts.append(f"GPS:        {r.exif_gps}")
        if r.exif_orientation:
            parts.append(f"Orientation: {r.exif_orientation}")
        return "\n".join(parts) if parts else f"[Image: {path.name}]"
    except Exception as e:
        return f"[Image extraction failed: {e}]"


def _local_video(path: Path) -> str:
    """Metadata only — no ffmpeg, <100ms."""
    try:
        from mm._mm import Scanner
        from mm.display import format_size

        scanner = Scanner(str(path.parent))
        scanner.scan()
        r = scanner.extract_fast(path.name)
        parts: list[str] = []
        if r.dimensions:
            parts.append(f"Resolution: {r.dimensions}")
        if r.duration_s is not None:
            mins, secs = divmod(r.duration_s, 60)
            parts.append(f"Duration:   {int(mins)}m {secs:.1f}s ({r.duration_s:.2f}s)")
        if size_str := format_size(path.stat().st_size):
            parts.append(f"Size:       {size_str}")
        if r.fps:
            parts.append(f"FPS:        {r.fps}")
        if r.video_codec:
            parts.append(f"Video:      {r.video_codec}")
        if r.audio_codec:
            parts.append(f"Audio:      {r.audio_codec}")
        elif r.has_audio is False:
            parts.append("Audio:      none")
        if r.content_hash:
            parts.append(f"Hash:       {r.content_hash}")
        return "\n".join(parts) if parts else f"[Video: {path.name}]"
    except Exception as e:
        return f"[Video extraction failed: {e}]"


def _local_audio(path: Path) -> str:
    """Metadata only — no ffmpeg, <100ms."""
    try:
        from mm._mm import Scanner
        from mm.display import format_size

        scanner = Scanner(str(path.parent))
        scanner.scan()
        r = scanner.extract_fast(path.name)
        parts: list[str] = []
        if r.duration_s is not None:
            mins, secs = divmod(r.duration_s, 60)
            parts.append(f"Duration: {int(mins)}m {secs:.1f}s ({r.duration_s:.2f}s)")
        if size_str := format_size(path.stat().st_size):
            parts.append(f"Size:     {size_str}")
        if r.audio_codec:
            parts.append(f"Codec:    {r.audio_codec}")
        if r.content_hash:
            parts.append(f"Hash:     {r.content_hash}")
        return "\n".join(parts) if parts else f"[Audio: {path.name}]"
    except Exception as e:
        return f"[Audio extraction failed: {e}]"


def _local_document(path: Path) -> str:
    """Extract document content."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _local_pdf(path)

    try:
        from mm.docs_extract import extract_docx, extract_pptx

        if ext == ".pptx":
            return extract_pptx(str(path))
        return extract_docx(str(path))
    except Exception as e:
        return f"[Document extraction failed for {path.name}: {e}]"


def _local_pdf(path: Path) -> str:
    """Fallback PDF text extraction via pypdfium2."""
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        pages_text: list[str] = []
        for i in range(len(pdf)):
            page = pdf[i]
            textpage = page.get_textpage()
            pages_text.append(textpage.get_text_range())
            textpage.close()
            page.close()
        pdf.close()
        text = "\n\n".join(pages_text).strip()
        if not text:
            return "[No extractable text — this PDF may contain scanned images only]"
        return text
    except Exception as e:
        return f"[PDF extraction failed: {e}]"


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


def _extract_llm_parts(msg: dict) -> list[dict]:
    """Extract OpenAI-compatible content parts from a Message dict."""
    parts: list[dict] = []
    content = msg.get("content", [])
    if isinstance(content, list):
        for part in content:
            if "inline_data" in part:
                idata = part["inline_data"]
                mime = idata.get("mime_type", "")
                b64 = idata.get("data", "")
                if mime.startswith("video/"):
                    continue
                parts.append(
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
                )
            else:
                parts.append(part)
    elif isinstance(content, str):
        parts.append({"type": "text", "text": content})
    return parts


_VIDEO_HEAVY_DURATION_S = 30 * 60
_VIDEO_HEAVY_SIZE_B = 500 * 1024 * 1024
_VIDEO_HEAVY_NUM_FRAMES = 64
_VIDEO_DEFAULT_NUM_FRAMES = 128


def _adaptive_num_frames(path: Path, duration: float, ekw: dict[str, Any]) -> int:
    """Adapt opts for long or large videos."""
    is_long = duration > _VIDEO_HEAVY_DURATION_S
    is_large = path.stat().st_size > _VIDEO_HEAVY_SIZE_B
    if not (is_long or is_large):
        return _VIDEO_DEFAULT_NUM_FRAMES

    from mm.display import console

    reasons: list[str] = []
    if is_long:
        reasons.append(f"duration {(duration / 60):.0f}min > 30min")
    if is_large:
        reasons.append(f"size {(path.stat().st_size / (1024 * 1024)):.0f}MB > 500MB")
    console.print(
        f"[dim]Video auto-tune ({', '.join(reasons)}): frames={_VIDEO_HEAVY_NUM_FRAMES}.[/dim]"
    )
    return _VIDEO_HEAVY_NUM_FRAMES


def _parse_tile(tile: str) -> tuple[int, int]:
    parts = tile.lower().split("x")
    if len(parts) == 2:
        return int(parts[0]), int(parts[1])
    n = int(parts[0])
    return n, n
