"""vlmctx bench -- benchmark all subcommands with statistical analysis."""

from __future__ import annotations

import gc
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Callable, Optional

import typer


# ── Sparkline rendering ─────────────────────────────────────────────

_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _sparkline(values: list[float]) -> str:
    """Render a list of floats as a sparkline string."""
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = hi - lo if hi > lo else 1.0
    return "".join(_SPARK_CHARS[min(int((v - lo) / span * (len(_SPARK_CHARS) - 1)), len(_SPARK_CHARS) - 1)] for v in values)


# ── Data model ──────────────────────────────────────────────────────


@dataclass
class BenchResult:
    """Timing results for a single benchmark."""

    name: str
    group: str  # "L0", "L1", "Pipe"
    timings_ms: list[float] = field(default_factory=list)
    files_count: int = 0
    total_bytes: int = 0
    skipped: bool = False
    skip_reason: str = ""

    @property
    def mean_ms(self) -> float:
        return statistics.mean(self.timings_ms) if self.timings_ms else 0.0

    @property
    def std_ms(self) -> float:
        return statistics.stdev(self.timings_ms) if len(self.timings_ms) > 1 else 0.0

    @property
    def min_ms(self) -> float:
        return min(self.timings_ms) if self.timings_ms else 0.0

    @property
    def max_ms(self) -> float:
        return max(self.timings_ms) if self.timings_ms else 0.0

    @property
    def median_ms(self) -> float:
        return statistics.median(self.timings_ms) if self.timings_ms else 0.0

    @property
    def files_per_sec(self) -> float:
        if self.mean_ms > 0 and self.files_count > 0:
            return self.files_count / (self.mean_ms / 1000.0)
        return 0.0

    @property
    def mb_per_sec(self) -> float:
        if self.mean_ms > 0 and self.total_bytes > 0:
            return (self.total_bytes / (1024 * 1024)) / (self.mean_ms / 1000.0)
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        if self.skipped:
            return {
                "name": self.name,
                "group": self.group,
                "skipped": True,
                "skip_reason": self.skip_reason,
            }
        return {
            "name": self.name,
            "group": self.group,
            "mean_ms": round(self.mean_ms, 2),
            "std_ms": round(self.std_ms, 2),
            "min_ms": round(self.min_ms, 2),
            "max_ms": round(self.max_ms, 2),
            "median_ms": round(self.median_ms, 2),
            "files_per_sec": round(self.files_per_sec),
            "mb_per_sec": round(self.mb_per_sec, 1),
            "timings_ms": [round(t, 2) for t in self.timings_ms],
        }


# ── Timing harness ──────────────────────────────────────────────────


def _time_fn(fn: Callable[[], Any], rounds: int, warmup: int) -> list[float]:
    """Run fn with warmup, return list of elapsed times in ms."""
    for _ in range(warmup):
        fn()
        gc.collect()

    timings: list[float] = []
    for _ in range(rounds):
        gc.collect()
        gc.disable()
        t0 = time.perf_counter_ns()
        fn()
        t1 = time.perf_counter_ns()
        gc.enable()
        timings.append((t1 - t0) / 1_000_000)  # ns → ms
    return timings


# ── Benchmark definitions ───────────────────────────────────────────


def _pick_file_by_kind(files: list, kind: str) -> str | None:
    """Pick the first file of a given kind from the file list."""
    for f in files:
        if f.kind == kind:
            return f.path
    return None


