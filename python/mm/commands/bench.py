"""mm bench -- benchmark all subcommands with statistical analysis."""

from __future__ import annotations

import importlib.util
import re
import shlex
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Callable, Optional

import typer

from mm.commands.bench_commands import ALL_COMMANDS, BenchCommand, resolve_command
from mm.utils import BaseFormat

# ── Data model ──────────────────────────────────────────────────────


@dataclass
class BenchResult:
    """Timing results for a single benchmark."""

    name: str
    group: str  # "metadata", "fast", "accurate"
    timings_ms: list[float] = field(default_factory=list)
    files_count: int = 0
    total_bytes: int = 0
    preview_lines: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""
    media_duration_s: float = 0.0
    media_width: int = 0
    media_height: int = 0
    media_fps: float = 0.0
    media_pixel_bits: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    is_dry_run: bool = False
    tags: dict[str, str] = field(default_factory=dict)

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
    def speed_str(self) -> str:
        """Realtime multiplier: Nx for all benchmarks."""
        if self.mean_ms <= 0:
            return "—"
        processing_s = self.mean_ms / 1000.0
        if self.media_duration_s > 0:
            # Audio/video: media duration vs processing time
            multiplier = self.media_duration_s / processing_s
        elif self.files_count > 0:
            # Files: files per second as multiplier
            multiplier = self.files_count / processing_s
        else:
            return "—"
        if multiplier >= 100:
            return f"{multiplier:.0f}x"
        if multiplier >= 10:
            return f"{multiplier:.1f}x"
        return f"{multiplier:.2f}x"

    @property
    def mb_per_sec(self) -> float:
        if self.mean_ms > 0 and self.total_bytes > 0:
            return (self.total_bytes / (1024 * 1024)) / (self.mean_ms / 1000.0)
        return 0.0

    @property
    def uncompressed_bits(self) -> float:
        """Total uncompressed bits for the benchmark target.

        Images:  width × height × 24 (RGB), summed over batch.
        Video:   width × height × 24 × fps × duration.
        Other:   file size × 8.
        """
        if self.media_pixel_bits > 0:
            return self.media_pixel_bits
        return self.total_bytes * 8

    @property
    def bits_per_sec(self) -> float:
        """Throughput in bits/s (uncompressed for image/video)."""
        if self.mean_ms > 0:
            bits = self.uncompressed_bits
            if bits > 0:
                return bits / (self.mean_ms / 1000.0)
        return 0.0

    @property
    def bits_per_sec_str(self) -> str:
        """Human-readable bits/s throughput."""
        bps = self.bits_per_sec
        if bps >= 1e9:
            return f"{bps / 1e9:.2f} Gbps"
        if bps >= 1e6:
            return f"{bps / 1e6:.2f} Mbps"
        if bps >= 1e3:
            return f"{bps / 1e3:.2f} kbps"
        if bps > 0:
            return f"{bps:.0f} bps"
        return "—"

    def to_dict(self) -> dict[str, Any]:
        if self.skipped:
            payload: dict[str, Any] = {
                "name": self.name,
                "group": self.group,
                "skipped": True,
                "skip_reason": self.skip_reason,
            }
            if self.tags:
                payload["tags"] = dict(self.tags)
            return payload
        if self.is_dry_run:
            dry_payload: dict[str, Any] = {
                "name": self.name,
                "group": self.group,
                "dry_run": True,
                "argv": list(self.preview_lines),
                "files_count": self.files_count,
                "total_bytes": self.total_bytes,
            }
            if self.tags:
                dry_payload["tags"] = dict(self.tags)
            return dry_payload
        payload: dict[str, Any] = {
            "name": self.name,
            "group": self.group,
            "mean_ms": round(self.mean_ms, 2),
            "std_ms": round(self.std_ms, 2),
            "min_ms": round(self.min_ms, 2),
            "max_ms": round(self.max_ms, 2),
            "median_ms": round(self.median_ms, 2),
            "files_per_sec": round(self.files_per_sec),
            "media_duration_s": round(self.media_duration_s, 2) if self.media_duration_s else 0,
            "speed": self.speed_str,
            "mb_per_sec": round(self.mb_per_sec, 1),
            "bits_per_sec": round(self.bits_per_sec),
            "bits_per_sec_str": self.bits_per_sec_str,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "timings_ms": [round(t, 2) for t in self.timings_ms],
        }
        if self.tags:
            payload["tags"] = dict(self.tags)
        return payload


