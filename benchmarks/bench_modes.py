#!/usr/bin/env python3
"""Information-theoretic benchmarks for mm multi-modal extraction.

Measures bits/s throughput — how fast we extract semantic information
from raw media data. Maximize bits/s, minimize latency.

Usage:
    python benchmarks/bench_modes.py [data_dir]
    mm cat benchmarks/bench_modes.py -l 0  # or just run directly
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


@dataclass
class BenchResult:
    """Single benchmark measurement."""

    label: str
    file: str
    file_bytes: int
    wall_s: float
    mode: str = ""
    # Modality-specific
    resolution: str = ""
    pixels: int = 0
    duration_s: float = 0.0
    fps: float = 0.0
    pages: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def bits(self) -> int:
        return self.file_bytes * 8

    @property
    def throughput_bps(self) -> float:
        return self.bits / max(self.wall_s, 1e-6)

    @property
    def throughput_str(self) -> str:
        bps = self.throughput_bps
        if bps >= 1e9:
            return f"{bps / 1e9:.2f} Gbps"
        if bps >= 1e6:
            return f"{bps / 1e6:.2f} Mbps"
        if bps >= 1e3:
            return f"{bps / 1e3:.2f} kbps"
        return f"{bps:.0f} bps"

    @property
    def latency_str(self) -> str:
        if self.wall_s < 0.001:
            return f"{self.wall_s * 1e6:.0f}µs"
        if self.wall_s < 1.0:
            return f"{self.wall_s * 1000:.0f}ms"
        return f"{self.wall_s:.2f}s"

    @property
    def media_rate_str(self) -> str:
        if self.duration_s > 0:
            rate = self.duration_s / max(self.wall_s, 1e-6)
            return f"{rate:.1f}x realtime"
        if self.pages > 0:
            rate = self.pages / max(self.wall_s, 1e-6)
            return f"{rate:.1f} pages/s"
        if self.pixels > 0:
            rate = self.pixels / max(self.wall_s, 1e-6)
            if rate >= 1e6:
                return f"{rate / 1e6:.1f} Mpx/s"
            return f"{rate:.0f} px/s"
        return ""


def _size_str(b: int) -> str:
    if b >= 1e9:
        return f"{b / 1e9:.2f} GB"
    if b >= 1e6:
        return f"{b / 1e6:.2f} MB"
    if b >= 1e3:
        return f"{b / 1e3:.1f} KB"
    return f"{b} B"


def _run_bench(cmd: list[str], runs: int = 3) -> float:
    """Run a command multiple times and return median wall time in seconds."""
    times = []
    for _ in range(runs):
        t0 = time.monotonic()
        subprocess.run(cmd, capture_output=True, timeout=300)
        times.append(time.monotonic() - t0)
    times.sort()
    return times[len(times) // 2]  # median


def _probe_image(path: Path) -> tuple[str, int]:
    """Get image dimensions via mm L1."""
    try:
        r = subprocess.run(
            ["mm", "cat", str(path), "-l", "1"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        import re

        m = re.search(r"(\d+)x(\d+)", r.stdout)
        if m:
            w, h = int(m.group(1)), int(m.group(2))
            return f"{w}x{h}", w * h
    except Exception:
        pass
    return "", 0


def _probe_video(path: Path) -> tuple[str, float, float]:
    """Get video resolution, duration, fps via mm L1."""
    try:
        r = subprocess.run(
            ["mm", "cat", str(path), "-l", "1"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        import re

        dims = ""
        m = re.search(r"(\d+)x(\d+)", r.stdout)
        if m:
            dims = m.group(0)
        dur = 0.0
        m = re.search(r"([\d.]+)s\)", r.stdout)
        if m:
            dur = float(m.group(1))
        fps = 0.0
        m = re.search(r"FPS:\s*([\d.]+)", r.stdout)
        if m:
            fps = float(m.group(1))
        return dims, dur, fps
    except Exception:
        return "", 0.0, 0.0


def _probe_pdf_pages(path: Path) -> int:
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        n = len(pdf)
        pdf.close()
        return n
    except Exception:
        return 0


def bench_image(path: Path, runs: int = 3) -> list[BenchResult]:
    dims, pixels = _probe_image(path)
    results = []
    for mode in ("fast", "accurate"):
        console.print(f"  [dim]Benchmarking image {mode}...[/dim]", end="\r")
        t = _run_bench(
            ["mm", "cat", str(path), "-l", "2", "--mode", mode, "--format", "json"], runs
        )
        results.append(
            BenchResult(
                label=f"image/{mode}",
                file=path.name,
                file_bytes=path.stat().st_size,
                wall_s=t,
                mode=mode,
                resolution=dims,
                pixels=pixels,
            )
        )
    return results


def bench_video(path: Path, runs: int = 2) -> list[BenchResult]:
    dims, dur, fps = _probe_video(path)
    results = []
    for mode in ("fast", "accurate"):
        console.print(f"  [dim]Benchmarking video {mode}...[/dim]", end="\r")
        t = _run_bench(
            ["mm", "cat", str(path), "-l", "2", "--mode", mode, "--format", "json"], runs
        )
        results.append(
            BenchResult(
                label=f"video/{mode}",
                file=path.name,
                file_bytes=path.stat().st_size,
                wall_s=t,
                mode=mode,
                resolution=dims,
                duration_s=dur,
                fps=fps,
            )
        )
    return results


def bench_pdf(path: Path, runs: int = 5) -> list[BenchResult]:
    pages = _probe_pdf_pages(path)
    console.print("  [dim]Benchmarking PDF L1...[/dim]", end="\r")
    t = _run_bench(["mm", "cat", str(path), "-l", "1", "--format", "json"], runs)
    return [
        BenchResult(
            label="document/L1",
            file=path.name,
            file_bytes=path.stat().st_size,
            wall_s=t,
            mode="L1",
            pages=pages,
        )
    ]


def _sysinfo_panel() -> Panel:
    from mm.sysinfo import collect

    info = collect()
    lines = [
        f"[bold]ffmpeg[/bold]       {info.ffmpeg_version or '[red]not found[/red]'}",
        f"[bold]GPU[/bold]          {info.gpu_name or '[dim]none (CPU)[/dim]'}",
        f"[bold]CUDA[/bold]         {'[green]yes[/green]' if info.cuda_available else '[dim]no[/dim]'}",
        f"[bold]whisper[/bold]      {'[green]yes[/green]' if info.whisper_available else '[dim]no[/dim]'}",
        f"[bold]scenedetect[/bold]  {'[green]yes[/green]' if info.scenedetect_available else '[dim]no[/dim]'}",
        f"[bold]docling[/bold]      {'[green]yes[/green]' if info.docling_available else '[dim]no[/dim]'}",
    ]
    return Panel("\n".join(lines), title="[bold]System", border_style="blue", box=box.ROUNDED)


def _file_info_panel(label: str, path: Path, **kwargs) -> Panel:
    size = path.stat().st_size
    bits = size * 8
    lines = [
        f"[bold]File[/bold]    {path.name}",
        f"[bold]Size[/bold]    {_size_str(size)} ({bits:,} bits)",
    ]
    if "resolution" in kwargs and kwargs["resolution"]:
        lines.append(f"[bold]Res[/bold]     {kwargs['resolution']}")
    if "pixels" in kwargs and kwargs["pixels"]:
        bpp = bits / kwargs["pixels"]
        lines.append(f"[bold]Pixels[/bold]  {kwargs['pixels']:,} ({bpp:.2f} bits/px)")
    if "duration_s" in kwargs and kwargs["duration_s"]:
        d = kwargs["duration_s"]
        bitrate = bits / d
        lines.append(f"[bold]Duration[/bold] {d:.1f}s")
        lines.append(f"[bold]Bitrate[/bold]  {bitrate / 1e6:.2f} Mbps")
    if "fps" in kwargs and kwargs["fps"]:
        lines.append(f"[bold]FPS[/bold]     {kwargs['fps']}")
    if "pages" in kwargs and kwargs["pages"]:
        bpp = bits / kwargs["pages"]
        lines.append(f"[bold]Pages[/bold]   {kwargs['pages']} ({bpp:,.0f} bits/page)")
    return Panel("\n".join(lines), title=f"[bold]{label}", border_style="cyan", box=box.ROUNDED)


def _results_table(results: list[BenchResult]) -> Table:
    table = Table(box=box.SIMPLE_HEAVY, show_edge=False, pad_edge=False)
    table.add_column("Mode", style="bold")
    table.add_column("Latency", justify="right")
    table.add_column("Throughput", justify="right", style="green")
    table.add_column("Media Rate", justify="right", style="cyan")
    table.add_column("Speedup", justify="right", style="yellow")

    base_time = results[0].wall_s if results else 1
    for r in results:
        speedup = base_time / max(r.wall_s, 1e-6)
        speedup_str = f"{speedup:.2f}x" if speedup != 1.0 else "baseline"
        table.add_row(
            r.mode,
            r.latency_str,
            r.throughput_str,
            r.media_rate_str or "—",
            speedup_str,
        )
    return table


def main():
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "data" / "1-demo"
    if not data_dir.exists():
        console.print(f"[red]Directory not found: {data_dir}[/red]")
        sys.exit(1)

    console.print()
    console.print(
        Panel(
            "[bold]mm multi-modal extraction benchmarks[/bold]\n"
            "[dim]Information-theoretic: maximize bits/s, minimize latency[/dim]",
            border_style="bright_blue",
            box=box.DOUBLE,
        )
    )
    console.print()
    console.print(_sysinfo_panel())
    console.print()

    all_results: list[BenchResult] = []

    # Find sample files
    def _find(exts):
        for ext in exts:
            for f in sorted(data_dir.rglob(f"*{ext}"))[:1]:
                return f
        return None

    image = _find([".jpg", ".png", ".jpeg"])
    video = _find([".mp4", ".mkv"])
    pdf = _find([".pdf"])

    # Image
    if image:
        dims, pixels = _probe_image(image)
        console.print(_file_info_panel("Image", image, resolution=dims, pixels=pixels))
        results = bench_image(image)
        all_results.extend(results)
        console.print(_results_table(results))
        console.print()

    # Video
    if video:
        dims, dur, fps = _probe_video(video)
        console.print(_file_info_panel("Video", video, resolution=dims, duration_s=dur, fps=fps))
        results = bench_video(video)
        all_results.extend(results)
        console.print(_results_table(results))
        console.print()

    # PDF
    if pdf:
        pages = _probe_pdf_pages(pdf)
        console.print(_file_info_panel("Document (PDF)", pdf, pages=pages))
        results = bench_pdf(pdf)
        all_results.extend(results)
        console.print(_results_table(results))
        console.print()

    # Summary table
    if all_results:
        summary = Table(
            title="Summary — All Modalities",
            box=box.ROUNDED,
            border_style="bright_blue",
        )
        summary.add_column("Pipeline", style="bold")
        summary.add_column("File", style="dim")
        summary.add_column("Size", justify="right")
        summary.add_column("Latency", justify="right")
        summary.add_column("Throughput", justify="right", style="green bold")
        summary.add_column("Media Rate", justify="right", style="cyan")

        for r in all_results:
            summary.add_row(
                r.label,
                r.file,
                _size_str(r.file_bytes),
                r.latency_str,
                r.throughput_str,
                r.media_rate_str or "—",
            )
        console.print(summary)
        console.print()

    console.print("[dim]Key metric: bits/s = information extraction rate. Higher = better.[/dim]")


if __name__ == "__main__":
    main()