def _run_benchmarks(
    directory: Path,
    rounds: int,
    warmup: int,
    on_progress: Callable[[str, str], None] | None = None,
) -> tuple[list[BenchResult], dict[str, Any]]:
    """Run all benchmark groups, return (results, target_info)."""
    from vlmctx._vlmctx import Scanner
    from vlmctx.context import Context

    resolved = str(directory.resolve())
    results: list[BenchResult] = []

    def _progress(group: str, name: str) -> None:
        if on_progress:
            on_progress(group, name)

    # Pre-scan to get target info and representative files.
    ctx = Context(directory)
    table = ctx.to_arrow()
    total_bytes = sum(r.as_py() for r in table.column("size")) if table.num_rows > 0 else 0
    files = ctx.files
    num_files = ctx.num_files

    target_info = {
        "directory": str(directory),
        "files": num_files,
        "total_bytes": total_bytes,
        "rounds": rounds,
        "warmup": warmup,
    }

    # ── L0: Metadata scanning ───────────────────────────────────────

    if num_files == 0:
        # No files — skip all benchmarks but report target info.
        for name in ["find .", "ls .", "wc .", "sql GROUP BY", "find --kind image"]:
            results.append(BenchResult(name, "L0", skipped=True, skip_reason="empty directory"))
        for name in ["cat code", "cat image", "cat video", "cat pdf", "grep pattern"]:
            results.append(BenchResult(name, "L1", skipped=True, skip_reason="empty directory"))
        return results, target_info

    # find .
    _progress("L0", "find .")

    def _bench_find():
        s = Scanner(resolved)
        s.scan()
        s.to_json_fast()

    r = BenchResult("find .", "L0", files_count=num_files, total_bytes=total_bytes)
    r.timings_ms = _time_fn(_bench_find, rounds, warmup)
    results.append(r)

    # ls .
    _progress("L0", "ls .")

    def _bench_ls():
        c = Context(directory)
        c.to_arrow()

    r = BenchResult("ls .", "L0", files_count=num_files, total_bytes=total_bytes)
    r.timings_ms = _time_fn(_bench_ls, rounds, warmup)
    results.append(r)

    # wc .
    _progress("L0", "wc .")

    def _bench_wc():
        import json as json_mod

        s = Scanner(resolved)
        s.scan()
        json_mod.loads(s.to_json_fast())

    r = BenchResult("wc .", "L0", files_count=num_files, total_bytes=total_bytes)
    r.timings_ms = _time_fn(_bench_wc, rounds, warmup)
    results.append(r)

    # sql GROUP BY
    _progress("L0", "sql GROUP BY")

    def _bench_sql():
        c = Context(directory)
        c.sql("SELECT kind, COUNT(*) as n FROM files GROUP BY kind")

    r = BenchResult("sql GROUP BY", "L0", files_count=num_files, total_bytes=total_bytes)
    r.timings_ms = _time_fn(_bench_sql, rounds, warmup)
    results.append(r)

    # find --kind image (filtered scan)
    _progress("L0", "find --kind image")

    def _bench_find_image():
        s = Scanner(resolved)
        s.scan()
        s.to_json_fast(kind="image")

    r = BenchResult("find --kind image", "L0", files_count=num_files, total_bytes=total_bytes)
    r.timings_ms = _time_fn(_bench_find_image, rounds, warmup)
    results.append(r)

    # ── L1: Content extraction ──────────────────────────────────────

    # cat on code files (batch)
    code_files = [f.path for f in files if f.kind == "code"][:20]
    if code_files:
        _progress("L1", f"cat code (x{len(code_files)})")
        scanner = Scanner(resolved)
        scanner.scan()

        def _bench_cat_code():
            for p in code_files:
                scanner.extract_l1(p)

        r = BenchResult(
            f"cat code (x{len(code_files)})", "L1",
            files_count=len(code_files), total_bytes=sum(
                (directory.resolve() / p).stat().st_size for p in code_files
            ),
        )
        r.timings_ms = _time_fn(_bench_cat_code, rounds, warmup)
        results.append(r)
    else:
        r = BenchResult("cat code", "L1", skipped=True, skip_reason="no code files")
        results.append(r)

    # cat on a single image
    img_path = _pick_file_by_kind(files, "image")
    if img_path:
        _progress("L1", "cat image")
        scanner = Scanner(resolved)
        scanner.scan()

        def _bench_cat_image():
            scanner.extract_l1(img_path)

        img_bytes = (directory.resolve() / img_path).stat().st_size
        r = BenchResult("cat image", "L1", files_count=1, total_bytes=img_bytes)
        r.timings_ms = _time_fn(_bench_cat_image, rounds, warmup)
        results.append(r)
    else:
        r = BenchResult("cat image", "L1", skipped=True, skip_reason="no image files")
        results.append(r)

    # cat on a single video
    vid_path = _pick_file_by_kind(files, "video")
    if vid_path:
        _progress("L1", "cat video")
        scanner = Scanner(resolved)
        scanner.scan()

        def _bench_cat_video():
            scanner.extract_l1(vid_path)

        vid_bytes = (directory.resolve() / vid_path).stat().st_size
        r = BenchResult("cat video", "L1", files_count=1, total_bytes=vid_bytes)
        r.timings_ms = _time_fn(_bench_cat_video, rounds, warmup)
        results.append(r)
    else:
        r = BenchResult("cat video", "L1", skipped=True, skip_reason="no video files")
        results.append(r)

    # cat on a PDF
    doc_path = _pick_file_by_kind(files, "document")
    if doc_path:
        _progress("L1", "cat pdf")

        def _bench_cat_pdf():
            from vlmctx.commands.cat import _l1_pdf
            _l1_pdf(directory.resolve() / doc_path)

        doc_bytes = (directory.resolve() / doc_path).stat().st_size
        r = BenchResult("cat pdf", "L1", files_count=1, total_bytes=doc_bytes)
        r.timings_ms = _time_fn(_bench_cat_pdf, rounds, warmup)
        results.append(r)
    else:
        r = BenchResult("cat pdf", "L1", skipped=True, skip_reason="no PDF files")
        results.append(r)

    # grep across all text files
    text_files = [f for f in files if not f.is_binary or f.kind == "document"]
    if text_files:
        _progress("L1", "grep pattern")

        def _bench_grep():
            import re
            regex = re.compile(r"import|include|require")
            for f in text_files[:50]:
                try:
                    full_path = directory.resolve() / f.path
                    content = full_path.read_text(errors="replace")
                    for line in content.splitlines():
                        regex.search(line)
                except Exception:
                    continue

        grep_bytes = sum(
            (directory.resolve() / f.path).stat().st_size
            for f in text_files[:50]
            if (directory.resolve() / f.path).exists()
        )
        r = BenchResult(
            "grep pattern", "L1",
            files_count=min(len(text_files), 50),
            total_bytes=grep_bytes,
        )
        r.timings_ms = _time_fn(_bench_grep, rounds, warmup)
        results.append(r)
    else:
        r = BenchResult("grep pattern", "L1", skipped=True, skip_reason="no text files")
        results.append(r)

    return results, target_info


