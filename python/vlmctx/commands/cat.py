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
    json_output: Annotated[bool, typer.Option("--json", help="Force JSON output")] = False,
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

    opts = _CatOpts(
        level=level, n=n, detail=detail, output_dir=output_dir,
        max_pages=max_pages, mosaic_tile=mosaic_tile, image_width=image_width,
        mosaic_count=mosaic_count, mosaic_strategy=mosaic_strategy,
        audio_speed=audio_speed, audio_sample_rate=audio_sample_rate,
        json_output=json_output,
    )

    use_rich = not is_piped_output() and not json_output
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

        if json_output:
            results.append({"path": str(p), "level": level, "content": content})
        elif use_rich:
            _display_rich(p, content, level, n)
        else:
            print(content)

    if json_output:
        import json

        print(json.dumps(results, indent=2, default=str))


# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------

class _CatOpts:
    """Bag of resolved options threaded through extraction."""

    __slots__ = (
        "level", "n", "detail", "output_dir", "max_pages",
        "mosaic_tile", "image_width", "mosaic_count", "mosaic_strategy",
        "audio_speed", "audio_sample_rate", "json_output",
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
    if ext == ".pdf":
        return "pdf"
    return "text"


def _extract(path: Path, opts: _CatOpts) -> str:
    """Dispatch extraction based on (file_kind, level)."""
    if opts.level == 0:
        return path.read_text(errors="replace")

    kind = _file_kind(path)

    if opts.level >= 2:
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
    if kind == "pdf":
        return _l1_pdf(path)
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


def _l1_pdf(path: Path) -> str:
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

    # pdf / text: extract L1 text then summarise
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
    elif kind == "pdf":
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