# ── Pre-ops sanitization ────────────────────────────────────────────


def _sanitize_files(files: list) -> list:
    """Return *files* with filesystem-noise entries removed."""

    def _is_filesystem_noise(name: str) -> bool:
        return name.startswith("._") or name == ".DS_Store"

    return [f for f in files if not _is_filesystem_noise(Path(f.path).name)]


# ── Timing harness ──────────────────────────────────────────────────


def _time_cmd(argv: list[str], rounds: int, warmup: int) -> list[float]:
    """Run a shell command with warmup, return list of elapsed times in ms.

    ``stdin`` is closed because ``mm cat`` (and friends) autodetect piped
    stdin and try to read paths from it — which deadlocks under
    ``subprocess.PIPE`` if we don't also feed something in.
    """
    for _ in range(warmup):
        subprocess.run(argv, capture_output=True, stdin=subprocess.DEVNULL)

    timings: list[float] = []
    for _ in range(rounds):
        t0 = time.perf_counter_ns()
        subprocess.run(argv, capture_output=True, stdin=subprocess.DEVNULL)
        t1 = time.perf_counter_ns()
        timings.append((t1 - t0) / 1_000_000)  # ns → ms
    return timings


# ── Benchmark runner ─────────────────────────────────────────────────


def _run_benchmarks(
    directory: Path,
    rounds: int,
    warmup: int,
    on_progress: Callable[[str, str], None] | None = None,
    commands: list | None = None,
    dry_run: bool = False,
) -> tuple[list[BenchResult], dict[str, Any]]:
    """Run benchmark commands, return (results, target_info).

    When ``dry_run`` is True the function still runs the directory pre-scan
    and resolves each command (so ``files_count``/``total_bytes``/``media_*``
    are populated), but does not invoke ``_time_cmd``. Each row is marked
    ``is_dry_run=True`` so the renderer / JSON encoder can show ``-``
    placeholders instead of zero metrics.
    """
    from mm.context import Context

    if commands is None:
        commands = ALL_COMMANDS

    results: list[BenchResult] = []
    t_wall = time.perf_counter_ns()

    # Pre-scan to get target info and pick representative files.
    ctx = Context(directory)
    files = _sanitize_files(ctx.files)
    num_files = len(files)
    total_bytes = sum(f.size for f in files)

    target_info = {
        "directory": str(directory),
        "files": num_files,
        "total_bytes": total_bytes,
        "rounds": rounds,
        "warmup": warmup,
        "dry_run": dry_run,
    }

    for cmd in commands:
        if on_progress:
            on_progress(cmd.group, cmd.name)

        if num_files == 0:
            results.append(
                BenchResult(
                    cmd.name,
                    cmd.group,
                    skipped=True,
                    skip_reason="empty directory",
                    tags=dict(cmd.tags),
                )
            )
            continue

        resolved = resolve_command(cmd, directory, files)
        if resolved is None:
            results.append(
                BenchResult(
                    cmd.name,
                    cmd.group,
                    skipped=True,
                    skip_reason=cmd.skip_reason,
                    tags=dict(cmd.tags),
                )
            )
            continue

        argv, fc, tb, media = resolved

        # Preview is the resolved shell command
        preview = [shlex.join(argv)]

        r = BenchResult(
            cmd.name,
            cmd.group,
            files_count=fc,
            total_bytes=tb,
            media_duration_s=media.duration_s,
            media_width=media.width,
            media_height=media.height,
            media_fps=media.fps,
            media_pixel_bits=media.pixel_bits,
            preview_lines=preview,
            is_dry_run=dry_run,
            tags=dict(cmd.tags),
        )
        if not dry_run:
            r.timings_ms = _time_cmd(argv, rounds, warmup)

        results.append(r)

    target_info["total_wall_ms"] = (time.perf_counter_ns() - t_wall) / 1_000_000
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


