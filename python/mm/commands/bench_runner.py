"""Benchmark data model and timing harness.

Contains ``BenchResult`` (the per-row result type), the subprocess timing
loop, and the ``run_benchmarks`` orchestrator that drives a full suite.
"""

from __future__ import annotations

import shlex
import statistics
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from mm.commands.bench_commands import ALL_COMMANDS, BenchCommand, resolve_command


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
    # Unresolved ``cmd_template`` from the originating ``BenchCommand``;
    # surfaced so the renderer can still show *what would have run* in
    # the Command cell of skipped rows (where ``preview_lines`` is empty
    # because ``resolve_command`` returned None).
    cmd_template: str = ""
    # Plumbed through from ``BenchCommand`` for the renderer's
    # ``<img>`` / ``<vid>`` / ``<doc>`` / ``<aud>`` / ``<code>`` /
    # ``<dir>`` placeholder substitution in the Command cell.
    requires_kind: str | None = None
    # Absolute paths the harness substituted into ``{file}`` /
    # ``{files}`` placeholders -- the row's actual data inputs.
    # Renderers use this to distinguish data files (which become
    # ``<img>`` / ``<vid>`` / ... placeholders) from helper-script
    # paths or other absolute paths the template may legitimately
    # contain.
    data_file_paths: list[str] = field(default_factory=list)
    # Captured from the *last* timed round of ``_time_cmd``. Used by
    # the markdown recorder to embed the actual command output beneath
    # each row's snapshot table; intentionally NOT surfaced in
    # ``to_dict`` (would balloon JSON payloads for verbose models like
    # dots-ocr).
    last_stdout: str = ""
    last_stderr: str = ""
    returncode: int | None = None
    # ``True`` when the originating ``BenchCommand.disabled`` was set.
    # Disabled rows are rendered (dimmed) in dry-run / live tables so
    # the matrix coverage stays visible, but the harness never invokes
    # their argv. Tracked separately from ``skipped`` so the renderer
    # can apply full-row dim styling without confusing it with regular
    # ``no <kind> files`` skips.
    disabled: bool = False

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

    def _annotate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Attach optional structured fields (tags, requires_kind).

        Keeps JSON output compact: only emits keys that carry a real
        value, so the default suite (no tags, no requires_kind) stays
        identical to the pre-PR shape.
        """
        if self.tags:
            payload["tags"] = dict(self.tags)
        if self.requires_kind:
            payload["requires_kind"] = self.requires_kind
        return payload

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any]
        if self.skipped:
            payload = {
                "name": self.name,
                "group": self.group,
                "skipped": True,
                "skip_reason": self.skip_reason,
            }
            if self.disabled:
                payload["disabled"] = True
            return self._annotate(payload)
        if self.is_dry_run:
            payload = {
                "name": self.name,
                "group": self.group,
                "dry_run": True,
                "argv": list(self.preview_lines),
                "files_count": self.files_count,
                "total_bytes": self.total_bytes,
            }
            return self._annotate(payload)
        payload = {
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
        return self._annotate(payload)


def _sanitize_files(files: list) -> list:
    """Return *files* with filesystem-noise entries removed."""

    def _is_filesystem_noise(name: str) -> bool:
        return name.startswith("._") or name == ".DS_Store"

    return [f for f in files if not _is_filesystem_noise(Path(f.path).name)]


def _time_cmd(
    argv: list[str], rounds: int, warmup: int
) -> tuple[list[float], subprocess.CompletedProcess[str]]:
    """Run a shell command with warmup, return ``(timings_ms, last_proc)``.

    ``stdin`` is closed because ``mm cat`` (and friends) autodetect piped
    stdin and try to read paths from it — which deadlocks under
    ``subprocess.PIPE`` if we don't also feed something in.

    The ``CompletedProcess`` from the *final* timed round is returned so
    callers (the markdown recorder) can embed the actual command output
    in the per-row snapshot. Warmup runs continue to discard their
    output; only the last timed round's stdout/stderr are kept.
    """

    def _inject_no_cache():
        return len(argv) > 1 and argv[1] == "cat" and "--no-cache" not in argv

    argv = [*argv, "--no-cache"] if _inject_no_cache() else argv

    for _ in range(warmup):
        subprocess.run(argv, capture_output=True, stdin=subprocess.DEVNULL)

    timings: list[float] = []
    last_proc: subprocess.CompletedProcess[str] | None = None
    for _ in range(rounds):
        t0 = time.perf_counter_ns()
        last_proc = subprocess.run(argv, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        t1 = time.perf_counter_ns()
        timings.append((t1 - t0) / 1_000_000)  # ns → ms

    if last_proc is None:
        # ``rounds=0`` is a pathological edge case (no measurement, no
        # output) but keeps callers crash-free without forcing an
        # extra subprocess invocation.
        last_proc = subprocess.CompletedProcess(argv, 0, "", "")
    return timings, last_proc


def _run_benchmarks(
    directory: Path,
    rounds: int,
    warmup: int,
    on_progress: Callable[[str, str], None] | None = None,
    commands: list[BenchCommand] | None = None,
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

    def _exec_run(cmd: BenchCommand) -> BenchResult:
        if on_progress:
            on_progress(cmd.group, cmd.name)

        if cmd.disabled:
            # Render-only row: keep the matrix coverage visible (with
            # ``skipped: disabled`` in the metrics column and full-row
            # dim styling) but never invoke the argv.
            return BenchResult(
                cmd.name,
                cmd.group,
                skipped=True,
                skip_reason="disabled",
                disabled=True,
                tags=dict(cmd.tags),
                cmd_template=cmd.cmd_template,
                requires_kind=cmd.requires_kind,
            )

        if num_files == 0:
            return BenchResult(
                cmd.name,
                cmd.group,
                skipped=True,
                skip_reason="empty directory",
                tags=dict(cmd.tags),
                cmd_template=cmd.cmd_template,
                requires_kind=cmd.requires_kind,
            )

        resolved = resolve_command(cmd, directory, files)
        if resolved is None:
            return BenchResult(
                cmd.name,
                cmd.group,
                skipped=True,
                skip_reason=cmd.skip_reason,
                tags=dict(cmd.tags),
                cmd_template=cmd.cmd_template,
                requires_kind=cmd.requires_kind,
            )

        argv, fc, tb, media, data_paths = resolved

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
            cmd_template=cmd.cmd_template,
            requires_kind=cmd.requires_kind,
            data_file_paths=list(data_paths),
        )
        if not dry_run:
            timings, last_proc = _time_cmd(argv, rounds, warmup)
            r.timings_ms = timings
            r.last_stdout = last_proc.stdout or ""
            r.last_stderr = last_proc.stderr or ""
            r.returncode = last_proc.returncode

        return r

    for cmd in commands:
        result = _exec_run(cmd)
        if not result.skipped or result.disabled:
            results.append(result)

    target_info["total_wall_ms"] = (time.perf_counter_ns() - t_wall) / 1_000_000
    return results, target_info
