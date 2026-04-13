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

from pathlib import Path
from typing import Annotated, Any, Optional

import typer

from mm.constants import FileKind
from mm.pipe import read_paths_from_stdin
from mm.pipelines.schema import PipelineSpec


def _collect_overrides(**kwargs: str | None) -> dict[str, str]:
    """Collect non-None CLI overrides into a ``{field: value}`` dict."""
    return {k: v for k, v in kwargs.items() if v is not None}


def _build_pipeline_help() -> str:
    """Build the --pipeline / -p help string with dynamically discovered encoder names."""
    try:
        from mm.encoders import list_strategies

        names = list_strategies()
        names_str = ", ".join(names) if names else "none discovered"
    except Exception:
        names_str = "(run --list-pipelines to see)"
    return (
        f"Pipeline: YAML path or encoder name ({names_str}). Repeatable."
    )


def cat_cmd(
    # -- Most important options first (Typer renders in declaration order) --
    mode: Annotated[
        str,
        typer.Option("--mode", "-m", help="Processing mode: fast or accurate [default: fast]"),
    ] = "fast",
    pipeline: Annotated[
        Optional[list[str]],
        typer.Option(
            "--pipeline", "-p",
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
        Optional[str],
        typer.Option("--format", help="Output format: json, tsv, csv, dataset-jsonl, dataset-hf"),
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
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show progress bars")
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
      mm cat paper.pdf                    # text extraction (fast)
      mm cat photo.png -m accurate        # VLM description
      mm cat video.mp4 -m accurate        # mosaic → VLM
      mm cat photo.png -p tile            # use named encoder
      mm cat photo.png -p my-pipeline.yaml  # custom pipeline YAML
    """
    if list_pipelines:
        _do_list_pipelines()
        return
    if list_encoders:
        _do_list_encoders()
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

    if mode not in ("fast", "accurate"):
        typer.echo(f"Error: Unknown mode {mode!r}. Use 'fast' or 'accurate'.", err=True)
        raise typer.Exit(1)

    enc_overrides = _collect_overrides(
        strategy=encode_strategy,
        pyfunc=encode_pyfunc,
    )
    gen_overrides = _collect_overrides(
        prompt=generate_prompt,
        max_tokens=generate_max_tokens,
        temperature=generate_temperature,
        json_mode=generate_json_mode,
    )

    # -- Load explicit pipeline/-p args (YAML files or named encoders) keyed by kind --
    pipeline_specs: dict[str, PipelineSpec] = {}
    if pipeline:
        pipeline_specs = _load_pipeline_args(pipeline)

    from mm.display import resolve_format

    fmt = resolve_format(format)

    opts = _CatOpts(
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

    multi_file = len(paths) > 1 or bool(stdin_paths)
    results: list[dict] = []

    for file_path in paths:
        p = Path(file_path)
        if not p.exists():
            typer.echo(f"Error: {file_path} not found.", err=True)
            continue

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
                    "type": _file_kind(p),
                    "size": p.stat().st_size,
                }
            results.append(entry)
        elif fmt == "rich":
            _display_rich(p, content, mode, n)
        else:
            if multi_file:
                kind = _file_kind(p)
                size = p.stat().st_size
                print(f"--- {p} ({kind}, {size}B) ---")
            # Use Rich console to properly render markup like [dim]...[/dim]
            from mm.display import output_console
            output_console.print(content)

    if fmt in ("json", "dataset-jsonl", "dataset-hf"):
        from mm.display import emit_rows

        emit_rows(fmt, results, output_dir=str(output_dir) if output_dir else "mm_dataset")


class _CatOpts:
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
    )

    n: int | None
    output_dir: Path | None
    mode: str
    no_cache: bool
    format: str
    encode_overrides: dict[str, str]
    generate_overrides: dict[str, str]
    pipelines: dict[str, PipelineSpec]
    verbose: bool

    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


def _file_kind(path: Path) -> FileKind:
    """Classify a file into a media kind based on its extension."""
    from mm.constants import file_kind

    return file_kind(path.name)


def _load_pipeline_args(pipeline_args: list[str]) -> dict[str, PipelineSpec]:
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
                    kind="_encoder", mode="fast",
                    encode=Encode(strategy=arg),
                    generate=None,
                )
            else:
                # Try as file path anyway
                if p.is_file():
                    from mm.pipelines import load_file

                    for spec in load_file(p):
                        specs[spec.kind] = spec
                else:
                    typer.echo(f"Warning: '{arg}' is not a known encoder or YAML file.", err=True)

    return specs


def _resolve_pipeline(opts: _CatOpts, kind: str) -> PipelineSpec:
    """Return a PipelineSpec from explicit -p pipelines or auto-resolve.

    If -p specified a named encoder (stored under key '_encoder'), that
    overrides for any kind.
    """
    if opts.pipelines:
        spec = opts.pipelines.get(kind) or opts.pipelines.get("_encoder")
        if spec is not None:
            return spec
    from mm.pipelines import load

    return load(kind, opts.mode)


def _extract(path: Path, opts: _CatOpts) -> str:
    """Pipeline-driven extraction dispatch.

    1. Auto-detect kind from file extension
    2. Resolve pipeline (explicit -p > toml override > built-in)
    3. Apply CLI overrides
    4. Run encode step (kind-specific L1 extraction)
    5. If generate is not None: run LLM call
    6. If generate is None: output encode result directly
    """
    kind = _file_kind(path)
    mode = opts.mode

    if mode == "fast":
        return _run_fast(path, kind, opts)
    else:
        return _run_accurate(path, kind, opts)


def _run_fast(path: Path, kind: str, opts: _CatOpts) -> str:
    """Fast mode: local extraction only (no LLM unless pipeline says otherwise).

    For image/video/audio/document kinds this loads a YAML pipeline and
    may invoke an encoder or, if the pipeline defines a ``generate``
    stage, a short LLM call. For text-like kinds (code, config, plain
    text) there is no pipeline — content is passed through directly.
    """
    if kind == "text":
        return _run_l1(path, kind, no_cache=opts.no_cache)

    from mm.pipelines import apply_overrides

    spec = _resolve_pipeline(opts, kind)
    spec = apply_overrides(spec, opts.encode_overrides or None, opts.generate_overrides or None)

    if spec.encode.strategy:
        return _run_encoder(path, kind, spec, opts)

    content = _run_l1(path, kind, no_cache=opts.no_cache)

    if spec.generate is not None:
        import time
        from mm.llm import LlmBackend

        t0 = time.monotonic()
        llm = LlmBackend()
        result = llm.generate(
            kind, "fast",
            context={"filename": path.name, "content": content[:4000]},
            pipeline_spec=spec,
        )
        elapsed = (time.monotonic() - t0) * 1000
        u = llm.last_usage
        footer = _format_footer(path, "fast", elapsed, u.prompt_tokens, u.completion_tokens, opts.verbose)
        return f"{result}\n\n{footer}" if footer else result

    return content


def _run_accurate(path: Path, kind: str, opts: _CatOpts) -> str:
    """Accurate mode: LLM-powered semantic extraction."""
    from mm.pipelines import apply_overrides
    from mm.profile import get_profile
    from mm.store.db import MmDatabase
    from mm.store.util import get_content_hash

    # No pipeline exists for code/text/config — pass content through raw.
    if kind == "text":
        return _run_l1(path, kind, no_cache=opts.no_cache)

    spec = _resolve_pipeline(opts, kind)
    spec = apply_overrides(spec, opts.encode_overrides or None, opts.generate_overrides or None)

    db = MmDatabase()
    profile = get_profile()
    content_hash = get_content_hash(path)

    extra_parts: list[str] = []
    if opts.encode_overrides:
        for k in sorted(opts.encode_overrides):
            extra_parts.append(f"{k}={opts.encode_overrides[k]}")
    if opts.generate_overrides:
        for k in sorted(opts.generate_overrides):
            extra_parts.append(f"g.{k}={opts.generate_overrides[k]}")
    if opts.pipelines:
        for pk in sorted(opts.pipelines):
            extra_parts.append(f"p:{pk}")
    extra = "|".join(extra_parts)

    if content_hash:
        from mm.store.util import get_l2_id

        l2_id = get_l2_id(
            content_hash,
            profile.name,
            profile.model,
            opts.mode,
            False,
            extra=extra,
        )

        if not opts.no_cache:
            value = db.get_l2(l2_id)
            if value is not None:
                return value
        else:
            db.evict_l2(l2_id)

    _run_l1(path, kind)

    result = _accurate_dispatch(path, kind, spec, opts)

    if content_hash and result and not result.startswith("["):
        uri = str(path.resolve())
        db.put_l2(
            uri=uri,
            content_hash=content_hash,
            profile=profile.name,
            model=profile.model,
            content=result,
            mode=opts.mode,
            detail=False,
            extra=extra,
        )
        try:
            from mm.store.embed import embed_file_chunks

            embed_file_chunks(l2_id)
        except Exception:
            pass
    return result


def _accurate_dispatch(path: Path, kind: str, spec: PipelineSpec, opts: _CatOpts) -> str:
    """Dispatch accurate-mode extraction based on file kind."""
    if kind == "image":
        return _accurate_image(path, spec, opts)
    if kind == "video":
        return _accurate_video(path, spec, opts)
    if kind == "audio":
        return _accurate_audio(path, spec, opts)

    if spec.encode.strategy:
        return _run_encoder(path, kind, spec, opts)

    content = _run_l1(path, kind)
    if spec.generate is None:
        return content

    from mm.llm import LlmBackend

    llm = LlmBackend()
    return llm.generate(
        kind, "accurate",
        context={"filename": path.name, "content": content[:4000]},
        pipeline_spec=spec,
    )


def _format_footer(path: Path, mode: str, elapsed_ms: float, prompt_tokens: int = 0, completion_tokens: int = 0, verbose: bool = False) -> str:
    """Format the footer with time, size, mode, profile, and tokens."""
    if not verbose:
        return ""
    
    from mm.display import format_size
    
    size_str = format_size(path.stat().st_size)
    elapsed_s = elapsed_ms / 1000.0
    
    parts = [f"{elapsed_s:.1f}s", size_str, mode]
    
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
    if not strategy:
        strategy = "unknown"
    elapsed_s = elapsed_ms / 1000.0
    part_summary = []
    
    for msg_idx, msg in enumerate(messages):
        content = msg.get("content", [])
        if isinstance(content, list):
            for part_idx, part in enumerate(content):
                if isinstance(part, dict):
                    part_type = part.get("type", "unknown")
                    if part_type == "text":
                        text_len = len(part.get("text", ""))
                        part_summary.append(f"  Message {msg_idx + 1}, Part {part_idx + 1}: text ({text_len} chars)")
                    elif part_type == "image_url" or "inline_data" in part:
                        part_summary.append(f"  Message {msg_idx + 1}, Part {part_idx + 1}: image")
    
    # Use Rich markup for dim styling on entire output
    encode_header = f"Encode: {strategy} • {elapsed_s:.1f}s"
    part_text = "\n".join(part_summary) if part_summary else ""
    
    if part_text:
        full_text = f"{encode_header}\n{part_text}"
    else:
        full_text = encode_header
    
    return f"[dim]{full_text}[/dim]"


def _run_encoder(path: Path, kind: str, spec: PipelineSpec, opts: _CatOpts) -> str:
    """Run a named encoder strategy and output JSON messages or pipe to LLM."""
    import json
    import time

    from mm.encoders import get as get_encoder

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
        
        if opts.verbose:
            encode_output = _format_encode_verbose(spec.encode.strategy, messages, encode_elapsed)
            result = f"{encode_output}\n\n{result}" if result else encode_output
        
        return result

    from mm.llm import LlmBackend

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
        result = llm.generate_chunked(kind, opts.mode, context=ctx, chunks=chunks, pipeline_spec=spec)
    
    elapsed = (time.monotonic() - t0) * 1000
    u = llm.last_usage
    footer = _format_footer(path, opts.mode, elapsed, u.prompt_tokens, u.completion_tokens, opts.verbose)
    
    if opts.verbose:
        encode_output = _format_encode_verbose(spec.encode.strategy, messages, encode_elapsed)
        result = f"{encode_output}\n\n{result}\n\n{footer}" if footer else f"{encode_output}\n\n{result}"
        return result
    
    return f"{result}\n\n{footer}" if footer else result


def _accurate_image(path: Path, spec: PipelineSpec, opts: _CatOpts) -> str:
    """Image extraction with mode-specific LLM prompts."""
    import time

    if spec.encode.strategy:
        return _run_encoder(path, "image", spec, opts)

    from mm.llm import LlmBackend, image_part

    t0 = time.monotonic()
    llm = LlmBackend()
    parts = [image_part(path)]
    content = llm.generate(
        "image", "accurate", context={"filename": path.name}, parts=parts,
        pipeline_spec=spec,
    )
    elapsed = (time.monotonic() - t0) * 1000
    u = llm.last_usage
    footer = _format_footer(path, "accurate", elapsed, u.prompt_tokens, u.completion_tokens, opts.verbose)

    return f"{content}\n\n{footer}" if footer else content


def _accurate_video(path: Path, spec: PipelineSpec, opts: _CatOpts) -> str:
    """Video extraction with mode-aware mosaic + whisper + LLM pipeline."""
    import shutil
    import time

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
        return _run_l1(path, "video", no_cache=opts.no_cache)

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

    ekw = spec.encode.strategy_opts
    tile_spec = ekw.get("mosaic_tile") or "4x4"
    tile_cols, tile_rows = _parse_tile(tile_spec)
    num_mosaics = ekw.get("mosaic_count") or 8
    num_frames = 128

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
            "video", "accurate",
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
    prompt_tokens = int(token_keys.get('vlm_prompt_tokens', 0))
    completion_tokens = int(token_keys.get('vlm_completion_tokens', 0))
    footer = _format_footer(path, "accurate", timing['total_ms'], prompt_tokens, completion_tokens, opts.verbose)
    if footer:
        out_parts.append(f"\n{footer}")
    return "\n".join(out_parts)


def _accurate_audio(path: Path, spec: PipelineSpec, opts: _CatOpts) -> str:
    """Audio extraction with transcription."""
    import time

    from mm.ffmpeg import extract_audio, ffmpeg_available
    from mm.whisper import transcribe, whisper_available

    if not ffmpeg_available():
        return f"[ffmpeg not found — cannot process {path.name}]"

    if not whisper_available():
        return (
            "[whisper not installed — pip install mm[extract] "
            "or pip install mm[extract,mlx] for MLX support on Apple Silicon]"
        )

    if spec.generate is None:
        return _run_l1(path, "audio", no_cache=opts.no_cache)

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
        "audio", "accurate",
        context={"filename": path.name, "transcript": transcript},
        pipeline_spec=spec,
    )
    timing["llm_call_ms"] = (time.monotonic() - t_llm) * 1000
    timing["total_ms"] = (time.monotonic() - t_total) * 1000
    u = llm.last_usage

    word_count = len(transcript.split())
    footer = _format_footer(path, "accurate", timing['total_ms'], u.prompt_tokens, u.completion_tokens, opts.verbose)
    result = f"{summary}\n\n[Transcript: {word_count} words]"
    if footer:
        result += f"\n{footer}"
    return result


def _run_l1(path: Path, kind: str, *, no_cache: bool = False) -> str:
    """Run local content extraction (fast mode) with caching.

    Dispatches to the appropriate extractor based on file kind: image
    metadata, video metadata, PDF text, or raw text passthrough.
    """
    from mm.store.db import MmDatabase
    from mm.store.util import get_content_hash

    content_hash = get_content_hash(path)
    if not no_cache and content_hash:
        cached = MmDatabase().get_l1(content_hash)
        if cached is not None:
            return cached

    def _handler() -> str:
        if kind == "image":
            return _l1_image(path)
        if kind == "video":
            return _l1_video(path)
        if kind == "audio":
            return _l1_audio(path)
        if kind == "document":
            return _l1_document(path)
        return path.read_text(errors="replace")

    result = _handler()
    if content_hash and result and not result.startswith("["):
        MmDatabase().put_l1(str(path.resolve()), content_hash, result)
    return result


def _l1_image(path: Path) -> str:
    try:
        from mm._mm import Scanner
        from mm.display import format_size

        scanner = Scanner(str(path.parent))
        scanner.scan()
        r = scanner.extract_l1(path.name)
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


def _l1_video(path: Path) -> str:
    """Metadata only — no ffmpeg, <100ms."""
    try:
        from mm._mm import Scanner
        from mm.display import format_size

        scanner = Scanner(str(path.parent))
        scanner.scan()
        r = scanner.extract_l1(path.name)
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


def _l1_audio(path: Path) -> str:
    """Metadata only — no ffmpeg, <100ms."""
    try:
        from mm._mm import Scanner
        from mm.display import format_size

        scanner = Scanner(str(path.parent))
        scanner.scan()
        r = scanner.extract_l1(path.name)
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


def _l1_document(path: Path) -> str:
    """Extract document content."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _l1_pdf(path)

    try:
        from mm.docs_extract import extract_docx, extract_pptx

        if ext == ".pptx":
            return extract_pptx(str(path))
        return extract_docx(str(path))
    except Exception as e:
        return f"[Document extraction failed for {path.name}: {e}]"


def _l1_pdf(path: Path) -> str:
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
    kind = _file_kind(path)
    is_binary = kind in ("image", "document", "video", "audio") or "\x00" in content[:512]
    
    if not is_binary and ext in ("py", "rs", "js", "ts", "tsx", "jsx", "go", "java", "c", "cpp", "h", "hpp", "rb", "sh", "bash", "zsh", "yaml", "yml", "toml", "json", "md", "html", "css", "sql", "xml"):
        from rich.syntax import Syntax
        syntax = Syntax(content, ext if ext in ("py", "rs", "js", "ts", "go", "java", "c", "cpp", "rb", "bash", "yaml", "json", "md", "html", "css", "sql", "xml") else "text", theme="monokai", line_numbers=True)
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


def _parse_tile(tile: str) -> tuple[int, int]:
    parts = tile.lower().split("x")
    if len(parts) == 2:
        return int(parts[0]), int(parts[1])
    n = int(parts[0])
    return n, n


_KIND_ORDER = ("image", "video", "audio", "document")


def _do_list_pipelines() -> None:
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

        for kind in _KIND_ORDER:
            for mode in ("fast", "accurate"):
                p = get_pipeline_path(kind, mode)
                if p:
                    rows.insert(0, (p, kind, mode, "—", {}))
    except Exception:
        pass

    kind_rank = {k: i for i, k in enumerate(_KIND_ORDER)}
    mode_rank = {"fast": 0, "accurate": 1}
    rows.sort(key=lambda r: (kind_rank.get(r[1], 99), mode_rank.get(r[2], 99), r[0]))

    home = str(Path.home())
    display_rows: list[tuple[str, str, str, str, dict[str, Any]]] = []
    for yaml_path, kind, mode, encoder, params in rows:
        dp = "~" + yaml_path[len(home):] if yaml_path.startswith(home) else yaml_path
        display_rows.append((dp, kind, mode, encoder, params))

    lines: list[Text] = []
    header = Text(no_wrap=True, overflow="ellipsis")
    header.append("Kind".ljust(10), style="bold cyan")
    header.append("Mode".ljust(10), style="bold cyan")
    header.append("Encoder", style="bold cyan")
    lines.append(header)

    prev_kind = ""
    for dp, kind, mode, encoder, params in display_rows:
        if kind != prev_kind and prev_kind:
            lines.append(Text(""))
        prev_kind = kind

        line = Text(no_wrap=True, overflow="ellipsis")
        line.append(kind.ljust(10), style="white")
        line.append(mode.ljust(10), style="green" if mode == "fast" else "yellow")
        line.append(encoder, style="bold white")
        if params:
            param_str = ", ".join(f"{k}={v}" for k, v in params.items())
            line.append(f"({param_str})", style="green")
        lines.append(line)

        path_line = Text(no_wrap=True, overflow="ellipsis")
        path_line.append(" " * 20)
        path_line.append(dp, style="dim")
        lines.append(path_line)

    body = Text("\n").join(lines)
    max_line = max((len(l.plain) for l in lines), default=60)
    panel_w = max_line + 8
    console = Console(width=max(panel_w, 80))
    panel = Panel(body, title="Pipelines", title_align="left", box=box.ROUNDED, padding=(1, 2), width=panel_w)
    console.print()
    console.print(panel)
    console.print()


def _do_list_encoders() -> None:
    """Print a Rich panel of all registered encoders with descriptions."""
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    from mm.encoders import list_encoders_detail

    entries = list_encoders_detail()

    kind_rank = {k: i for i, k in enumerate(_KIND_ORDER)}
    entries.sort(key=lambda e: (kind_rank.get(e["media_types"][0], 99), e["prefixed_name"]))

    max_name = max((len(e["prefixed_name"]) for e in entries), default=28)
    name_w = max_name + 2
    lines: list[Text] = []
    prev_kind = ""
    for entry in entries:
        cur_kind = entry["media_types"][0] if entry["media_types"] else "unknown"
        if cur_kind != prev_kind and prev_kind:
            lines.append(Text(""))
        prev_kind = cur_kind

        prefixed = entry["prefixed_name"]
        desc = entry["description"]
        params: list[tuple[str, str]] = entry["params"]

        line = Text(no_wrap=True, overflow="ellipsis")
        line.append(prefixed.ljust(name_w), style="bold white")
        line.append(desc, style="white")
        lines.append(line)

        if params:
            param_line = Text(no_wrap=True, overflow="ellipsis")
            param_line.append(" " * name_w)
            param_parts: list[str] = []
            for pname, default in params:
                param_parts.append(f"{pname}={default}")
            param_line.append(", ".join(param_parts), style="green")
            lines.append(param_line)

    body = Text("\n").join(lines)
    max_line = max((len(l.plain) for l in lines), default=60)
    panel_w = max_line + 8
    console = Console(width=max(panel_w, 80))
    panel = Panel(body, title="Encoders", title_align="left", box=box.ROUNDED, padding=(1, 2), width=panel_w)
    console.print()
    console.print(panel)
    console.print()
