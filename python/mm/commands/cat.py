"""mm cat -- unified content extraction with auto-detection.

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
from typing import TYPE_CHECKING, Annotated, Literal, Optional

import typer

from mm.pipe import read_paths_from_stdin
from mm.utils import Format

if TYPE_CHECKING:
    from mm.config import Mode

VIDEO_EXTS = frozenset(
    (
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".wmv",
        ".flv",
        ".webm",
        ".m4v",
        ".mpg",
        ".mpeg",
        ".3gp",
        ".ogv",
    )
)
IMAGE_EXTS = frozenset(
    (
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".tiff",
        ".svg",
    )
)
AUDIO_EXTS = frozenset(
    (
        ".mp3",
        ".wav",
        ".flac",
        ".aac",
        ".ogg",
        ".m4a",
        ".wma",
        ".opus",
    )
)
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
        Optional[Path],
        typer.Option("--output-dir", "-o", help="Output directory for mosaics/audio"),
    ] = None,
    max_pages: Annotated[
        Optional[int], typer.Option("--max-pages", help="Max PDF pages to render at L2")
    ] = None,
    mosaic_tile: Annotated[
        str, typer.Option("--mosaic-tile", help="Mosaic tile grid COLSxROWS")
    ] = "6x8",
    mosaic_image_width: Annotated[
        int, typer.Option("--mosaic-image-width", help="Thumbnail width in pixels for mosaics")
    ] = 160,
    video_mosaic_count: Annotated[
        int, typer.Option("--video-mosaic-count", help="Number of mosaics for video (1-8)")
    ] = 1,
    video_mosaic_strategy: Annotated[
        str,
        typer.Option(
            "--video-mosaic-strategy", help="Video frame selection: uniform, keyframe, scene"
        ),
    ] = "uniform",
    audio_speed: Annotated[
        float, typer.Option("--audio-speed", help="Audio playback speed multiplier")
    ] = 2.0,
    audio_sample_rate: Annotated[
        int, typer.Option("--audio-sample-rate", help="Audio sample rate Hz")
    ] = 16000,
    mode: Annotated[
        Optional[str],
        typer.Option("--mode", "-m", help="Extraction mode: 'fast' or 'accurate' (L2 only)"),
    ] = None,
    no_cache: Annotated[
        bool, typer.Option("--no-cache", help="Bypass L2 cache and force a fresh LLM run")
    ] = False,
    format: Annotated[
        Optional[Format],
        typer.Option("--format", help="Output format: json, tsv, csv, dataset-jsonl, dataset-hf"),
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
      mm cat paper.pdf                    # extract text (L1)
      mm cat paper.pdf -n 20              # first 20 lines
      mm cat video.mp4                    # metadata (<100ms)
      mm cat video.mp4 -l 2               # mosaic + LLM description
      mm cat photo.png -l 2               # LLM caption (~20 words)
      mm cat photo.png -l 2 --detail      # ~80-word description
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

    from mm.display import resolve_format

    fmt = resolve_format(format.value if format else None)

    opts = _CatOpts(
        level=level,
        n=n,
        detail=detail,
        output_dir=output_dir,
        max_pages=max_pages,
        mosaic_tile=mosaic_tile,
        mosaic_image_width=mosaic_image_width,
        video_mosaic_count=video_mosaic_count,
        video_mosaic_strategy=video_mosaic_strategy,
        audio_speed=audio_speed,
        audio_sample_rate=audio_sample_rate,
        mode=mode,
        no_cache=no_cache,
        format=fmt,
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
                entry: dict = {"path": str(p), "level": level, "content": content}
            else:
                entry = {
                    "path": str(p),
                    "level": level,
                    "content": content,
                    "name": p.name,
                    "type": _file_kind(p),
                    "size": p.stat().st_size,
                }
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

    if fmt in ("json", "dataset-jsonl", "dataset-hf"):
        from mm.display import emit_rows

        emit_rows(fmt, results, output_dir=str(output_dir) if output_dir else "mm_dataset")


# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------


class _CatOpts:
    """Bag of resolved options threaded through extraction."""

    __slots__ = (
        "level",
        "n",
        "detail",
        "output_dir",
        "max_pages",
        "mosaic_tile",
        "mosaic_image_width",
        "video_mosaic_count",
        "video_mosaic_strategy",
        "audio_speed",
        "audio_sample_rate",
        "mode",
        "no_cache",
        "format",
    )

    level: int
    n: int | None
    detail: bool
    output_dir: Path | None
    max_pages: int | None
    mosaic_tile: str
    mosaic_image_width: int
    video_mosaic_count: int
    video_mosaic_strategy: str
    audio_speed: float
    audio_sample_rate: int
    mode: Mode | None
    no_cache: bool
    format: str

    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

FileKind = Literal["text", "image", "video", "audio", "document"]


def _file_kind(path: Path) -> FileKind:
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
    """Dispatch extraction based on (file_kind, level).

    Uses the path.read_text(errors="replace") fallback in _l1
    """
    kind = _file_kind(path)
    if opts.level >= 2:
        return _run_l2(path, kind, opts)

    return _run_l1(path, kind, no_cache=opts.no_cache)


def _run_l2(path: Path, kind: str, opts: _CatOpts) -> str:
    """Run L2 with cache lookup/store unless --no-cache."""
    from mm.profile import get_profile
    from mm.store.db import MmDatabase
    from mm.store.util import get_content_hash

    db = MmDatabase()
    profile = get_profile()
    content_hash = get_content_hash(path)
    # Include video mosaic parameters in cache key for different mosaic configs.
    extra_parts: list[str] = []
    if kind == "video":
        extra_parts.append(opts.mosaic_tile)
        extra_parts.append(str(opts.mosaic_image_width))
        extra_parts.append(str(opts.video_mosaic_count))
        extra_parts.append(opts.video_mosaic_strategy)
    extra = "|".join(extra_parts)

    if content_hash:
        from mm.store.util import get_l2_id

        l2_id = get_l2_id(
            content_hash,
            profile.name,
            profile.model,
            opts.mode,
            opts.detail,
            extra=extra,
        )

        if not opts.no_cache:
            value = db.get_l2(l2_id)
            if value is not None:
                return value
        else:
            db.evict_l2(l2_id)

    _run_l1(path, kind)  # Ensure L1 exist

    # Run the actual L2 extraction
    if opts.mode is not None:
        result = _l2_modal(path, kind, opts)
    else:
        result = _l2(path, kind, opts)

    if content_hash and result and not result.startswith("["):
        uri = str(path.resolve())
        l2_id = db.put_l2(
            uri=uri,
            content_hash=content_hash,
            profile=profile.name,
            model=profile.model,
            content=result,
            mode=opts.mode,
            detail=opts.detail,
            extra=extra,
        )
        try:
            from mm.store.embed import embed_file_chunks

            embed_file_chunks(l2_id)
        except Exception:
            pass
    return result


# ---------------------------------------------------------------------------
# L1 — structured extraction, <100ms per file
# ---------------------------------------------------------------------------


def _run_l1(path: Path, kind: str, *, no_cache=False) -> str:
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
    from mm.llm import LlmBackend

    content = _run_l1(path, kind)
    return LlmBackend().describe(path, content, detail=opts.detail)


def _l2_image(path: Path, opts: _CatOpts) -> str:
    from mm.llm import LlmBackend

    return LlmBackend().caption(path, detail=opts.detail)


def _l2_video(path: Path, opts: _CatOpts) -> str:
    """Generate keyframe mosaic then send to LLM for description."""
    try:
        from mm.ffmpeg import (
            extract_keyframe_mosaics,
            extract_scene_mosaics,
            extract_uniform_mosaics,
            ffmpeg_available,
        )
        from mm.llm import LlmBackend

        if not ffmpeg_available():
            raise RuntimeError(f"ffmpeg not found — cannot generate mosaic for {path.name}")

        cols, rows = _parse_tile(opts.mosaic_tile)
        count = max(1, min(opts.video_mosaic_count, 8))

        if opts.video_mosaic_strategy == "uniform":
            result = extract_uniform_mosaics(
                path,
                out_dir=opts.output_dir,
                tile_cols=cols,
                tile_rows=rows,
                thumb_width=opts.mosaic_image_width,
                num_mosaics=count,
            )
        elif opts.video_mosaic_strategy == "scene":
            result = extract_scene_mosaics(
                path,
                out_dir=opts.output_dir,
                tile_cols=cols,
                tile_rows=rows,
                thumb_width=opts.mosaic_image_width,
                max_mosaics=count,
            )
        else:
            result = extract_keyframe_mosaics(
                path,
                out_dir=opts.output_dir,
                tile_cols=cols,
                tile_rows=rows,
                thumb_width=opts.mosaic_image_width,
                max_mosaics=count,
            )

        if not result.mosaic_paths:
            raise RuntimeError(f"No keyframes extracted from {path.name}")

        info = LlmBackend().describe_video(
            result.mosaic_paths,
            video_name=path.name,
            duration_s=result.duration_s,
        )
        return info.get("summary", "") or str(info)
    except Exception as e:
        return f"[Video L2 failed: {e}]"


def _l2_audio(path: Path, opts: _CatOpts) -> str:
    """Describe audio from metadata via LLM."""
    from mm.llm import LlmBackend

    metadata = _run_l1(path, "audio")
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
        # Documents use basic extraction at L1; at L2, summarize via LLM
        from mm.llm import LlmBackend

        content = _run_l1(path, kind)
        return LlmBackend().describe(path, content, detail=(mode == "accurate"))

    # text/code: summarize
    from mm.llm import LlmBackend

    content = _run_l1(path, kind)
    return LlmBackend().describe(path, content, detail=(mode == "accurate"))


def _l2_image_modal(path: Path, mode: Mode) -> str:
    """Image extraction with mode-specific LLM prompts.

    fast:     10-word description + 5 tags
    accurate: 200-word description + 10 tags + 10 objects
    """
    import time

    from mm.llm import LlmBackend

    t0 = time.monotonic()
    llm = LlmBackend()
    content = llm.caption_modal(path, mode=mode)
    elapsed = (time.monotonic() - t0) * 1000
    u = llm.last_usage

    return f"{content}\n\n[mode={mode}, {elapsed:.0f}ms, {u.prompt_tokens}→{u.completion_tokens} tokens]"


def _l2_video_modal(path: Path, opts: _CatOpts, mode: Mode) -> str:
    """Video extraction with mode-aware mosaic + whisper + LLM pipeline.

    fast (<5min):  16 uniform frames, 1 mosaic, whisper tiny @ 2x
    fast (≥5min):  scene detection → 16 shots, 1 mosaic, whisper tiny @ 2x
    accurate:      scene detection → 128 shots, 8 mosaics, whisper medium @ 1x
    """
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
    from mm.llm import LlmBackend

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
    from concurrent.futures import Future, ThreadPoolExecutor

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

    def _extract_visual_and_vlm() -> tuple[list[Path], str]:
        """Extract frames, assemble mosaics, run VLM — all sequential.

        Returns (mosaic_paths, vlm_analysis).
        """
        t0 = time.monotonic()
        if use_scenes:
            from mm.scenes import (
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

        # VLM call on mosaic only — no transcript in prompt
        t_vlm = time.monotonic()
        llm = LlmBackend()
        analysis = llm.analyze_video_visual(
            mosaics,
            video_name=path.name,
            duration_s=duration,
            mode=mode,
        )
        timing["vlm_call_ms"] = (time.monotonic() - t_vlm) * 1000
        timing["vlm_prompt_tokens"] = llm.last_usage.prompt_tokens
        timing["vlm_completion_tokens"] = llm.last_usage.completion_tokens
        return mosaics, analysis

    def _extract_audio_transcript() -> str:
        """Extract audio and transcribe with whisper."""
        from mm.whisper import whisper_available

        if not whisper_available():
            return ""

        from mm.config import get_mode_config

        mode_cfg = get_mode_config(mode)

        t_audio = time.monotonic()
        audio_result = extract_audio(path, speed=mode_cfg.audio_speed)
        timing["audio_extraction_ms"] = (time.monotonic() - t_audio) * 1000

        from mm.whisper import transcribe

        whisper_result = transcribe(
            audio_result.path,
            model_size=mode_cfg.whisper_model,
            beam_size=mode_cfg.beam_size or 1,
            audio_speed=mode_cfg.audio_speed,
        )
        timing["audio_transcription_ms"] = whisper_result.elapsed_ms

        try:
            audio_result.path.unlink(missing_ok=True)
        except Exception:
            pass
        return whisper_result.text

    # Run (visual → VLM) ∥ (audio → whisper) in parallel
    # The VLM sees only the mosaic; transcript is concatenated at the end.
    with ThreadPoolExecutor(max_workers=2) as pool:
        visual_future: Future[tuple[list[Path], str]] = pool.submit(_extract_visual_and_vlm)
        audio_future: Future[str] = pool.submit(_extract_audio_transcript)
        mosaic_paths, analysis = visual_future.result()
        transcript = audio_future.result()

    if not mosaic_paths:
        return f"[No frames extracted from {path.name}]"

    timing["total_ms"] = (time.monotonic() - t_total) * 1000

    # Cleanup temp mosaics (unless --output-dir was specified)
    if opts.output_dir is None:
        for mp in mosaic_paths:
            try:
                parent = mp.parent
                mp.unlink(missing_ok=True)
                if parent.name.startswith("mm_"):
                    shutil.rmtree(parent, ignore_errors=True)
            except Exception:
                pass

    # Concatenate: VLM visual analysis + whisper transcript
    parts: list[str] = [analysis]
    if transcript:
        word_count = len(transcript.split())
        parts.append(f"\n## Transcript ({word_count} words)\n{transcript}")

    # Separate timing and token metrics
    time_keys = {k: v for k, v in timing.items() if k.endswith("_ms") and k != "total_ms"}
    token_keys = {k: v for k, v in timing.items() if "tokens" in k}
    timing_str = " | ".join(f"{k}: {v:.0f}ms" for k, v in time_keys.items())
    token_str = (
        f" | {int(token_keys.get('vlm_prompt_tokens', 0))}→{int(token_keys.get('vlm_completion_tokens', 0))} tokens"
        if token_keys
        else ""
    )
    parts.append(f"\n[mode={mode}, total={timing['total_ms']:.0f}ms{token_str} | {timing_str}]")
    return "\n".join(parts)


def _l2_audio_modal(path: Path, opts: _CatOpts, mode: Mode) -> str:
    """Audio extraction with transcription.

    fast:     2x speed + tiny model + greedy decoding
    accurate: 1x speed + medium model + beam search
    """
    import time

    from mm.ffmpeg import extract_audio, ffmpeg_available
    from mm.whisper import transcribe, whisper_available

    if not ffmpeg_available():
        return f"[ffmpeg not found — cannot process {path.name}]"

    if not whisper_available():
        return "[whisper not installed — pip install mm[extract] or pip install mm[extract,mlx] for MLX support on Apple Silicon]"

    from mm.config import get_mode_config

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
    timing["audio_transcription_ms"] = whisper_result.elapsed_ms
    transcript = whisper_result.text

    # Cleanup temp audio
    try:
        audio_result.path.unlink(missing_ok=True)
    except Exception:
        pass

    if not transcript or transcript.startswith("["):
        return transcript or "[No speech detected]"

    # 3. Optionally summarize via LLM
    from mm.llm import LlmBackend

    t_llm = time.monotonic()
    llm = LlmBackend()
    summary = llm.summarize_transcript(transcript, mode=mode, filename=path.name)
    timing["llm_call_ms"] = (time.monotonic() - t_llm) * 1000
    timing["total_ms"] = (time.monotonic() - t_total) * 1000
    u = llm.last_usage

    # 4. Format output
    word_count = len(transcript.split())
    timing_str = " | ".join(f"{k}: {v:.0f}ms" for k, v in timing.items() if k != "total_ms")
    return (
        f"{summary}\n\n"
        f"[Transcript: {word_count} words]\n"
        f"[mode={mode}, total={timing['total_ms']:.0f}ms, {u.prompt_tokens}→{u.completion_tokens} tokens | {timing_str}]"
    )


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


def _display_rich(
    path: Path,
    content: str,
    level: int,
    n: int | None,
) -> None:
    from rich import box
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.text import Text

    from mm.display import format_size, output_console

    ext = path.suffix.lstrip(".")
    size_str = format_size(path.stat().st_size)
    level_label = {0: "raw", 1: "extracted", 2: "semantic"}.get(level, f"L{level}")

    subtitle = Text()
    subtitle.append(f"{size_str}", style="bright_blue")
    subtitle.append(f"  L{level} {level_label}", style="dim")

    if level >= 2:
        from mm.profile import get_active_profile_name

        profile_name = get_active_profile_name()
        subtitle.append(f"  {profile_name}", style="yellow")

    if n is not None:
        total_lines = len(path.read_text(errors="replace").splitlines()) if level == 0 else None
        if n >= 0:
            subtitle.append(f"  lines 1-{n}", style="dim")
        else:
            subtitle.append(f"  last {abs(n)} lines", style="dim")
        if total_lines:
            subtitle.append(f" of {total_lines}", style="dim")

    lang_map = {
        "py": "python",
        "rs": "rust",
        "js": "javascript",
        "ts": "typescript",
        "tsx": "typescript",
        "jsx": "javascript",
        "go": "go",
        "java": "java",
        "c": "c",
        "cpp": "cpp",
        "h": "c",
        "hpp": "cpp",
        "rb": "ruby",
        "sh": "bash",
        "bash": "bash",
        "zsh": "bash",
        "yaml": "yaml",
        "yml": "yaml",
        "toml": "toml",
        "json": "json",
        "md": "markdown",
        "html": "html",
        "css": "css",
        "sql": "sql",
        "xml": "xml",
    }

    title = f"[bold]{path}[/bold]"
    kind = _file_kind(path)
    is_binary = kind in ("image", "document", "video", "audio") or "\x00" in content[:512]
    if is_binary:
        safe_content: Text | str = Text(content.replace("\x1b", "\ufffd"))
    else:
        safe_content = Text(content) if level >= 2 else content

    if ext in lang_map and level == 0:
        syntax = Syntax(content, lang_map[ext], theme="monokai", line_numbers=True)
        output_console.print(
            Panel(
                syntax,
                title=title,
                title_align="left",
                subtitle=subtitle,
                expand=False,
                border_style="green",
                box=box.ROUNDED,
            )
        )
    elif kind == "image":
        min_width = len(subtitle.plain) + 10
        output_console.print(
            Panel(
                safe_content,
                title=title,
                title_align="left",
                subtitle=subtitle,
                expand=True,
                width=min_width,
                border_style="green",
                box=box.ROUNDED,
            )
        )
    elif kind == "document":
        line_count = len(content.splitlines())
        if line_count > 0:
            subtitle.append(f"  {line_count} lines", style="dim")
        output_console.print(
            Panel(
                safe_content,
                title=title,
                title_align="left",
                subtitle=subtitle,
                expand=False,
                border_style="cyan",
                box=box.ROUNDED,
            )
        )
    elif kind in ("video", "audio"):
        content_width = max((len(line) for line in content.splitlines()), default=0)
        min_width = max(content_width + 4, len(subtitle.plain) + 10)
        output_console.print(
            Panel(
                safe_content,
                title=title,
                title_align="left",
                subtitle=subtitle,
                expand=False,
                width=min_width,
                border_style="magenta",
                box=box.ROUNDED,
            )
        )
    else:
        output_console.print(
            Panel(
                safe_content,
                title=title,
                title_align="left",
                subtitle=subtitle,
                expand=False,
                border_style="blue",
                box=box.ROUNDED,
            )
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