# ── Rich output ─────────────────────────────────────────────────────


def _fmt_ms(ms: float) -> str:
    """Format milliseconds with appropriate precision."""
    if ms >= 1000:
        return f"{ms / 1000:.2f}s"
    if ms >= 100:
        return f"{ms:.0f}ms"
    if ms >= 10:
        return f"{ms:.1f}ms"
    return f"{ms:.2f}ms"


def _fmt_rate(rate: float, unit: str) -> str:
    """Format a throughput rate."""
    from vlmctx.display import format_number
    if rate <= 0:
        return "—"
    return f"{format_number(rate)} {unit}"


def _render_summary(results: list[BenchResult], target_info: dict[str, Any]) -> None:
    """Render the default summary panel."""
    from rich import box
    from rich.console import Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    from vlmctx.display import format_size, output_console

    parts: list[Any] = []

    # Header
    header = Text()
    header.append("  Target    ", style="dim")
    header.append(target_info["directory"], style="bold")
    header.append(f"  ({target_info['files']:,} files, {format_size(target_info['total_bytes'])})\n", style="dim")
    header.append("  Rounds    ", style="dim")
    header.append(f"{target_info['rounds']}", style="bold")
    header.append(f"  Warmup {target_info['warmup']}", style="dim")
    parts.append(header)

    # Build tables per group
    for group_name, group_label in [("L0", "L0 · Metadata Scanning"), ("L1", "L1 · Content Extraction")]:
        group_results = [r for r in results if r.group == group_name and not r.skipped]
        skipped = [r for r in results if r.group == group_name and r.skipped]
        if not group_results and not skipped:
            continue

        parts.append(Text())  # spacer

        tbl = Table(
            title=f"[bold]{group_label}[/bold]",
            title_style="",
            show_header=True,
            header_style="bold dim",
            padding=(0, 1),
            border_style="dim",
            expand=False,
            box=box.SIMPLE_HEAVY,
        )
        tbl.add_column("Command", style="white", no_wrap=True, min_width=20)
        tbl.add_column("Mean", justify="right", style="bold bright_green", min_width=8)
        tbl.add_column("±Std", justify="right", style="dim", min_width=8)
        tbl.add_column("Min", justify="right", style="dim cyan", min_width=8)
        tbl.add_column("Max", justify="right", style="dim cyan", min_width=8)
        tbl.add_column("Files/s", justify="right", style="bright_blue", min_width=8)
        tbl.add_column("MB/s", justify="right", style="bright_blue", min_width=8)

        for r in group_results:
            tbl.add_row(
                r.name,
                _fmt_ms(r.mean_ms),
                _fmt_ms(r.std_ms),
                _fmt_ms(r.min_ms),
                _fmt_ms(r.max_ms),
                _fmt_rate(r.files_per_sec, ""),
                _fmt_rate(r.mb_per_sec, ""),
            )

        for r in skipped:
            tbl.add_row(
                Text(r.name, style="dim"),
                Text("—", style="dim"),
                Text("", style="dim"),
                Text("", style="dim"),
                Text("", style="dim"),
                Text("", style="dim"),
                Text(r.skip_reason, style="dim italic"),
            )

        parts.append(tbl)

    # Bottleneck analysis
    measured = [r for r in results if not r.skipped and r.timings_ms]
    if measured:
        slowest = max(measured, key=lambda r: r.mean_ms)
        l0_results = [r for r in measured if r.group == "L0"]
        fastest_l0 = min(l0_results, key=lambda r: r.mean_ms) if l0_results else None

        parts.append(Text())  # spacer
        footer = Text()
        footer.append("  Bottleneck  ", style="dim")
        footer.append(slowest.name, style="bold yellow")
        footer.append(f" ({_fmt_ms(slowest.mean_ms)})", style="dim")
        if fastest_l0:
            footer.append(f"\n  Fastest L0  ", style="dim")
            footer.append(fastest_l0.name, style="bold green")
            footer.append(f" ({_fmt_ms(fastest_l0.mean_ms)}", style="dim")
            if fastest_l0.files_per_sec > 0:
                footer.append(f", {_fmt_rate(fastest_l0.files_per_sec, 'files/s')}", style="dim")
            footer.append(")", style="dim")
        parts.append(footer)

    panel = Panel(
        Group(*parts),
        title="[bold]vlmctx bench[/bold]",
        title_align="left",
        expand=False,
        padding=(1, 2),
        box=box.ROUNDED,
    )
    output_console.print(panel)