# Latency thresholds (ms) per group: (green_cutoff, yellow_cutoff).
_LATENCY_THRESHOLDS: dict[str, tuple[float, float]] = {
    "overhead": (80.0, 200.0),  # import/startup overhead
    "metadata": (100.0, 500.0),  # includes CLI startup (~60ms)
    "fast": (200.0, 1000.0),  # fast extractions
    "accurate": (2000.0, 10000.0),  # accurate extractions
}


def _latency_style(ms: float, group: str) -> str:
    """Return a rich style based on latency relative to group thresholds."""
    green, yellow = _LATENCY_THRESHOLDS.get(group, (200.0, 1000.0))
    if ms <= green:
        return "green"
    if ms <= yellow:
        return "yellow"
    return "red"


def _collect_tag_keys(results: list[BenchResult]) -> list[str]:
    """Return the union of tag keys across rows in first-seen order.

    Benchfile authors control column ordering by declaring tags in the
    order they want them displayed; we preserve that by iterating
    rows + each row's dict in insertion order.
    """
    seen: list[str] = []
    for r in results:
        for k in r.tags:
            if k not in seen:
                seen.append(k)
    return seen


def _humanize_tag_key(key: str) -> str:
    """``extra_body`` -> ``Extra Body``; ``model`` -> ``Model``."""
    return key.replace("_", " ").replace("-", " ").title()


def _render_table(results: list[BenchResult], target_info: dict[str, Any]) -> None:
    """Render all results as a single Rich table.

    Tags declared on any ``BenchCommand`` surface as additional columns
    inserted between ``Group`` and ``Command``, in first-seen key order.
    Rows that don't declare a given key render the cell as an empty
    string. This keeps the default benchmark suite (no tags anywhere)
    looking identical to before, while allowing benchfiles to surface
    structured metadata like ``model`` / ``extra_body`` without
    bespoke renderer code.
    """
    from rich import box
    from rich.table import Table
    from rich.text import Text

    from mm.display import format_size, output_console

    wall_ms = target_info.get("total_wall_ms", 0)
    wall_str = _fmt_ms(wall_ms) if wall_ms else "—"
    is_dry_run = bool(target_info.get("dry_run"))
    caption = (
        f"{target_info['files']:,} files  "
        f"{format_size(target_info['total_bytes'])}  "
        f"rounds={target_info['rounds']}  warmup={target_info['warmup']}  "
        f"total={wall_str}"
    )
    if is_dry_run:
        caption += "  (dry run — no commands executed)"

    tag_keys = _collect_tag_keys(results)
    n_tag_cols = len(tag_keys)

    table = Table(
        caption=caption,
        caption_style="dim",
        caption_justify="right",
        show_header=True,
        header_style="bold white",
        padding=(0, 1),
        border_style="dim",
        box=box.ROUNDED,
    )
    table.add_column("Group", style="dim", width=10)
    for key in tag_keys:
        # Wide free-text columns (extra_body, prompt, etc.) wrap;
        # short identifier-style ones (model) stay compact. We hint at
        # the difference by giving every tag column overflow="fold" so
        # JSON blobs wrap rather than truncate.
        table.add_column(_humanize_tag_key(key), no_wrap=False, overflow="fold")
    table.add_column("Command", no_wrap=True)
    table.add_column("Mean", justify="right")
    table.add_column("\u00b1Std", justify="right", style="dim")
    table.add_column("Min", justify="right")
    table.add_column("Max", justify="right")
    table.add_column("Speed", justify="right")
    table.add_column("MB/s", justify="right")
    table.add_column("bps", justify="right")

    prev_group = None
    for r in results:
        # Add section separator between groups
        if prev_group is not None and r.group != prev_group:
            table.add_section()
        prev_group = r.group

        tag_cells = [r.tags.get(k, "") for k in tag_keys]

        if r.skipped:
            # Tag cells stay populated (still useful context); the metric
            # cells collapse to one "skipped: <reason>" Text under the
            # Command column, with the rest blank.
            table.add_row(
                r.group,
                *tag_cells,
                Text(r.name, style="dim"),
                Text(f"skipped: {r.skip_reason}", style="dim italic"),
                *([""] * 7),
            )
            continue

        if r.is_dry_run:
            placeholder = Text("-", style="dim")
            table.add_row(
                r.group,
                *tag_cells,
                r.name,
                *([placeholder] * 7),
            )
            continue

        color = _latency_style(r.mean_ms, r.group)
        table.add_row(
            r.group,
            *tag_cells,
            r.name,
            Text(_fmt_ms(r.mean_ms), style=f"bold {color}"),
            Text(_fmt_ms(r.std_ms)),
            Text(_fmt_ms(r.min_ms), style=color),
            Text(_fmt_ms(r.max_ms), style=color),
            Text(r.speed_str),
            Text(f"{r.mb_per_sec:.1f}" if r.mb_per_sec > 0 else "\u2014"),
            Text(r.bits_per_sec_str, style="bright_cyan") if r.bits_per_sec > 0 else Text("\u2014"),
        )

    # ``n_tag_cols`` is referenced indirectly via ``tag_cells`` length;
    # bind it for type-checker friendliness when no tags are in play.
    _ = n_tag_cols
    output_console.print(table)


