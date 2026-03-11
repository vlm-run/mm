"""vlmctx cat -- unified content extraction (text, visual mosaics, audio)."""

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
    visual: Annotated[
        bool, typer.Option("--visual", help="Extract visual mosaics (PDF pages / video keyframes)")
    ] = False,
    audio: Annotated[
        bool, typer.Option("--audio", help="Extract audio track from video/audio files")
    ] = False,
    out: Annotated[
        Optional[Path], typer.Option("--out", "-o", help="Output directory for mosaics/audio")
    ] = None,
    tile: Annotated[str, typer.Option("--tile", "-t", help="Mosaic tile grid COLSxROWS")] = "6x8",
    width: Annotated[int, typer.Option("--width", "-w", help="Thumbnail width in pixels")] = 160,
    num_mosaics: Annotated[
        int, typer.Option("--num-mosaics", help="Number of mosaics for video (1-8)")
    ] = 1,
    strategy: Annotated[
        str, typer.Option("--strategy", help="Video frame selection: uniform, keyframe, scene")
    ] = "uniform",
    speed: Annotated[float, typer.Option("--speed", help="Audio playback speed multiplier")] = 2.0,
    sample_rate: Annotated[int, typer.Option("--sample-rate", help="Audio sample rate Hz")] = 16000,
    max_pages: Annotated[
        Optional[int], typer.Option("--max-pages", help="Max PDF pages to render for --visual")
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Force JSON output")] = False,
) -> None:
    """Display file content semantically (like bat/cat).

    Supports head/tail via -n, visual mosaics via --visual, audio extraction via --audio.

    \b
    Examples:
      vlmctx cat paper.pdf                   # extract text (L1)
      vlmctx cat paper.pdf -n 20             # first 20 lines (head)
      vlmctx cat paper.pdf -n -20            # last 20 lines (tail)
      vlmctx cat paper.pdf --visual          # page mosaic grid
      vlmctx cat video.mp4                   # metadata + keyframes
      vlmctx cat video.mp4 --audio --speed 2 # extract audio track
      vlmctx cat photo.png --level 2         # LLM caption
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

    if visual:
        _handle_visual(paths, out, tile, width, num_mosaics, strategy, max_pages, json_output)
        return

    if audio:
        _handle_audio(paths, out, speed, sample_rate, json_output)
        return

    _handle_content(paths, level, n, json_output)


def _handle_content(
    paths: list[str], level: int, n: int | None, json_output: bool
) -> None:
    """Default mode: text/metadata extraction with optional head/tail."""
    use_rich = not is_piped_output() and not json_output
    results: list[dict] = []

    for file_path in paths:
        p = Path(file_path)
        if not p.exists():
            typer.echo(f"Error: {file_path} not found.", err=True)
            continue

        if level == 0:
            content = p.read_text(errors="replace")
        elif level == 1:
            content = _extract_l1_content(p)
        else:
            content = _extract_l2_content(p)

        if n is not None:
            all_lines = content.splitlines()
            if n >= 0:
                lines = all_lines[:n]
            else:
                lines = all_lines[n:]
            content = "\n".join(lines)

        if json_output:
            results.append({"path": str(p), "level": level, "content": content})
        elif use_rich:
            _display_rich(p, content, level, n)
        else:
            print(content)

    if json_output:
        import json

        print(json.dumps(results, indent=2, default=str))


def _handle_visual(
    paths: list[str],
    out: Path | None,
    tile: str,
    width: int,
    num_mosaics: int,
    strategy: str,
    max_pages: int | None,
    json_output: bool,
) -> None:
    """Extract visual mosaics from videos and PDFs."""
    piped = is_piped_output()
    all_results: list[dict] = []

    for file_path in paths:
        p = Path(file_path)
        if not p.exists():
            typer.echo(f"Error: {file_path} not found.", err=True)
            continue

        ext = p.suffix.lower()

        if ext == ".pdf" or (p.is_dir()):
            _visual_pdf(p, out, tile, width, max_pages, json_output, piped, all_results)
        elif ext in VIDEO_EXTS:
            _visual_video(
                p, out, tile, width, num_mosaics, strategy, json_output, piped, all_results
            )
        else:
            typer.echo(f"Warning: --visual not supported for {ext}", err=True)

    if json_output:
        import json

        print(json.dumps(all_results, indent=2))


def _visual_pdf(
    path: Path,
    out: Path | None,
    tile: str,
    width: int,
    max_pages: int | None,
    json_output: bool,
    piped: bool,
    results: list[dict],
) -> None:
    from vlmctx.pdf import extract_pdf_mosaics, pypdfium2_available

    if not pypdfium2_available():
        typer.echo("Error: pypdfium2 not installed: pip install pypdfium2", err=True)
        return

    cols, rows = _parse_tile(tile)

    pdfs: list[Path] = []
    if path.is_file():
        pdfs = [path]
    elif path.is_dir():
        pdfs = sorted(path.glob("**/*.pdf"))

    for pdf in pdfs:
        r = extract_pdf_mosaics(
            pdf, out_dir=out, tile_cols=cols, tile_rows=rows,
            thumb_width=width, max_pages=max_pages,
        )
        entry = {
            "pdf": str(pdf), "pages": r.page_count,
            "rendered": r.rendered_pages,
            "mosaics": [str(p) for p in r.mosaic_paths],
            "elapsed_ms": round(r.elapsed_ms, 1),
        }
        results.append(entry)

        if not json_output:
            if piped:
                for mp in r.mosaic_paths:
                    print(mp)
            else:
                from rich.table import Table as RichTable

                from vlmctx.display import format_size, output_console

                tbl = RichTable(
                    title=f"[bold]{pdf.name}[/bold]",
                    show_header=True, header_style="bold",
                    padding=(0, 1), border_style="dim", expand=False,
                )
                tbl.add_column("pages", justify="right")
                tbl.add_column("rendered", justify="right")
                tbl.add_column("time", justify="right", style="green")
                tbl.add_column("output", style="cyan")
                mosaic_strs = "\n".join(
                    f"{mp}  ({format_size(mp.stat().st_size)})" for mp in r.mosaic_paths
                )
                tbl.add_row(
                    str(r.page_count), str(r.rendered_pages),
                    f"{r.elapsed_ms:.0f}ms", mosaic_strs,
                )
                output_console.print(tbl)


def _visual_video(
    path: Path,
    out: Path | None,
    tile: str,
    width: int,
    num_mosaics: int,
    strategy: str,
    json_output: bool,
    piped: bool,
    results: list[dict],
) -> None:
    from vlmctx.display import console
    from vlmctx.ffmpeg import (
        extract_keyframe_mosaics,
        extract_scene_mosaics,
        extract_uniform_mosaics,
        ffmpeg_available,
    )

    if not ffmpeg_available():
        console.print("[red]ffmpeg not found on PATH[/red]", style="bold")
        return

    cols, rows = _parse_tile(tile)
    num_mosaics = max(1, min(num_mosaics, 8))

    if strategy == "uniform":
        result = extract_uniform_mosaics(
            path, out_dir=out, tile_cols=cols, tile_rows=rows,
            thumb_width=width, num_mosaics=num_mosaics,
        )
    elif strategy == "scene":
        result = extract_scene_mosaics(
            path, out_dir=out, tile_cols=cols, tile_rows=rows,
            thumb_width=width, max_mosaics=num_mosaics,
        )
    else:
        result = extract_keyframe_mosaics(
            path, out_dir=out, tile_cols=cols, tile_rows=rows,
            thumb_width=width, max_mosaics=num_mosaics,
        )

    entry = {
        "video": str(path), "frames": result.frame_count,
        "mosaics": [str(p) for p in result.mosaic_paths],
        "tile": f"{cols}x{rows}", "strategy": result.strategy,
    }
    if result.elapsed_ms > 0:
        entry["elapsed_ms"] = round(result.elapsed_ms, 1)
    if result.duration_s > 0:
        entry["duration_s"] = round(result.duration_s, 2)
    results.append(entry)

    if not json_output:
        if piped:
            for p in result.mosaic_paths:
                print(str(p))
        else:
            from rich.panel import Panel
            from rich.text import Text

            from vlmctx.display import format_size, output_console

            body = Text()
            body.append(f"  {result.frame_count}", style="bold bright_blue")
            body.append(" frames → ", style="dim")
            body.append(f"{len(result.mosaic_paths)}", style="bold bright_green")
            body.append(f" mosaic(s)  [{result.strategy}]\n", style="dim")
            if result.elapsed_ms > 0:
                body.append(f"  {result.elapsed_ms:.0f}ms", style="bright_yellow")
                if result.duration_s > 0:
                    speedup = result.duration_s * 1000 / result.elapsed_ms
                    body.append(f"  ({speedup:.0f}x realtime)\n", style="dim")
                else:
                    body.append("\n")
            for mp in result.mosaic_paths:
                body.append(f"  {mp}", style="white")
                body.append(f"  ({format_size(mp.stat().st_size)})\n", style="dim")
            output_console.print(
                Panel(body, title=f"[bold]{path.name}[/bold]", expand=False)
            )


def _handle_audio(
    paths: list[str], out: Path | None, speed: float, sample_rate: int, json_output: bool
) -> None:
    """Extract audio tracks from video/audio files."""
    from vlmctx.display import console
    from vlmctx.ffmpeg import extract_audio, ffmpeg_available

    if not ffmpeg_available():
        console.print("[red]ffmpeg not found on PATH[/red]", style="bold")
        raise typer.Exit(1)

    piped = is_piped_output()
    all_results = []

    for file_path in paths:
        p = Path(file_path)
        if not p.exists():
            typer.echo(f"Error: {file_path} not found.", err=True)
            continue

        out_path = None
        if out:
            out.mkdir(parents=True, exist_ok=True)
            out_path = out / f"{p.stem}_{speed}x.wav"

        result = extract_audio(
            p, out_path=out_path, speed=speed, sample_rate=sample_rate, mono=True, fmt="wav",
        )
        all_results.append({
            "source": str(p),
            "audio": str(result.path),
            "speed": result.speed,
            "sample_rate": result.sample_rate,
            "channels": result.channels,
            "size_kb": result.path.stat().st_size // 1024 if result.path.exists() else 0,
        })

    if not all_results:
        return

    if json_output:
        import json

        print(json.dumps(all_results, indent=2))
        return

    if piped:
        for entry in all_results:
            print(entry["audio"])
    else:
        from rich.table import Table as RichTable

        from vlmctx.display import format_size, output_console

        tbl = RichTable(
            show_header=True, header_style="bold",
            padding=(0, 1), border_style="dim", expand=False,
        )
        tbl.add_column("source", style="bold")
        tbl.add_column("output", style="cyan")
        tbl.add_column("size", justify="right", style="bright_blue")
        tbl.add_column("speed", justify="right")
        tbl.add_column("rate", justify="right")

        for entry in all_results:
            tbl.add_row(
                Path(entry["source"]).name,
                str(entry["audio"]),
                format_size(entry["size_kb"] * 1024),
                f"{entry['speed']}x",
                f"{entry['sample_rate']}Hz",
            )
        output_console.print(tbl)


def _extract_l1_content(path: Path) -> str:
    """Extract L1 content based on file type."""
    ext = path.suffix.lower()

    if ext == ".pdf":
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

    if ext in IMAGE_EXTS:
        try:
            from vlmctx._vlmctx import Scanner

            parent = str(path.parent)
            scanner = Scanner(parent)
            scanner.scan()
            result = scanner.extract_l1(path.name)
            parts: list[str] = []
            if result.dimensions:
                parts.append(f"Dimensions: {result.dimensions}")
            if result.magic_mime:
                parts.append(f"MIME:       {result.magic_mime}")
            if result.content_hash:
                parts.append(f"Hash:       {result.content_hash}")
            if result.exif_camera:
                parts.append(f"Camera:     {result.exif_camera}")
            if result.exif_date:
                parts.append(f"Date:       {result.exif_date}")
            if result.exif_gps:
                parts.append(f"GPS:        {result.exif_gps}")
            if result.exif_orientation:
                parts.append(f"Orientation: {result.exif_orientation}")
            return "\n".join(parts) if parts else f"[Image: {path.name}]"
        except Exception as e:
            return f"[Image extraction failed: {e}]"

    if ext in VIDEO_EXTS:
        try:
            from vlmctx._vlmctx import Scanner

            parent = str(path.parent)
            scanner = Scanner(parent)
            scanner.scan()
            result = scanner.extract_l1(path.name)

            parts: list[str] = []
            if result.dimensions:
                parts.append(f"Resolution: {result.dimensions}")
            if result.duration_s is not None:
                mins, secs = divmod(result.duration_s, 60)
                parts.append(f"Duration:   {int(mins)}m {secs:.1f}s ({result.duration_s:.2f}s)")
            if result.fps:
                parts.append(f"FPS:        {result.fps}")
            if result.video_codec:
                parts.append(f"Video:      {result.video_codec}")
            if result.audio_codec:
                parts.append(f"Audio:      {result.audio_codec}")
            elif result.has_audio is False:
                parts.append("Audio:      none")
            if result.content_hash:
                parts.append(f"Hash:       {result.content_hash}")

            try:
                from vlmctx.ffmpeg import extract_uniform_mosaics, ffmpeg_available

                if ffmpeg_available():
                    mosaic = extract_uniform_mosaics(path, num_mosaics=1)
                    if mosaic.mosaic_paths:
                        parts.append(f"Frames:     {mosaic.frame_count} ({mosaic.strategy})")
                        parts.append(f"Sampled:    {mosaic.elapsed_ms:.0f}ms")
                        for mp in mosaic.mosaic_paths:
                            parts.append(f"Mosaic:     {mp}")
            except Exception:
                pass

            return "\n".join(parts) if parts else f"[Video: {path.name}]"
        except Exception as e:
            return f"[Video extraction failed: {e}]"

    return path.read_text(errors="replace")


def _extract_l2_content(path: Path) -> str:
    """Extract L2 content using LLM backend."""
    from vlmctx.llm import LlmBackend

    llm = LlmBackend()
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return llm.caption(path)
    else:
        content = _extract_l1_content(path)
        return llm.describe(path, content)


def _display_rich(path: Path, content: str, level: int, n: int | None) -> None:
    """Display content with Rich formatting."""
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

    if ext in lang_map and level == 0:
        syntax = Syntax(content, lang_map[ext], theme="monokai", line_numbers=True)
        output_console.print(
            Panel(syntax, title=title, subtitle=subtitle, expand=False, border_style="green")
        )
    elif path.suffix.lower() in IMAGE_EXTS:
        output_console.print(
            Panel(safe_content, title=title, subtitle=subtitle, expand=False, border_style="green")
        )
    elif path.suffix.lower() == ".pdf":
        lines = content.splitlines()
        line_count = len(lines)
        if line_count > 0:
            subtitle.append(f"  {line_count} lines", style="dim")
        output_console.print(
            Panel(safe_content, title=title, subtitle=subtitle, expand=False, border_style="cyan")
        )
    else:
        output_console.print(
            Panel(safe_content, title=title, subtitle=subtitle, expand=False, border_style="blue")
        )


def _parse_tile(tile: str) -> tuple[int, int]:
    parts = tile.lower().split("x")
    if len(parts) == 2:
        return int(parts[0]), int(parts[1])
    n = int(parts[0])
    return n, n