def _render_verbose(results: list[BenchResult], target_info: dict[str, Any]) -> None:
    """Render per-command detail panels with sparklines."""
    from rich import box
    from rich.panel import Panel
    from rich.text import Text

    from vlmctx.display import format_size, output_console

    # Print header
    header = Text()
    header.append("vlmctx bench", style="bold")
    header.append(f"  {target_info['directory']}", style="dim")
    header.append(f"  ({target_info['files']:,} files, {format_size(target_info['total_bytes'])})", style="dim")
    header.append(f"  rounds={target_info['rounds']} warmup={target_info['warmup']}", style="dim")
    output_console.print(header)
    output_console.print()

    measured = [r for r in results if not r.skipped]
    slowest = max(measured, key=lambda r: r.mean_ms) if measured else None

    for r in results:
        if r.skipped:
            panel = Panel(
                Text(f"  Skipped: {r.skip_reason}", style="dim italic"),
                title=f"[dim]{r.group}[/dim] [bold]{r.name}[/bold]",
                title_align="left",
                expand=False,
                padding=(0, 2),
                box=box.ROUNDED,
                border_style="dim",
            )
            output_console.print(panel)
            continue

        body = Text()

        # Timings row
        body.append("  Timings  ", style="dim")
        body.append("  ".join(_fmt_ms(t) for t in r.timings_ms), style="bright_blue")
        body.append("\n")

        # Sparkline
        body.append("  Spark    ", style="dim")
        body.append(_sparkline(r.timings_ms), style="bright_green")
        body.append("\n")

        # Stats
        body.append("  Mean ", style="dim")
        body.append(_fmt_ms(r.mean_ms), style="bold bright_green")
        body.append("  Std ", style="dim")
        body.append(_fmt_ms(r.std_ms), style="white")
        body.append("  Min ", style="dim")
        body.append(_fmt_ms(r.min_ms), style="cyan")
        body.append("  Max ", style="dim")
        body.append(_fmt_ms(r.max_ms), style="cyan")
        body.append("  Med ", style="dim")
        body.append(_fmt_ms(r.median_ms), style="white")
        body.append("\n")

        # Throughput
        if r.files_per_sec > 0 or r.mb_per_sec > 0:
            body.append("  Throughput  ", style="dim")
            if r.files_per_sec > 0:
                body.append(_fmt_rate(r.files_per_sec, "files/s"), style="bright_blue")
            if r.files_per_sec > 0 and r.mb_per_sec > 0:
                body.append("  ", style="dim")
            if r.mb_per_sec > 0:
                body.append(_fmt_rate(r.mb_per_sec, "MB/s"), style="bright_blue")

        # Slowest flag
        if slowest and r is slowest and len(measured) > 1:
            body.append("\n")
            body.append("  !! Slowest benchmark", style="bold yellow")

        border_style = "yellow" if (slowest and r is slowest and len(measured) > 1) else "dim"
        panel = Panel(
            body,
            title=f"[dim]{r.group}[/dim] [bold]{r.name}[/bold]",
            title_align="left",
            expand=False,
            padding=(0, 2),
            box=box.ROUNDED,
            border_style=border_style,
        )
        output_console.print(panel)