# ── Stdout snapshot mode ────────────────────────────────────────────


# CSI escape sequences (colour, dim, cursor, etc.) leak into snapshots when
# Rich treats ``subprocess.PIPE`` as a terminal. Strip them so the recorded
# markdown is plain text and diff-friendly.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from *text*."""
    return _ANSI_RE.sub("", text)


def _format_stdout_block(label: str, cmd: str, stdout: str) -> str:
    """Format one snapshot record: ``$ <cmd>  # <label>`` then stdout.

    Trailing whitespace and trailing newlines are stripped so adjacent
    blocks separated by ``---`` render cleanly in markdown. ANSI escape
    sequences are also removed — the recorded markdown is meant to be
    reviewable as plain text, not replayable as a terminal recording.
    """
    body = _strip_ansi(stdout).rstrip("\n")
    return f"$ {cmd}  # {label}\n{body}"


def _run_stdout_snapshot(
    *,
    directory: Path,
    mode: str,
    command_filter: str | None,
    timeout_s: float,
    with_generate: bool,
) -> None:
    """Run each filtered ``mm cat`` encoder variant once and emit its stdout.

    The output format is::

        $ mm cat <video> ... --pipeline encoder-a  # encoder-a
        <stdout from that run>
        ---
        $ mm cat <video> ... --pipeline encoder-b  # encoder-b
        ...

    Errors (non-zero exit, timeouts, missing files) are emitted in the same
    block style with the failure reason in place of stdout, so the resulting
    markdown is always valid and reviewable.

    Args:
        directory: Directory passed to ``mm bench``.
        mode: ``--mode`` value forwarded to each ``mm cat`` invocation.
        command_filter: Substring filter on synthesised bench-command names.
            ``None`` keeps everything; ``"video"`` keeps only video encoders.
        timeout_s: Wall-clock cap per command. Hitting it terminates the
            subprocess and records ``[timeout after Xs]`` for that block.
        with_generate: When False (default) each ``mm cat`` invocation gets
            ``--no-generate`` so the snapshot is LLM-free, deterministic,
            and offline-friendly. When True, the full pipeline runs
            (including the LLM step) — useful for capturing real model
            output but slow and dependent on the active profile.
    """
    from mm.commands.bench_commands import build_encoder_cat_commands, resolve_command
    from mm.context import Context

    if mode not in ("fast", "accurate"):
        typer.echo(
            f"Error: --format stdout only supports --mode fast|accurate (got {mode!r}).",
            err=True,
        )
        raise typer.Exit(code=1)

    ctx = Context(directory)
    files = _sanitize_files(ctx.files)
    if not files:
        typer.echo(f"Error: no files found in {directory}", err=True)
        raise typer.Exit(code=1)

    commands = build_encoder_cat_commands(files, mode=mode, no_generate=not with_generate)
    if command_filter:
        needle = command_filter.lower()
        commands = [c for c in commands if needle in c.name.lower()]
    if not commands:
        typer.echo(
            "Error: no encoders applicable to files in this directory "
            f"(mode={mode!r}, filter={command_filter!r}).",
            err=True,
        )
        raise typer.Exit(code=1)

    blocks: list[str] = []
    for cmd in commands:
        resolved = resolve_command(cmd, directory, files)
        if resolved is None:
            blocks.append(
                _format_stdout_block(cmd.name, cmd.cmd_template, f"[skipped: {cmd.skip_reason}]")
            )
            continue

        argv, _, _, _ = resolved
        # The bench harness resolves ``{file}`` to an absolute path so the
        # subprocess can find it. For the *recorded* snapshot we strip the
        # directory prefix down to the file's basename — ``$ mm cat
        # bakery.mp4 ...`` reads cleanly in ``tests/stdout/*.md`` and stays
        # stable regardless of where the user has the test data on disk.
        abs_paths = {a for a in argv if a.startswith("/") and Path(a).is_file()}
        display_argv = [Path(a).name if a in abs_paths else a for a in argv]
        cmd_str = shlex.join(display_argv)
        try:
            # ``mm cat`` autodetects a piped stdin (`isatty()` is False under
            # subprocess.PIPE) and tries to read paths from it. Close stdin
            # explicitly so the snapshot subprocess never blocks on input.
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            blocks.append(
                _format_stdout_block(cmd.name, cmd_str, f"[timeout after {timeout_s:.0f}s]")
            )
            continue

        # Mirror the same path normalisation in the captured stdout so the
        # ``"path": "..."`` field in JSON output is stable too.
        clean_stdout = proc.stdout
        for abs_path in abs_paths:
            clean_stdout = clean_stdout.replace(abs_path, Path(abs_path).name)

        if proc.returncode != 0:
            err_tail = (proc.stderr or "").strip().splitlines()[-5:]
            err_blob = "\n".join(err_tail) if err_tail else "(no stderr)"
            body = f"[exit {proc.returncode}]\n{err_blob}"
            blocks.append(_format_stdout_block(cmd.name, cmd_str, body))
            continue

        blocks.append(_format_stdout_block(cmd.name, cmd_str, clean_stdout))

    print("\n---\n".join(blocks))


