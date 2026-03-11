"""vlmctx pages -- PDF page mosaic extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from vlmctx.pipe import is_piped_output


def pages_cmd(
    path: Annotated[Path, typer.Argument(help="PDF file or directory of PDFs")],
    out_dir: Annotated[
        Optional[Path], typer.Option("--out", "-o", help="Output directory for mosaics")
    ] = None,
    cols: Annotated[int, typer.Option("--cols", help="Tile columns")] = 4,
    rows: Annotated[int, typer.Option("--rows", help="Tile rows")] = 4,
    width: Annotated[int, typer.Option("--width", "-w", help="Thumbnail width px")] = 200,
    max_pages: Annotated[
        Optional[int], typer.Option("--max-pages", "-n", help="Max pages to render")
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="JSON output")] = False,
) -> None:
    """Extract PDF page mosaics -- visual snapshots of document pages."""
    from vlmctx.pdf import extract_pdf_mosaics, pypdfium2_available

    if not pypdfium2_available():
        raise typer.BadParameter("pypdfium2 not installed: pip install pypdfium2")

    pdfs: list[Path] = []
    if path.is_file():
        pdfs = [path]
    elif path.is_dir():
        pdfs = sorted(path.glob("**/*.pdf"))
    else:
        raise typer.BadParameter(f"Not a file or directory: {path}")

    if not pdfs:
        raise typer.BadParameter(f"No PDFs found in {path}")

    all_results = []
    for pdf in pdfs:
        result = extract_pdf_mosaics(
            pdf,
            out_dir=out_dir,
            tile_cols=cols,
            tile_rows=rows,
            thumb_width=width,
            max_pages=max_pages,
        )
        all_results.append((pdf, result))

    if json_output:
        import json

        output = []
        for pdf, r in all_results:
            output.append({
                "pdf": str(pdf),
                "pages": r.page_count,
                "rendered": r.rendered_pages,
                "mosaics": [str(p) for p in r.mosaic_paths],
                "elapsed_ms": round(r.elapsed_ms, 1),
            })
        print(json.dumps(output, indent=2))
        return

    if is_piped_output():
        for _, r in all_results:
            for mp in r.mosaic_paths:
                print(mp)
        return

    from rich.table import Table as RichTable

    from vlmctx.display import format_size, output_console

    tbl = RichTable(
        title="[bold]vlmctx pages[/bold]",
        show_header=True,
        header_style="bold",
        padding=(0, 1),
        border_style="dim",
        expand=False,
    )
    tbl.add_column("pdf", style="bold")
    tbl.add_column("pages", justify="right")
    tbl.add_column("rendered", justify="right")
    tbl.add_column("mosaics", justify="right")
    tbl.add_column("time", justify="right", style="green")
    tbl.add_column("output", style="cyan")

    for pdf, r in all_results:
        mosaic_strs = "\n".join(
            f"{mp}  ({format_size(mp.stat().st_size)})" for mp in r.mosaic_paths
        )
        tbl.add_row(
            pdf.name,
            str(r.page_count),
            str(r.rendered_pages),
            str(len(r.mosaic_paths)),
            f"{r.elapsed_ms:.0f}ms",
            mosaic_strs,
        )

    output_console.print(tbl)
