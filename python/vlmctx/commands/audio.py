"""vlmctx audio -- extract audio from video/audio files."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from vlmctx.pipe import is_piped_output, read_paths_from_stdin


def audio_cmd(
    files: Annotated[Optional[list[Path]], typer.Argument(help="Video/audio files")] = None,
    out: Annotated[Optional[Path], typer.Option("--out", "-o", help="Output directory")] = None,
    speed: Annotated[float, typer.Option("--speed", "-s", help="Playback speed multiplier")] = 2.0,
    rate: Annotated[int, typer.Option("--rate", "-r", help="Sample rate in Hz")] = 16000,
    mono: Annotated[bool, typer.Option("--mono/--stereo", help="Mono or stereo output")] = True,
    fmt: Annotated[
        str, typer.Option("--format", "-f", help="Output format: wav, mp3, flac")
    ] = "wav",
    json_output: Annotated[bool, typer.Option("--json", help="JSON output")] = False,
) -> None:
    """Extract audio from video files, optimized for transcription (pipe-composable)."""
    from vlmctx.display import console, output_console
    from vlmctx.ffmpeg import extract_audio, ffmpeg_available

    if not ffmpeg_available():
        console.print("[red]ffmpeg not found on PATH[/red]", style="bold")
        raise typer.Exit(1)

    paths: list[Path] = []
    stdin_paths = read_paths_from_stdin()
    if stdin_paths:
        paths.extend(Path(p) for p in stdin_paths)
    if files:
        paths.extend(files)

    if not paths:
        console.print("[red]No files specified[/red]")
        raise typer.Exit(1)

    all_results = []

    for media_path in paths:
        if not media_path.exists():
            console.print(f"[yellow]skip: {media_path} (not found)[/yellow]")
            continue

        out_path = None
        if out:
            out.mkdir(parents=True, exist_ok=True)
            out_path = out / f"{media_path.stem}_{speed}x.{fmt}"

        result = extract_audio(
            media_path,
            out_path=out_path,
            speed=speed,
            sample_rate=rate,
            mono=mono,
            fmt=fmt,
        )

        entry = {
            "source": str(media_path),
            "audio": str(result.path),
            "speed": result.speed,
            "sample_rate": result.sample_rate,
            "channels": result.channels,
            "size_kb": result.path.stat().st_size // 1024 if result.path.exists() else 0,
        }
        all_results.append(entry)

    if not all_results:
        return

    if json_output:
        import json

        output_console.print(json.dumps(all_results, indent=2))
        return

    if is_piped_output():
        for entry in all_results:
            output_console.print(entry["audio"])
    else:
        from rich.table import Table as RichTable

        from vlmctx.display import format_size

        tbl = RichTable(
            title="[bold]vlmctx audio[/bold]",
            show_header=True,
            header_style="bold",
            padding=(0, 1),
            border_style="dim",
            expand=False,
        )
        tbl.add_column("source", style="bold")
        tbl.add_column("output", style="cyan")
        tbl.add_column("size", justify="right", style="bright_blue")
        tbl.add_column("speed", justify="right")
        tbl.add_column("rate", justify="right")
        tbl.add_column("channels", justify="right")

        for entry in all_results:
            out_size = format_size(entry["size_kb"] * 1024)
            tbl.add_row(
                Path(entry["source"]).name,
                str(entry["audio"]),
                out_size,
                f"{entry['speed']}x",
                f"{entry['sample_rate']}Hz",
                str(entry["channels"]),
            )

        output_console.print(tbl)