# ── External benchfile loader ────────────────────────────────────────


def _load_benchfile(
    path: Path,
    files: list | None = None,
) -> list[BenchCommand]:
    """Load an external benchfile and return its ``BenchCommand`` list.

    A benchfile is an ordinary Python module that exposes ONE of:

    * ``commands(files: list[FileEntry]) -> list[BenchCommand]`` — file-aware
      factory; preferred when present so the benchfile can short-circuit
      based on which kinds are available on disk.
    * ``COMMANDS: list[BenchCommand]`` — static list, sufficient for matrices
      that only depend on placeholder substitution.

    The factory takes precedence: a file may define both, but if
    ``commands`` is callable we always call it. ``files`` may be ``None``
    when the loader runs before the directory pre-scan (e.g. when the
    pre-scan itself wants the command count); the factory should tolerate
    an empty list in that case.

    Raises ``typer.Exit(1)`` with a friendly stderr message when:
      * The path doesn't exist or isn't a ``.py`` file
      * Importing the module raises
      * Neither ``commands`` nor ``COMMANDS`` is defined
      * The result isn't a list of ``BenchCommand`` instances
    """
    if not path.exists():
        typer.echo(f"Error: --bench-file {path} not found.", err=True)
        raise typer.Exit(code=1)
    if path.suffix != ".py":
        typer.echo(
            f"Error: --bench-file must be a .py file (got {path.suffix or '<no suffix>'}).",
            err=True,
        )
        raise typer.Exit(code=1)

    module_name = f"_mm_benchfile_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        typer.echo(f"Error: could not load benchfile {path} (invalid module spec).", err=True)
        raise typer.Exit(code=1)
    module = importlib.util.module_from_spec(spec)
    # Register the module in sys.modules BEFORE exec_module so any
    # dataclass declared at module scope can resolve its `__module__`
    # via `sys.modules.get(...)` during decoration. Python 3.12+ raises
    # AttributeError otherwise.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as e:  # pragma: no cover - exercised via tests with bad files
        sys.modules.pop(module_name, None)
        typer.echo(f"Error: failed to import benchfile {path}: {e}", err=True)
        raise typer.Exit(code=1) from e

    factory = getattr(module, "commands", None)
    if callable(factory):
        try:
            commands = factory(files or [])
        except Exception as e:
            typer.echo(f"Error: benchfile {path} `commands(files)` raised: {e}", err=True)
            raise typer.Exit(code=1) from e
    elif hasattr(module, "COMMANDS"):
        commands = module.COMMANDS
    else:
        typer.echo(
            f"Error: benchfile {path} must define either "
            f"`COMMANDS: list[BenchCommand]` or `def commands(files) -> list[BenchCommand]`.",
            err=True,
        )
        raise typer.Exit(code=1)

    if not isinstance(commands, list):
        typer.echo(
            f"Error: benchfile {path} produced {type(commands).__name__}, expected a list.",
            err=True,
        )
        raise typer.Exit(code=1)
    bad = [(i, c) for i, c in enumerate(commands) if not isinstance(c, BenchCommand)]
    if bad:
        i, c = bad[0]
        typer.echo(
            f"Error: benchfile {path} entry [{i}] is {type(c).__name__}, "
            f"expected mm.commands.bench_commands.BenchCommand.",
            err=True,
        )
        raise typer.Exit(code=1)
    return commands