# ── CLI command ─────────────────────────────────────────────────────


def bench_cmd(
    directory: Annotated[Path, typer.Argument(help="Directory to benchmark")] = Path("."),
    rounds: Annotated[int, typer.Option("--rounds", "-r", help="Measurement rounds")] = 5,
    warmup: Annotated[int, typer.Option("--warmup", "-w", help="Warmup rounds")] = 1,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Per-command detail panels")] = False,
    format: Annotated[
        Optional[str], typer.Option("--format", help="Output format: rich, json")
    ] = None,
) -> None:
    """Benchmark all subcommands with statistical analysis."""
    from vlmctx.display import resolve_format

    fmt = resolve_format(format)

    # Progress callback for rich output
    if fmt == "rich":
        from vlmctx.display import console

        status = console.status("[dim]Starting benchmarks...[/dim]", spinner="dots")
        status.start()

        def on_progress(group: str, name: str) -> None:
            status.update(f"[dim]{group}[/dim] [bold]{name}[/bold]")

        try:
            results, target_info = _run_benchmarks(directory, rounds, warmup, on_progress)
        finally:
            status.stop()

        if verbose:
            _render_verbose(results, target_info)
        else:
            _render_summary(results, target_info)
    elif fmt == "json":
        results, target_info = _run_benchmarks(directory, rounds, warmup)

        from vlmctx.display import json_dumps

        output = {
            **target_info,
            "results": [r.to_dict() for r in results],
        }
        print(json_dumps(output))
    else:
        # tsv/csv fallback
        results, target_info = _run_benchmarks(directory, rounds, warmup)

        from vlmctx.display import emit_tsv

        rows = [r.to_dict() for r in results if not r.skipped]
        emit_tsv(rows, columns=["group", "name", "mean_ms", "std_ms", "min_ms", "max_ms", "files_per_sec", "mb_per_sec"])
