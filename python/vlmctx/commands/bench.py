"""vlmctx bench -- benchmark all subcommands with statistical analysis."""

from __future__ import annotations

import gc
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Callable, Optional

import typer

from vlmctx.commands.bench_commands import ALL_COMMANDS, BenchCommand


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


# ── Benchmark runner ─────────────────────────────────────────────────


def _run_benchmarks(
    directory: Path,
    rounds: int,
    warmup: int,
    on_progress: Callable[[str, str], None] | None = None,
) -> tuple[list[BenchResult], dict[str, Any]]:
    """Run all benchmark commands, return (results, target_info)."""
    from vlmctx._vlmctx import Scanner
    from vlmctx.context import Context

    results: list[BenchResult] = []

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

    for cmd in ALL_COMMANDS:
        if on_progress:
            on_progress(cmd.group, cmd.name)

        if num_files == 0:
            results.append(BenchResult(cmd.name, cmd.group, skipped=True, skip_reason="empty directory"))
            continue

        fn = cmd.make_fn(directory, files, Scanner)
        if fn is None:
            results.append(BenchResult(cmd.name, cmd.group, skipped=True, skip_reason=cmd.skip_reason))
            continue

        fc = cmd.files_count_fn(directory, files) if cmd.files_count_fn else num_files
        tb = cmd.total_bytes_fn(directory, files) if cmd.total_bytes_fn else total_bytes

        r = BenchResult(cmd.name, cmd.group, files_count=fc, total_bytes=tb)
        r.timings_ms = _time_fn(fn, rounds, warmup)
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


# Latency thresholds (ms) per group: (green_cutoff, yellow_cutoff).
# Below green → dim green, between → dim yellow, above → dim red.
_LATENCY_THRESHOLDS: dict[str, tuple[float, float]] = {
    "L0": (10.0, 50.0),      # metadata: <10ms green, 10-50ms yellow, >50ms red
    "L1": (50.0, 200.0),     # extraction: <50ms green, 50-200ms yellow, >200ms red
    "L2": (1000.0, 5000.0),  # semantic/LLM: <1s green, 1-5s yellow, >5s red
}


def _latency_style(ms: float, group: str) -> str:
    """Return a rich style based on latency relative to group thresholds."""
    green, yellow = _LATENCY_THRESHOLDS.get(group, (50.0, 200.0))
    if ms <= green:
        return "dim green"
    if ms <= yellow:
        return "dim yellow"
    return "dim red"


def _render_summary(results: list[BenchResult], target_info: dict[str, Any]) -> None:
    """Render alternating command / stats rows in a panel."""
    from rich import box
    from rich.console import Group
    from rich.panel import Panel
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

    # Group results by group name
    groups_seen: list[str] = []
    groups_map: dict[str, list[BenchResult]] = {}
    for r in results:
        if r.group not in groups_map:
            groups_seen.append(r.group)
            groups_map[r.group] = []
        groups_map[r.group].append(r)

    for group_name in groups_seen:
        group_results = groups_map[group_name]
        group_label = {"L0": "L0 · Metadata", "L1": "L1 · Extraction"}.get(group_name, group_name)

        parts.append(Text())  # spacer
        section_header = Text()
        section_header.append(f"  {group_label}", style="bold underline")
        parts.append(section_header)

        for r in group_results:
            cmd_line = Text()

            if r.skipped:
                cmd_line.append(f"  $ {r.name}", style="dim")
                cmd_line.append(f"  — {r.skip_reason}", style="dim italic")
                parts.append(cmd_line)
                continue

            # Line 1: full-width command
            cmd_line.append("  $ ", style="dim")
            cmd_line.append(r.name, style="bold white")
            parts.append(cmd_line)

            # Line 2: stats, indented — colorized by latency
            color = _latency_style(r.mean_ms, r.group)
            stats_line = Text()
            stats_line.append("    ", style="")
            stats_line.append(_fmt_ms(r.mean_ms), style=f"bold {color}")
            stats_line.append(" ±", style="dim")
            stats_line.append(_fmt_ms(r.std_ms), style=color)
            stats_line.append("  min ", style="dim")
            stats_line.append(_fmt_ms(r.min_ms), style=color)
            stats_line.append("  max ", style="dim")
            stats_line.append(_fmt_ms(r.max_ms), style=color)
            if r.files_per_sec > 0:
                stats_line.append("  ", style="")
                stats_line.append(_fmt_rate(r.files_per_sec, "files/s"), style=color)
            if r.mb_per_sec > 0:
                stats_line.append("  ", style="")
                stats_line.append(_fmt_rate(r.mb_per_sec, "MB/s"), style=color)
            parts.append(stats_line)

    # Bottleneck analysis
    measured = [r for r in results if not r.skipped and r.timings_ms]
    if measured:
        slowest = max(measured, key=lambda r: r.mean_ms)
        fastest = min(measured, key=lambda r: r.mean_ms)

        parts.append(Text())  # spacer
        footer = Text()
        footer.append("  Slowest   ", style="dim")
        footer.append(slowest.name, style="bold yellow")
        footer.append(f"  {_fmt_ms(slowest.mean_ms)}", style="dim")
        footer.append(f"\n  Fastest   ", style="dim")
        footer.append(fastest.name, style="bold green")
        footer.append(f"  {_fmt_ms(fastest.mean_ms)}", style="dim")
        parts.append(footer)

    panel = Panel(
        Group(*parts),
        title="[bold]vlmctx bench[/bold]",
        title_align="left",
        expand=True,
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
