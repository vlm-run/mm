"""vlmctx keyframes -- extract video frame mosaics with uniform sampling."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from vlmctx.pipe import is_piped_output, read_paths_from_stdin


def keyframes_cmd(
    files: Annotated[Optional[list[Path]], typer.Argument(help="Video files to process")] = None,
    out: Annotated[
        Optional[Path], typer.Option("--out", "-o", help="Output directory for mosaics")
    ] = None,
    tile: Annotated[str, typer.Option("--tile", "-t", help="Tile grid as COLSxROWS")] = "6x8",
    width: Annotated[int, typer.Option("--width", "-w", help="Thumbnail width in pixels")] = 160,
    num_mosaics: Annotated[
        int, typer.Option("--num", "-n", help="Number of mosaics (1-8, each 6x8=48 frames)")
    ] = 1,
    quality: Annotated[
        int, typer.Option("--quality", "-q", help="JPEG quality (1=best, 31=worst)")
    ] = 3,
    strategy: Annotated[
        str,
        typer.Option(
            "--strategy", "-s", help="Frame selection: uniform (default), keyframe, scene"
        ),
    ] = "uniform",
    scene_threshold: Annotated[
        float, typer.Option("--scene-threshold", help="Scene change threshold (0.0-1.0)")
    ] = 0.3,
    blur_window: Annotated[
        int,
        typer.Option("--blur-window", help="Frames to evaluate for sharpness at each sample point"),
    ] = 10,
    workers: Annotated[
        int, typer.Option("--workers", help="Parallel ffmpeg workers for uniform strategy")
    ] = 8,
    json_output: Annotated[bool, typer.Option("--json", help="JSON output")] = False,
) -> None:
    """Extract frame mosaics from videos.

    Default: uniform temporal sampling (6x8 = 48 frames per mosaic) with
    per-frame blur rejection via ffmpeg's thumbnail filter.

    Use --num 1..8 to control how many mosaics (up to 384 frames total).
    Pipe-composable: vlmctx find --kind video | vlmctx keyframes
    """
    from vlmctx.display import console, output_console
    from vlmctx.ffmpeg import (
        extract_keyframe_mosaics,
        extract_scene_mosaics,
        extract_uniform_mosaics,
        ffmpeg_available,
    )

    if not ffmpeg_available():
        console.print("[red]ffmpeg not found on PATH[/red]", style="bold")
        raise typer.Exit(1)

    num_mosaics = max(1, min(num_mosaics, 8))

    paths: list[Path] = []
    stdin_paths = read_paths_from_stdin()
    if stdin_paths:
        paths.extend(Path(p) for p in stdin_paths)
    if files:
        paths.extend(files)

    if not paths:
        console.print("[red]No files specified[/red]")
        raise typer.Exit(1)

    cols, rows = _parse_tile(tile)
    all_results = []

    for video_path in paths:
        if not video_path.exists():
            console.print(f"[yellow]skip: {video_path} (not found)[/yellow]")
            continue

        if strategy == "uniform":
            result = extract_uniform_mosaics(
                video_path,
                out_dir=out,
                tile_cols=cols,
                tile_rows=rows,
                thumb_width=width,
                num_mosaics=num_mosaics,
                quality=quality,
                blur_window=blur_window,
                max_workers=workers,
            )
        elif strategy == "scene":
            result = extract_scene_mosaics(
                video_path,
                out_dir=out,
                threshold=scene_threshold,
                tile_cols=cols,
                tile_rows=rows,
                thumb_width=width,
                max_mosaics=num_mosaics,
                quality=quality,
            )
        else:
            result = extract_keyframe_mosaics(
                video_path,
                out_dir=out,
                tile_cols=cols,
                tile_rows=rows,
                thumb_width=width,
                max_mosaics=num_mosaics,
                quality=quality,
            )

        entry = {
            "video": str(video_path),
            "frames": result.frame_count,
            "mosaics": [str(p) for p in result.mosaic_paths],
            "tile": f"{cols}x{rows}",
            "strategy": result.strategy,
        }
        if result.elapsed_ms > 0:
            entry["elapsed_ms"] = round(result.elapsed_ms, 1)
        if result.duration_s > 0:
            entry["duration_s"] = round(result.duration_s, 2)
        all_results.append(entry)

        if not json_output:
            if is_piped_output():
                for p in result.mosaic_paths:
                    output_console.print(str(p))
            else:
                from rich.panel import Panel
                from rich.text import Text

                body = Text()
                body.append(f"  {result.frame_count}", style="bold bright_blue")
                body.append(" frames → ", style="dim")
                body.append(f"{len(result.mosaic_paths)}", style="bold bright_green")
                body.append(f" mosaic(s)  [{result.strategy}]\n", style="dim")
                if result.elapsed_ms > 0:
                    body.append(f"  ⏱  {result.elapsed_ms:.0f}ms", style="bright_yellow")
                    if result.duration_s > 0:
                        speedup = result.duration_s * 1000 / result.elapsed_ms
                        body.append(f"  ({speedup:.0f}x realtime)\n", style="dim")
                    else:
                        body.append("\n")
                for p in result.mosaic_paths:
                    kb = p.stat().st_size // 1024
                    body.append(f"  {p}", style="white")
                    body.append(f"  ({kb}KB)\n", style="dim")
                output_console.print(
                    Panel(body, title=f"[bold]{video_path.name}[/bold]", expand=False)
                )

    if json_output:
        import json

        print(json.dumps(all_results, indent=2))


def _parse_tile(tile: str) -> tuple[int, int]:
    parts = tile.lower().split("x")
    if len(parts) == 2:
        return int(parts[0]), int(parts[1])
    n = int(parts[0])
    return n, n
