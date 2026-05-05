"""mm peek -- direct file metadata extraction.

``peek`` is the cheap, deterministic counterpart to ``cat``: it surfaces
locally-extracted metadata (dimensions, EXIF, codec, duration, mime,
content hash, …) for one or more files. Run it as often as you like — every invocation
is a fresh scan.

Use ``peek`` for "what is this file?", and ``cat`` for "what does this
file *say*?".
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Optional

import typer

from mm.utils import BaseFormat

if TYPE_CHECKING:
    from mm.peek import FileMetadata

print("sys argv:", sys.argv)

if len(sys.argv) > 1 and "peek" in sys.argv:
    from mm.peek import _preload_magika

    _preload_magika()


def peek_cmd(
    files: Annotated[
        Optional[list[Path]],
        typer.Argument(help="One or more files to inspect"),
    ] = None,
    format: Annotated[
        Optional[BaseFormat],
        typer.Option(
            "--format",
            "-f",
            help="Output format: rich (default in TTY), json, pretty-json, tsv, csv, stdout",
        ),
    ] = None,
) -> None:
    """Surface locally-extracted file metadata. Always direct, never cached.

    Examples:
      mm peek photo.png            # dimensions, EXIF, content hash
      mm peek paper.pdf            # mime, hash (no extracted text — use ``mm cat`` for that)
      mm peek a.png b.mp4 --format json
    """
    from mm.pipe import read_paths_from_stdin

    paths = list(files or [])
    stdin_paths = read_paths_from_stdin()
    if stdin_paths:
        paths.extend(Path(p) for p in stdin_paths)
    if not paths:
        typer.echo("Error: No files specified.", err=True)
        raise typer.Exit(1)

    from mm.display import resolve_format
    from mm.peek import FileMetadata

    fmt = resolve_format(format.value if format else None)

    rows: list[FileMetadata] = []
    for p in paths:
        if not p.exists():
            typer.echo(f"Error: {p} not found.", err=True)
            continue
        if not p.is_file():
            typer.echo(f"Error: {p} is not a regular file.", err=True)
            continue
        rows.append(FileMetadata.from_path(p))

    if not rows:
        raise typer.Exit(1)

    from mm.display import emit_csv, emit_rows, emit_tsv

    dict_rows_full = [r.to_dict() for r in rows]
    dict_rows = [{k: v for k, v in d.items() if v is not None} for d in dict_rows_full]

    if fmt in ("json", "pretty-json"):
        emit_rows(fmt, dict_rows)
    elif fmt == "tsv":
        emit_tsv(dict_rows)
    elif fmt == "csv":
        emit_csv(dict_rows)
    else:
        _emit_rich(rows)


def _emit_rich(rows: list[FileMetadata]) -> None:
    """Render each file as a Rich panel listing only populated fields.

    Hides ``None`` fields so the output is dense and scannable; the
    flat shape is preserved for JSON/TSV consumers.
    """
    from rich.panel import Panel
    from rich.table import Table

    from mm.display import KIND_STYLES, format_size, output_console

    for r in rows:
        d = r.to_dict()
        kind_style = KIND_STYLES.get(r.kind, "white")

        tbl = Table.grid(padding=(0, 1))
        tbl.add_column(style="dim")
        tbl.add_column()

        tbl.add_row("kind", f"[{kind_style}]{r.kind}[/{kind_style}]")
        tbl.add_row("size", format_size(r.size) or str(r.size))
        tbl.add_row("mime", r.mime)
        if r.magic_mime and r.magic_mime != r.mime:
            tbl.add_row("magic_mime", r.magic_mime)
        if r.content_hash:
            tbl.add_row("hash", r.content_hash)

        # Visual / dimension fields
        if r.dimensions:
            tbl.add_row("dimensions", r.dimensions)
        if r.phash is not None:
            tbl.add_row("phash", f"{r.phash:016x}")

        # EXIF (image)
        for label, key in (
            ("camera", "exif_camera"),
            ("date", "exif_date"),
            ("gps", "exif_gps"),
            ("orientation", "exif_orientation"),
        ):
            if d.get(key):
                tbl.add_row(label, str(d[key]))

        # AV
        if r.duration_s is not None:
            mins, secs = divmod(r.duration_s, 60)
            tbl.add_row("duration", f"{int(mins)}m {secs:.1f}s ({r.duration_s:.2f}s)")
        if r.fps:
            tbl.add_row("fps", f"{r.fps:g}")
        if r.video_codec:
            tbl.add_row("video_codec", r.video_codec)
        if r.audio_codec:
            tbl.add_row("audio_codec", r.audio_codec)
        elif r.has_audio is False:
            tbl.add_row("audio", "none")

        # Document
        if r.pages is not None:
            tbl.add_row("pages", str(r.pages))

        if r.aimeta:
            inner = Table.grid(padding=(0, 1))
            inner.add_column(style="dim")
            inner.add_column()
            for k, v in r.aimeta.items():
                inner.add_row(k, "" if v is None else str(v))
            tbl.add_row("aimeta", inner)

        output_console.print(Panel(tbl, title=f"[bold]{r.name}[/bold]", border_style=kind_style))
