"""vlmctx cat -- unified content extraction with auto-detection.

The primary content-inspection command. Behaviour is determined by
(file type x processing level) — no manual mode flags needed.

Processing levels (--level / -l):
  L0  Raw file bytes read as text.
  L1  Structured extraction (default) — type-aware, <100ms per file.
  L2  Semantic understanding via LLM chat/completions.
      Concise ~20-word summary by default, ~80-word with --detail.

File-type behaviour:
  Images   L1: dimensions, MIME, xxh3 hash, EXIF metadata.
           L2: LLM caption via vision model.
  Videos   L1: resolution, duration, FPS, codecs (metadata only, no ffmpeg).
           L2: keyframe mosaic → LLM description.
  Audio    L1: duration, codec, bitrate (metadata only).
           L2: LLM description from metadata.
  PDFs     L1: text extraction via pypdfium2.
           L2: LLM summary of extracted text.
  Code/text  L1: raw text passthrough.
             L2: LLM summary.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from vlmctx.pipe import is_piped_output, read_paths_from_stdin

VIDEO_EXTS = frozenset((
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".m4v", ".mpg", ".mpeg", ".3gp", ".ogv",
))
IMAGE_EXTS = frozenset((
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".svg",
))
AUDIO_EXTS = frozenset((
    ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus",
))
DOCUMENT_EXTS = frozenset((".pdf", ".docx", ".pptx"))


def cat_cmd(
    files: Annotated[Optional[list[Path]], typer.Argument(help="Files to display")] = None,
    level: Annotated[
        int, typer.Option("--level", "-l", help="Processing level (0=raw, 1=extracted, 2=semantic)")
    ] = 1,
    n: Annotated[
        Optional[int],
        typer.Option("-n", help="Line limit: positive = first N (head), negative = last N (tail)"),
    ] = None,
    detail: Annotated[
        bool, typer.Option("--detail", help="L2: deeper ~80-word description (default is ~20-word)")
    ] = False,
    output_dir: Annotated[
        Optional[Path], typer.Option("--output-dir", "-o", help="Output directory for mosaics/audio")
    ] = None,
    max_pages: Annotated[
        Optional[int], typer.Option("--max-pages", help="Max PDF pages to render at L2")
    ] = None,
    mosaic_tile: Annotated[
        str, typer.Option("--mosaic-tile", help="Mosaic tile grid COLSxROWS")
    ] = "6x8",
    image_width: Annotated[
        int, typer.Option("--image-width", help="Thumbnail width in pixels for mosaics")
    ] = 160,
    mosaic_count: Annotated[
        int, typer.Option("--mosaic-count", help="Number of mosaics for video (1-8)")
    ] = 1,
    mosaic_strategy: Annotated[
        str, typer.Option("--mosaic-strategy", help="Video frame selection: uniform, keyframe, scene")
    ] = "uniform",
    audio_speed: Annotated[
        float, typer.Option("--audio-speed", help="Audio playback speed multiplier")
    ] = 2.0,
    audio_sample_rate: Annotated[
        int, typer.Option("--audio-sample-rate", help="Audio sample rate Hz")
    ] = 16000,
    mode: Annotated[
        Optional[str],
        typer.Option("--mode", "-m", help="Extraction mode: fast or accurate (L2 only)"),
    ] = None,
    format: Annotated[
        Optional[str], typer.Option("--format", help="Output format: json, tsv, csv")
    ] = None,
) -> None:
    """Display file content semantically (like bat/cat).

    Behaviour auto-detects from file type. No mode flags needed.

    \b
    Images (png, jpg, gif, webp, bmp, tiff, svg):
      L1  Metadata: dimensions, MIME, xxh3 hash, EXIF.
      L2  LLM caption (~20 words, or ~80 with --detail).

    Videos (mp4, mkv, avi, mov, webm, ...):
      L1  Metadata: resolution, duration, FPS, codecs (<100ms).
      L2  Keyframe mosaic → LLM description.

    Audio (mp3, wav, flac, aac, ogg, m4a, ...):
      L1  Metadata: duration, codec, bitrate (<100ms).
      L2  LLM description.

    PDFs / documents:
      L1  Text extraction via pypdfium2.
      L2  LLM summary of extracted text.

    Code / text / other:
      L0  Raw text with syntax highlighting (TTY).
      L1  Raw text passthrough.
      L2  LLM summary.

    \b
    Examples:
      vlmctx cat paper.pdf                    # extract text (L1)
      vlmctx cat paper.pdf -n 20              # first 20 lines
      vlmctx cat video.mp4                    # metadata (<100ms)
      vlmctx cat video.mp4 -l 2               # mosaic + LLM description
      vlmctx cat photo.png -l 2               # LLM caption (~20 words)
      vlmctx cat photo.png -l 2 --detail      # ~80-word description
    """
    paths: list[str] = []

    stdin_paths = read_paths_from_stdin()
    if stdin_paths:
        paths.extend(stdin_paths)
    if files:
        paths.extend(str(f) for f in files)

    if not paths:
        typer.echo("Error: No files specified.", err=True)
        raise typer.Exit(1)

    from vlmctx.display import resolve_format

    fmt = resolve_format(format)

    opts = _CatOpts(
        level=level, n=n, detail=detail, output_dir=output_dir,
        max_pages=max_pages, mosaic_tile=mosaic_tile, image_width=image_width,
        mosaic_count=mosaic_count, mosaic_strategy=mosaic_strategy,
        audio_speed=audio_speed, audio_sample_rate=audio_sample_rate,
        mode=mode, format=fmt,
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

        if fmt == "json":
            entry: dict = {"path": str(p), "level": level, "content": content}
            if mode:
                entry["mode"] = mode
            results.append(entry)
        elif fmt == "rich":
            _display_rich(p, content, level, n)
        else:
            # When piping multiple files, emit a compact header so LLMs can
            # distinguish which content belongs to which file.
            if multi_file:
                kind = _file_kind(p)
                size = p.stat().st_size
                print(f"--- {p} ({kind}, {size}B) ---")
            print(content)

    if fmt == "json":
        from vlmctx.display import json_dumps

        print(json_dumps(results))


# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------

class _CatOpts:
    """Bag of resolved options threaded through extraction."""

    __slots__ = (
        "level", "n", "detail", "output_dir", "max_pages",
        "mosaic_tile", "image_width", "mosaic_count", "mosaic_strategy",
        "audio_speed", "audio_sample_rate", "mode", "format",
    )

    def __init__(self, **kwargs):  # noqa: ANN003
        for k, v in kwargs.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def _file_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in DOCUMENT_EXTS:
        return "document"
    return "text"


def _extract(path: Path, opts: _CatOpts) -> str:
    """Dispatch extraction based on (file_kind, level)."""
    if opts.level == 0:
        return path.read_text(errors="replace")

    kind = _file_kind(path)

    if opts.level >= 2:
        # When --mode is set, use the new modal extraction pipeline
        if opts.mode is not None:
            return _l2_modal(path, kind, opts)
        return _l2(path, kind, opts)

    return _l1(path, kind)


# ---------------------------------------------------------------------------
# L1 — structured extraction, <100ms per file
# ---------------------------------------------------------------------------

def _l1(path: Path, kind: str) -> str:
    if kind == "image":
        return _l1_image(path)
    if kind == "video":
        return _l1_video(path)
    if kind == "audio":
        return _l1_audio(path)
    if kind == "document":
        return _l1_document(path)
    return path.read_text(errors="replace")


def _l1_image(path: Path) -> str:
    try:
        from vlmctx._vlmctx import Scanner

        scanner = Scanner(str(path.parent))
        scanner.scan()
        r = scanner.extract_l1(path.name)
        parts: list[str] = []
        if r.dimensions:
            parts.append(f"Dimensions: {r.dimensions}")
        if r.magic_mime:
            parts.append(f"MIME:       {r.magic_mime}")
        if r.content_hash:
            parts.append(f"Hash:       {r.content_hash}")
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
        from vlmctx._vlmctx import Scanner

        scanner = Scanner(str(path.parent))
        scanner.scan()
        r = scanner.extract_l1(path.name)
        parts: list[str] = []
        if r.dimensions:
            parts.append(f"Resolution: {r.dimensions}")
        if r.duration_s is not None:
            mins, secs = divmod(r.duration_s, 60)
            parts.append(f"Duration:   {int(mins)}m {secs:.1f}s ({r.duration_s:.2f}s)")
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
        from vlmctx._vlmctx import Scanner

        scanner = Scanner(str(path.parent))
        scanner.scan()
        r = scanner.extract_l1(path.name)
        parts: list[str] = []
        if r.duration_s is not None:
            mins, secs = divmod(r.duration_s, 60)
            parts.append(f"Duration: {int(mins)}m {secs:.1f}s ({r.duration_s:.2f}s)")
        if r.audio_codec:
            parts.append(f"Codec:    {r.audio_codec}")
        if r.content_hash:
            parts.append(f"Hash:     {r.content_hash}")
        return "\n".join(parts) if parts else f"[Audio: {path.name}]"
    except Exception as e:
        return f"[Audio extraction failed: {e}]"


def _l1_document(path: Path) -> str:
    """Extract document content. Uses docling if available, falls back to pypdfium2 for PDFs."""
    from vlmctx.docling_extract import convert_to_markdown, docling_available

    if docling_available():
        result = convert_to_markdown(path)
        return result.markdown

    # Fallback: pypdfium2 for PDFs only
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _l1_pdf_fallback(path)
    return f"[docling not installed — pip install vlmctx[extract] for {ext} support]"


def _l1_pdf_fallback(path: Path) -> str:
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


# ---------------------------------------------------------------------------
# L2 — semantic understanding via LLM
# ---------------------------------------------------------------------------

def _l2(path: Path, kind: str, opts: _CatOpts) -> str:
    if kind == "image":
        return _l2_image(path, opts)
    if kind == "video":
        return _l2_video(path, opts)
    if kind == "audio":
        return _l2_audio(path, opts)

    # document / text: extract L1 text then summarise
    from vlmctx.llm import LlmBackend

    content = _l1(path, kind)
    return LlmBackend().describe(path, content, detail=opts.detail)


def _l2_image(path: Path, opts: _CatOpts) -> str:
    from vlmctx.llm import LlmBackend

    return LlmBackend().caption(path, detail=opts.detail)


def _l2_video(path: Path, opts: _CatOpts) -> str:
    """Generate keyframe mosaic then send to LLM for description."""
    from vlmctx.llm import LlmBackend

    try:
        from vlmctx.ffmpeg import (
            extract_keyframe_mosaics,
            extract_scene_mosaics,
            extract_uniform_mosaics,
            ffmpeg_available,
        )

        if not ffmpeg_available():
            return f"[ffmpeg not found — cannot generate mosaic for {path.name}]"

        cols, rows = _parse_tile(opts.mosaic_tile)
        count = max(1, min(opts.mosaic_count, 8))

        if opts.mosaic_strategy == "uniform":
            result = extract_uniform_mosaics(
                path, out_dir=opts.output_dir, tile_cols=cols, tile_rows=rows,
                thumb_width=opts.image_width, num_mosaics=count,
            )
        elif opts.mosaic_strategy == "scene":
            result = extract_scene_mosaics(
                path, out_dir=opts.output_dir, tile_cols=cols, tile_rows=rows,
                thumb_width=opts.image_width, max_mosaics=count,
            )
        else:
            result = extract_keyframe_mosaics(
                path, out_dir=opts.output_dir, tile_cols=cols, tile_rows=rows,
                thumb_width=opts.image_width, max_mosaics=count,
            )

        if not result.mosaic_paths:
            return f"[No keyframes extracted from {path.name}]"

        llm = LlmBackend()
        info = llm.describe_video(
            result.mosaic_paths,
            video_name=path.name,
            duration_s=result.duration_s,
        )
        return info.get("summary", "") or str(info)

    except Exception as e:
        return f"[Video L2 failed: {e}]"


def _l2_audio(path: Path, opts: _CatOpts) -> str:
    """Describe audio from metadata via LLM."""
    from vlmctx.llm import LlmBackend

    metadata = _l1(path, "audio")
    return LlmBackend().describe(path, metadata, detail=opts.detail)


# ---------------------------------------------------------------------------
# L2 Modal — mode-aware extraction (--mode fast|accurate)
# ---------------------------------------------------------------------------

def _l2_modal(path: Path, kind: str, opts: _CatOpts) -> str:
    """Dispatch modal extraction based on file kind and --mode flag."""
    mode = opts.mode or "fast"
    if mode not in ("fast", "accurate"):
        return f"[Unknown mode: {mode}. Use 'fast' or 'accurate'.]"

    if kind == "image":
        return _l2_image_modal(path, mode)
    if kind == "video":
        return _l2_video_modal(path, opts, mode)
    if kind == "audio":
        return _l2_audio_modal(path, opts, mode)
    if kind == "document":
        # Documents use docling at L1; at L2, summarize via LLM
        from vlmctx.llm import LlmBackend
        content = _l1(path, kind)
        return LlmBackend().describe(path, content, detail=(mode == "accurate"))

    # text/code: summarize
    from vlmctx.llm import LlmBackend
    content = _l1(path, kind)
    return LlmBackend().describe(path, content, detail=(mode == "accurate"))


def _l2_image_modal(path: Path, mode: str) -> str:
    """Image extraction with mode-specific LLM prompts.

    fast:     10-word description + 5 tags
    accurate: 200-word description + 10 tags + 10 objects
    """
    import time

    from vlmctx.llm import LlmBackend

    t0 = time.monotonic()
    content = LlmBackend().caption_modal(path, mode=mode)
    elapsed = (time.monotonic() - t0) * 1000

    return f"{content}\n\n[mode={mode}, {elapsed:.0f}ms]"


def _l2_video_modal(path: Path, opts: _CatOpts, mode: str) -> str:
    """Video extraction with mode-aware mosaic + whisper + LLM pipeline.

    fast (<5min):  16 uniform frames, 1 mosaic, whisper tiny @ 2x
    fast (≥5min):  scene detection → 16 shots, 1 mosaic, whisper tiny @ 2x
    accurate:      scene detection → 128 shots, 8 mosaics, whisper medium @ 1x
    """
    import json as _json
    import shutil
    import time

    from vlmctx.ffmpeg import (
        extract_audio,
        extract_frames_at_timestamps,
        extract_uniform_mosaics,
        ffmpeg_available,
        probe_duration,
        tile_frames_to_mosaics,
    )
    from vlmctx.llm import LlmBackend

    if not ffmpeg_available():
        return f"[ffmpeg not found — cannot process {path.name}]"

    timing: dict[str, float] = {}
    t_total = time.monotonic()

    # 1. Get duration
    duration = probe_duration(path)
    if duration <= 0:
        return f"[Could not determine duration for {path.name}]"

    # 2+3. Frame extraction and audio transcription run in parallel —
    #       they are independent and converge only at the LLM call.
    from concurrent.futures import ThreadPoolExecutor, Future

    tile_cols, tile_rows = 4, 4
    if mode == "accurate":
        num_frames = 128
        num_mosaics = 8
    else:
        num_frames = 16
        num_mosaics = 1

    # Target ~1500px mosaic width
    mosaic_max_width = 1500
    thumb_width = mosaic_max_width // tile_cols  # 375px per tile

    use_scenes = (mode == "accurate") or (mode == "fast" and duration >= 300)

    def _extract_visual() -> list[Path]:
        """Extract frames and assemble mosaics."""
        t0 = time.monotonic()
        if use_scenes:
            from vlmctx.scenes import (
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
                path, timestamps, thumb_width=thumb_width,
                out_dir=opts.output_dir,
            )
            timing["frame_extraction_ms"] = (time.monotonic() - t0) * 1000

            t_tile = time.monotonic()
            mosaics = tile_frames_to_mosaics(
                frames, tile_cols=tile_cols, tile_rows=tile_rows, stem=path.stem,
                out_dir=opts.output_dir,
            )
            timing["mosaic_assembly_ms"] = (time.monotonic() - t_tile) * 1000
        else:
            result = extract_uniform_mosaics(
                path, out_dir=opts.output_dir, tile_cols=tile_cols, tile_rows=tile_rows,
                thumb_width=thumb_width, num_mosaics=num_mosaics,
            )
            mosaics = result.mosaic_paths
            timing["frame_extraction_ms"] = result.elapsed_ms
        return mosaics

    def _extract_audio_transcript() -> str:
        """Extract audio and transcribe with whisper."""
        from vlmctx.whisper import whisper_available
        if not whisper_available():
            return ""

        from vlmctx.config import get_mode_config
        mode_cfg = get_mode_config(mode)

        t_audio = time.monotonic()
        audio_result = extract_audio(path, speed=mode_cfg.audio_speed)
        timing["audio_extraction_ms"] = (time.monotonic() - t_audio) * 1000

        from vlmctx.whisper import transcribe
        whisper_result = transcribe(
            audio_result.path,
            model_size=mode_cfg.whisper_model,
            beam_size=mode_cfg.beam_size or 1,
            audio_speed=mode_cfg.audio_speed,
        )
        timing["whisper_transcription_ms"] = whisper_result.elapsed_ms

        try:
            audio_result.path.unlink(missing_ok=True)
        except Exception:
            pass
        return whisper_result.text

    # Run visual + audio in parallel
    with ThreadPoolExecutor(max_workers=2) as pool:
        visual_future: Future[list[Path]] = pool.submit(_extract_visual)
        audio_future: Future[str] = pool.submit(_extract_audio_transcript)
        mosaic_paths = visual_future.result()
        transcript = audio_future.result()

    if not mosaic_paths:
        return f"[No frames extracted from {path.name}]"

    # 4. Combined LLM analysis
    t_llm = time.monotonic()
    llm = LlmBackend()
    analysis = llm.analyze_video_with_transcript(
        mosaic_paths,
        transcript,
        video_name=path.name,
        duration_s=duration,
        mode=mode,
    )
    timing["llm_call_ms"] = (time.monotonic() - t_llm) * 1000
    timing["total_ms"] = (time.monotonic() - t_total) * 1000

    # 5. Cleanup temp mosaics (unless --output-dir was specified)
    if opts.output_dir is None:
        for mp in mosaic_paths:
            try:
                parent = mp.parent
                mp.unlink(missing_ok=True)
                if parent.name.startswith("vlmctx_"):
                    shutil.rmtree(parent, ignore_errors=True)
            except Exception:
                pass

    # 6. Format output
    parts: list[str] = [analysis]
    if transcript:
        word_count = len(transcript.split())
        parts.append(f"\n[Transcript: {word_count} words]")

    timing_str = " | ".join(f"{k}: {v:.0f}ms" for k, v in timing.items() if k != "total_ms")
    parts.append(f"[mode={mode}, total={timing['total_ms']:.0f}ms | {timing_str}]")
    return "\n".join(parts)


def _l2_audio_modal(path: Path, opts: _CatOpts, mode: str) -> str:
    """Audio extraction with whisper transcription.

    fast:     2x speed + whisper tiny
    accurate: 1x speed + whisper medium
    """
    import time

    from vlmctx.ffmpeg import extract_audio, ffmpeg_available
    from vlmctx.whisper import transcribe, whisper_available

    if not ffmpeg_available():
        return f"[ffmpeg not found — cannot process {path.name}]"

    if not whisper_available():
        return "[whisper not installed — pip install vlmctx[extract]]"

    from vlmctx.config import get_mode_config
    mode_cfg = get_mode_config(mode)

    timing: dict[str, float] = {}
    t_total = time.monotonic()

    # 1. Extract audio
    t0 = time.monotonic()
    audio_result = extract_audio(path, speed=mode_cfg.audio_speed)
    timing["audio_extraction_ms"] = (time.monotonic() - t0) * 1000

    # 2. Transcribe
    whisper_model = mode_cfg.whisper_model
    whisper_result = transcribe(
        audio_result.path,
        model_size=whisper_model,
        beam_size=mode_cfg.beam_size or 1,
        audio_speed=mode_cfg.audio_speed,
    )
    timing["whisper_ms"] = whisper_result.elapsed_ms
    transcript = whisper_result.text

    # Cleanup temp audio
    try:
        audio_result.path.unlink(missing_ok=True)
    except Exception:
        pass

    if not transcript or transcript.startswith("["):
        return transcript or "[No speech detected]"

    # 3. Optionally summarize via LLM
    from vlmctx.llm import LlmBackend

    t_llm = time.monotonic()
    llm = LlmBackend()
    summary = llm.summarize_transcript(transcript, mode=mode, filename=path.name)
    timing["llm_call_ms"] = (time.monotonic() - t_llm) * 1000
    timing["total_ms"] = (time.monotonic() - t_total) * 1000

    # 4. Format output
    word_count = len(transcript.split())
    timing_str = " | ".join(f"{k}: {v:.0f}ms" for k, v in timing.items() if k != "total_ms")
    return (
        f"{summary}\n\n"
        f"[Transcript: {word_count} words, model={whisper_model}]\n"
        f"[mode={mode}, total={timing['total_ms']:.0f}ms | {timing_str}]"
    )


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _display_rich(path: Path, content: str, level: int, n: int | None) -> None:
    from rich import box
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.text import Text

    from vlmctx.display import format_size, output_console

    ext = path.suffix.lstrip(".")
    size_str = format_size(path.stat().st_size)
    level_label = {0: "raw", 1: "extracted", 2: "semantic"}.get(level, f"L{level}")

    subtitle = Text()
    subtitle.append(f"{size_str}", style="bright_blue")
    subtitle.append(f"  L{level} {level_label}", style="dim")

    if n is not None:
        total_lines = len(path.read_text(errors="replace").splitlines()) if level == 0 else None
        if n >= 0:
            subtitle.append(f"  lines 1-{n}", style="dim")
        else:
            subtitle.append(f"  last {abs(n)} lines", style="dim")
        if total_lines:
            subtitle.append(f" of {total_lines}", style="dim")

    lang_map = {
        "py": "python", "rs": "rust", "js": "javascript", "ts": "typescript",
        "tsx": "typescript", "jsx": "javascript", "go": "go", "java": "java",
        "c": "c", "cpp": "cpp", "h": "c", "hpp": "cpp", "rb": "ruby",
        "sh": "bash", "bash": "bash", "zsh": "bash", "yaml": "yaml",
        "yml": "yaml", "toml": "toml", "json": "json", "md": "markdown",
        "html": "html", "css": "css", "sql": "sql", "xml": "xml",
    }

    title = f"[bold]{path}[/bold]"
    safe_content = Text(content) if level >= 2 else content

    kind = _file_kind(path)

    if ext in lang_map and level == 0:
        syntax = Syntax(content, lang_map[ext], theme="monokai", line_numbers=True)
        output_console.print(
            Panel(syntax, title=title, title_align="left", subtitle=subtitle, expand=False, border_style="green", box=box.ROUNDED)
        )
    elif kind == "image":
        output_console.print(
            Panel(safe_content, title=title, title_align="left", subtitle=subtitle, expand=False, border_style="green", box=box.ROUNDED)
        )
    elif kind == "document":
        line_count = len(content.splitlines())
        if line_count > 0:
            subtitle.append(f"  {line_count} lines", style="dim")
        output_console.print(
            Panel(safe_content, title=title, title_align="left", subtitle=subtitle, expand=False, border_style="cyan", box=box.ROUNDED)
        )
    elif kind in ("video", "audio"):
        output_console.print(
            Panel(safe_content, title=title, title_align="left", subtitle=subtitle, expand=False, border_style="magenta", box=box.ROUNDED)
        )
    else:
        output_console.print(
            Panel(safe_content, title=title, title_align="left", subtitle=subtitle, expand=False, border_style="blue", box=box.ROUNDED)
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_tile(tile: str) -> tuple[int, int]:
    parts = tile.lower().split("x")
    if len(parts) == 2:
        return int(parts[0]), int(parts[1])
    n = int(parts[0])
    return n, n
