"""vlmctx cat -- semantic content display."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from vlmctx.pipe import is_piped_output, read_paths_from_stdin


def cat_cmd(
    files: Annotated[Optional[list[Path]], typer.Argument(help="Files to display")] = None,
    level: Annotated[int, typer.Option("--level", "-l", help="Processing level (0=raw, 1=extracted, 2=semantic)")] = 1,
    json_output: Annotated[bool, typer.Option("--json", help="Force JSON output")] = False,
) -> None:
    """Display file content semantically (like bat/cat).

    Level 0: raw content with syntax highlighting.
    Level 1: extracted content (text from PDF, image metadata).
    Level 2: LLM-generated description (requires --llm-base-url).
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

        if json_output:
            results.append({"path": str(p), "level": level, "content": content})
        elif use_rich:
            _display_rich(p, content, level)
        else:
            print(content)

    if json_output:
        import json

        print(json.dumps(results, indent=2, default=str))


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

    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".svg"):
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

    if ext in (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg", ".3gp", ".ogv"):
        try:
            from vlmctx.video import extract_video_metadata

            meta = extract_video_metadata(path)
            parts: list[str] = []
            if meta.width and meta.height:
                parts.append(f"Resolution: {meta.width}x{meta.height}")
            if meta.duration_s is not None:
                mins, secs = divmod(meta.duration_s, 60)
                parts.append(f"Duration:   {int(mins)}m {secs:.1f}s ({meta.duration_s:.2f}s)")
            if meta.fps:
                parts.append(f"FPS:        {meta.fps}")
            if meta.video_codec:
                parts.append(f"Video:      {meta.video_codec}")
            if meta.audio_codec:
                parts.append(f"Audio:      {meta.audio_codec}")
            elif not meta.has_audio:
                parts.append("Audio:      none")
            if meta.bitrate:
                from vlmctx.display import format_size
                parts.append(f"Bitrate:    {format_size(meta.bitrate)}/s")
            if meta.pixel_format:
                parts.append(f"Pixel fmt:  {meta.pixel_format}")
            if meta.rotation:
                parts.append(f"Rotation:   {meta.rotation}°")
            return "\n".join(parts) if parts else f"[Video: {path.name}]"
        except Exception as e:
            return f"[Video extraction failed: {e}]"

    return path.read_text(errors="replace")


def _extract_l2_content(path: Path) -> str:
    """Extract L2 content using LLM backend."""
    from vlmctx.llm import LlmBackend

    llm = LlmBackend()
    if not llm.is_configured:
        return (
            "[L2 requires LLM — set VLMCTX_LLM_BASE_URL]\n\n"
            + _extract_l1_content(path)
        )

    ext = path.suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"):
        return llm.caption(path)
    else:
        content = _extract_l1_content(path)
        return llm.describe(path, content)


def _display_rich(path: Path, content: str, level: int) -> None:
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
        output_console.print(Panel(syntax, title=title, subtitle=subtitle, expand=False, border_style="green"))
    elif path.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"):
        output_console.print(Panel(safe_content, title=title, subtitle=subtitle, expand=False, border_style="green"))
    elif path.suffix.lower() == ".pdf":
        lines = content.splitlines()
        line_count = len(lines)
        page_info = f"  {line_count} lines" if line_count > 0 else ""
        subtitle.append(page_info, style="dim")
        output_console.print(Panel(safe_content, title=title, subtitle=subtitle, expand=False, border_style="cyan"))
    else:
        output_console.print(Panel(safe_content, title=title, subtitle=subtitle, expand=False, border_style="blue"))