# ── CLI command ─────────────────────────────────────────────────────


def bench_cmd(
    directory: Annotated[Path, typer.Argument(help="Directory to benchmark")] = Path("."),
    rounds: Annotated[int, typer.Option("--rounds", "-r", help="Measurement rounds")] = 3,
    warmup: Annotated[int, typer.Option("--warmup", "-w", help="Warmup rounds")] = 1,
    mode: Annotated[
        Optional[str],
        typer.Option(
            "--mode",
            "-m",
            help="Groups to bench: metadata (default), fast, accurate, all",
        ),
    ] = None,
    command: Annotated[
        Optional[str],
        typer.Option(
            "--command",
            "-c",
            help=(
                "Substring filter on bench-command names "
                "(e.g. 'cat' to keep only `mm cat ...` benchmarks)."
            ),
        ),
    ] = None,
    group: Annotated[
        Optional[str],
        typer.Option(
            "--group",
            "-g",
            help=(
                "Filter to a single group (case-insensitive exact match on "
                "`BenchCommand.group`). Useful for scoping a benchfile run "
                "to one bucket, e.g. `--group model` or `--group cache`."
            ),
        ),
    ] = None,
    model: Annotated[
        Optional[str],
        typer.Option(
            "--model",
            help=(
                "Filter to rows whose `model` tag matches the given value "
                "(case-insensitive exact match on `BenchCommand.tags['model']`). "
                "Cuts across groups, e.g. `--model qwen3.5-0.8b` keeps every "
                "row pinned to that model regardless of its group. Combines "
                "with --group / --command via AND."
            ),
        ),
    ] = None,
    format: Annotated[
        Optional[BaseFormat],
        typer.Option("--format", "-f", help="Output format: rich, json, tsv, csv, stdout"),
    ] = None,
    timeout: Annotated[
        float,
        typer.Option(
            "--timeout",
            help="Per-command timeout in seconds (stdout snapshot mode only)",
        ),
    ] = 600.0,
    with_generate: Annotated[
        bool,
        typer.Option(
            "--with-generate",
            help=(
                "Stdout snapshot mode: include the LLM generate step in each "
                "cat invocation. Default omits it (`--no-generate`) so the "
                "snapshot is fast, deterministic, and offline-friendly."
            ),
        ),
    ] = False,
    bench_file: Annotated[
        Optional[Path],
        typer.Option(
            "--bench-file",
            "-b",
            help=(
                "Python file exposing `COMMANDS: list[BenchCommand]` or "
                "`def commands(files) -> list[BenchCommand]`. Replaces the "
                "built-in overhead+metadata+mode set entirely; --mode is "
                "ignored. --group / --model / --command filters still "
                "apply on top."
            ),
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help=(
                "Resolve the benchmark plan and render the same table with "
                "`-` placeholders, without executing any commands. Useful "
                "for inspecting an external --bench-file before running it."
            ),
        ),
    ] = False,
    host_info: Annotated[
        bool,
        typer.Option("--host-info", help="Show host system info and exit"),
    ] = False,
) -> None:
    """Benchmark all subcommands with statistical analysis.

    \b
    overhead + metadata always run; ``--mode`` picks which extraction tier joins:
      metadata (default)  overhead + metadata (Unix-comparable: find/wc/sql/grep)
      fast                overhead + metadata + fast
      accurate            overhead + metadata + accurate
      all                 overhead + metadata + fast + accurate

    \b
    ``--format stdout`` switches to *snapshot* mode: each cat-encoder
    variant runs once and its stdout is recorded between ``---`` separators
    — handy for refreshing ``tests/stdout/cat.md``.

    \b
    Filtering (combined via AND):
      --group/-g GROUP    keep rows where BenchCommand.group == GROUP
      --model MODEL       keep rows where tags['model'] == MODEL
      --command/-c TERM   keep rows where TERM is a substring of name

    \b
    ``--bench-file PATH`` loads a Python module that exposes either
    ``COMMANDS: list[BenchCommand]`` or ``def commands(files) ->
    list[BenchCommand]`` and **fully replaces** the built-in matrix.
    ``--mode`` is ignored in this mode; the benchfile's own
    ``BenchCommand.group`` drives display grouping. ``--group`` /
    ``--model`` / ``--command`` filters still apply on top.

    \b
    ``--dry-run`` resolves the plan without timing — every row renders
    with ``-`` placeholders (or ``dry_run: true`` in JSON), great for
    inspecting a new benchfile before running it.

    \b
    Examples:
      mm bench ~/data                              # overhead + metadata (default)
      mm bench ~/data --mode metadata              # Unix-comparable subset (no LLM)
      mm bench ~/data --mode accurate              # overhead + metadata + accurate
      mm bench ~/data --mode all                   # full suite
      mm bench ~/data --rounds 5                   # more rounds for stability
      mm bench ~/data --format json                # JSON output for archival
      mm bench ~/data --command cat --format stdout > tests/stdout/cat.md
      mm bench ~/data -b benchmarks/vlmgw_bench_commands.py --dry-run
      mm bench ~/data -b benchmarks/vlmgw_bench_commands.py -r 1 -w 0
      mm bench ~/data -b benchmarks/vlmgw_bench_commands.py --group cache
      mm bench ~/data -b benchmarks/vlmgw_bench_commands.py --model qwen3.5-0.8b
      mm bench ~/data -b benchmarks/vlmgw_bench_commands.py -g model --model sam3
      mm bench --host-info                         # print host spec and exit
      mm bench --host-info --format json           # host spec as JSON
    """
    from mm.commands.bench_commands import (
        ACCURATE_COMMANDS,
        FAST_COMMANDS,
        METADATA_COMMANDS,
        OVERHEAD_COMMANDS,
    )
    from mm.display import resolve_format

    fmt = resolve_format(format.value if format else None)

    if host_info:
        from mm.bench_utils import collect_host_info, render_host_info

        render_host_info(collect_host_info(), fmt=fmt)
        return

    if fmt == "stdout":
        _run_stdout_snapshot(
            directory=directory,
            mode=mode or "fast",
            command_filter=command,
            timeout_s=timeout,
            with_generate=with_generate,
        )
        return

    if bench_file is not None:
        # External benchfile fully replaces the built-in set. We pass an
        # empty `files` list to the loader because the directory pre-scan
        # happens inside `_run_benchmarks`; benchfile factories should
        # return commands keyed by `requires_kind` placeholders, which are
        # then resolved per-file inside the runner.
        commands = _load_benchfile(bench_file)
        if mode is not None:
            typer.echo(
                "Note: --mode is ignored when --bench-file is set; "
                "the benchfile's BenchCommand.group drives display grouping.",
                err=True,
            )
    else:
        bench_mode = mode or "metadata"
        if bench_mode == "metadata":
            extraction: list = []
        elif bench_mode == "fast":
            extraction = FAST_COMMANDS
        elif bench_mode == "accurate":
            extraction = ACCURATE_COMMANDS
        elif bench_mode == "all":
            extraction = FAST_COMMANDS + ACCURATE_COMMANDS
        else:
            typer.echo(
                f"Error: Unknown --mode {bench_mode!r}. "
                "Use 'metadata', 'fast', 'accurate', or 'all'.",
                err=True,
            )
            raise typer.Exit(code=1)

        commands = OVERHEAD_COMMANDS + METADATA_COMMANDS + extraction

    # Compose --group, --model, --command filters via AND. Each filter
    # narrows the surviving command set; the first one that empties it
    # raises with a flag-specific error so the user knows which one
    # was the culprit.
    if group:
        needle_g = group.lower()
        commands = [c for c in commands if c.group.lower() == needle_g]
        if not commands:
            typer.echo(f"Error: --group {group!r} matched no benchmarks.", err=True)
            raise typer.Exit(code=1)

    if model:
        needle_m = model.lower()
        commands = [c for c in commands if c.tags.get("model", "").lower() == needle_m]
        if not commands:
            typer.echo(
                f"Error: --model {model!r} matched no benchmarks "
                "(no rows declare this value in `BenchCommand.tags['model']`).",
                err=True,
            )
            raise typer.Exit(code=1)

    if command:
        needle = command.lower()
        commands = [c for c in commands if needle in c.name.lower()]
        if not commands:
            typer.echo(
                f"Error: --command {command!r} matched no benchmark names.",
                err=True,
            )
            raise typer.Exit(code=1)

    from mm.bench_utils import collect_host_info, render_host_info

    render_host_info(collect_host_info(), fmt=fmt, to_stderr=True)

    # Progress callback for rich output
    if fmt == "rich":
        from mm.display import console

        status = console.status("[dim]Starting benchmarks...[/dim]", spinner="dots")
        status.start()

        def on_progress(group: str, name: str) -> None:
            status.update(f"[dim]{group}[/dim] [bold]{name}[/bold]")

        try:
            results, target_info = _run_benchmarks(
                directory,
                rounds,
                warmup,
                on_progress,
                commands,
                dry_run=dry_run,
            )
        finally:
            status.stop()

        _render_table(results, target_info)
    elif fmt == "json":
        results, target_info = _run_benchmarks(
            directory, rounds, warmup, commands=commands, dry_run=dry_run
        )

        from mm.display import json_dumps

        output = {
            **target_info,
            "results": [r.to_dict() for r in results],
        }
        print(json_dumps(output))
    else:
        # tsv/csv fallback
        results, target_info = _run_benchmarks(
            directory, rounds, warmup, commands=commands, dry_run=dry_run
        )

        from mm.display import emit_tsv

        rows = [r.to_dict() for r in results if not r.skipped]
        emit_tsv(
            rows,
            columns=[
                "group",
                "name",
                "mean_ms",
                "std_ms",
                "min_ms",
                "max_ms",
                "speed",
                "mb_per_sec",
            ],
        )
