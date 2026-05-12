"""mm bench -- benchmark all subcommands with statistical analysis."""

from __future__ import annotations

import importlib.util
import json
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
                # Distinct from "no <kind> files" -- disabled rows are
                # an intentional opt-out (e.g. broken upstream model)
                # rather than a missing-input skip. External consumers
                # use this to filter out vs. surface failure paths.
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


# ── Pre-ops sanitization ────────────────────────────────────────────


def _sanitize_files(files: list) -> list:
    """Return *files* with filesystem-noise entries removed."""

    def _is_filesystem_noise(name: str) -> bool:
        return name.startswith("._") or name == ".DS_Store"

    return [f for f in files if not _is_filesystem_noise(Path(f.path).name)]


# ── Timing harness ──────────────────────────────────────────────────


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


# ── Benchmark runner ─────────────────────────────────────────────────


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
            # dim styling) but never invoke the argv. Short-circuits
            # before ``resolve_command`` so missing-input errors on
            # disabled rows can't accidentally mask the disable intent.
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
        results.append(_exec_run(cmd))

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


def _split_argv(joined: str) -> list[str]:
    """Best-effort ``shlex.split`` -- returns an empty list on failure."""
    try:
        return shlex.split(joined)
    except ValueError:
        return []


def _extract_flag(argv: list[str], *names: str) -> str:
    """Return the value following the first matching long flag, or ``""``.

    Accepts both ``--flag VALUE`` and ``--flag=VALUE``.
    """
    for i, a in enumerate(argv):
        for name in names:
            if a == name and i + 1 < len(argv):
                return argv[i + 1]
            if a.startswith(f"{name}="):
                return a.split("=", 1)[1]
    return ""


def _strip_flag(argv: list[str], *names: str) -> list[str]:
    """Return *argv* with the named flags (and their adjacent values) removed."""
    out: list[str] = []
    skip = False
    name_set = set(names)
    for a in argv:
        if skip:
            skip = False
            continue
        if a in name_set:
            skip = True
            continue
        if any(a.startswith(f"{n}=") for n in name_set):
            continue
        out.append(a)
    return out


def _replace_flag_value(argv: list[str], placeholder: str, *names: str) -> list[str]:
    """Replace the values following ``names`` with ``placeholder``.

    Used to templatize ``--mode accurate`` -> ``--mode <mode>`` so the
    Command cell shows the *shape* of the invocation while the actual
    value lives in its own (``Mode``) column.
    """
    out: list[str] = []
    swap = False
    name_set = set(names)
    for a in argv:
        if swap:
            out.append(placeholder)
            swap = False
            continue
        if a in name_set:
            out.append(a)
            swap = True
            continue
        eq_match = next((n for n in name_set if a.startswith(f"{n}=")), None)
        if eq_match is not None:
            out.append(f"{eq_match}={placeholder}")
            continue
        out.append(a)
    return out


_KIND_PLACEHOLDER: dict[str, str] = {
    "image": "<img>",
    "video": "<vid>",
    "audio": "<aud>",
    "document": "<doc>",
    "code": "<code>",
}


def _kind_placeholder(kind: str | None) -> str:
    """``"image"`` -> ``"<img>"``; unknown kind falls back to ``"<file>"``."""
    if not kind:
        return "<file>"
    return _KIND_PLACEHOLDER.get(kind, f"<{kind}>")


def _replace_paths(
    argv: list[str],
    file_placeholder: str,
    *,
    data_paths: set[str] | None = None,
) -> list[str]:
    """Replace abs paths and ``{file}`` / ``{files}`` / ``{dir}`` tokens.

    Substitution rules:

    * ``{file}`` / ``{files}`` template tokens (preserved on skipped
      rows where ``resolve_command`` returns None) -> *file_placeholder*.
    * ``{dir}`` -> ``<dir>``.
    * Abs path that's in *data_paths* (the row's resolved data files)
      -> *file_placeholder*.
    * Other abs paths that *exist as a file* -> ``Path(a).name``
      (basename only). This covers helper-script paths embedded in
      the cmd_template (e.g. ``benchmarks/_multi_image_call.py``) so
      the displayed Base Command stays portable across machines while
      remaining recognizable.
    * Abs paths that exist as a directory -> ``<dir>``.

    When *data_paths* is None we fall back to the legacy behaviour
    (every existing file becomes *file_placeholder*) -- preserves
    callers that don't have the resolved-paths info handy (e.g.
    skipped rows running on the unresolved ``cmd_template``).
    """
    out: list[str] = []
    for a in argv:
        if a in ("{file}", "{files}"):
            out.append(file_placeholder)
            continue
        if a == "{dir}":
            out.append("<dir>")
            continue
        if a.startswith("/"):
            if data_paths is not None and a in data_paths:
                out.append(file_placeholder)
                continue
            p = Path(a)
            if p.is_file():
                # With explicit data_paths, ``a`` is a non-data file
                # (helper script, interpreter, etc.) -- show basename.
                # Without it, fall back to legacy placeholder swap.
                if data_paths is None:
                    out.append(file_placeholder)
                else:
                    out.append(p.name)
                continue
            if p.is_dir():
                out.append("<dir>")
                continue
        out.append(a)
    return out


# Flags whose values describe the *variation* between bench rows
# (vs. the static invocation skeleton). They get pulled into the
# ``Extra Args`` column so the ``Base Command`` reads as a stable
# shell skeleton across rows.
_EXTRA_FLAG_PREFIXES: tuple[str, ...] = ("--prompt", "--generate.", "--encode.")


def _is_extra_flag(token: str) -> bool:
    return any(token.startswith(p) for p in _EXTRA_FLAG_PREFIXES)


def _split_base_extra(argv: list[str]) -> tuple[list[str], list[str]]:
    """Partition *argv* into ``(base, extra)``.

    Tokens whose flag matches ``_EXTRA_FLAG_PREFIXES`` (and the
    immediately-following value, when not already ``--flag=value``-
    bundled) move to *extra*; everything else stays in *base*. Used
    by the renderer to give variant-specific knobs (``--prompt``,
    ``--generate.*``, ``--encode.*``) their own column so the ``Base
    Command`` remains a stable shell skeleton across rows.
    """
    base: list[str] = []
    extra: list[str] = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if not _is_extra_flag(token):
            base.append(token)
            i += 1
            continue
        if "=" in token:
            extra.append(token)
            i += 1
            continue
        # ``--prompt VALUE`` form: pull the value too, but only if it
        # isn't itself another flag (defensive -- shouldn't happen for
        # well-formed bench commands but keeps the helper robust).
        extra.append(token)
        if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            extra.append(argv[i + 1])
            i += 2
        else:
            i += 1
    return base, extra


# shlex.join treats ``<`` and ``>`` as shell metacharacters and wraps
# our placeholders in single quotes (``'<img>'``). For *display* the
# quoting is just noise -- placeholders are clearly not real shell
# tokens -- so we strip the protective quotes after joining.
_PLACEHOLDER_QUOTE_RE = re.compile(r"'(<[^'>]*>)'")


def _shell_join(argv: list[str]) -> str:
    """``shlex.join`` with our display placeholders unquoted."""
    return _PLACEHOLDER_QUOTE_RE.sub(r"\1", shlex.join(argv))


def _build_command_cells(r: BenchResult) -> tuple[str, str]:
    """Render the ``(Base Command, Extra Args)`` cell pair for a row.

    Drops ``--profile`` and ``--model`` (constant-per-benchfile or
    surfaced in the ``Model`` column respectively), then partitions
    the remaining argv into *base* (the stable shell skeleton:
    ``mm cat <img> --mode accurate --no-cache --format json``) and
    *extra* (variant-specific knobs: ``--prompt``, ``--generate.*``,
    ``--encode.*``). File paths in *base* are substituted with
    kind-based placeholders (``<img>`` / ``<vid>`` / ``<doc>`` /
    ``<aud>`` / ``<code>`` / ``<dir>``). Skipped rows fall back to
    the unresolved ``cmd_template`` so the cell still describes what
    *would* have run.
    """
    joined = r.preview_lines[0] if r.preview_lines else r.cmd_template
    if not joined:
        return "", ""
    argv = _split_argv(joined)
    if not argv:
        return joined, ""
    argv = _strip_flag(argv, "--profile", "--model", "--generate.model")
    base_argv, extra_argv = _split_base_extra(argv)
    # ``data_paths`` is empty on skipped rows (we render off
    # ``cmd_template``, so abs paths haven't been substituted yet) and
    # on rows whose template carries no ``{file}`` / ``{files}``. Pass
    # ``None`` in those cases to keep the legacy single-bucket
    # behaviour; otherwise pass the resolved set so non-data abs paths
    # (helper scripts, ...) basename-out instead of being miscast as
    # the row's media kind.
    data_paths: set[str] | None = set(r.data_file_paths) if r.data_file_paths else None
    base_argv = _replace_paths(base_argv, _kind_placeholder(r.requires_kind), data_paths=data_paths)
    base_str = _shell_join(base_argv)
    extra_str = _shell_join(extra_argv) if extra_argv else ""
    return base_str, extra_str


def _build_table(
    results: list[BenchResult],
    target_info: dict[str, Any],
    *,
    include_caption: bool = True,
) -> Any:
    """Build a Rich ``Table`` for *results* and return it (no printing).

    Shared between the live ``mm bench`` renderer and the per-row
    markdown recorder so both paths stay in lockstep on column layout
    and cell content. ``include_caption`` is False for single-row
    snapshots (the recorder's own header carries the totals already, so
    repeating them on every row is noise).

    Layout: ``Group | Model | Base Command | Extra Args | <metrics>``.
    ``Model`` and ``Extra Args`` are conditional -- rendered only when
    at least one row carries a value for them -- so the default suite
    (no tags, no ``--prompt`` / ``--generate.*`` / ``--encode.*``)
    stays compact while benchfiles like ``vlmgw_bench_commands.py``
    get the fully split layout.

    The ``Base Command`` cell holds the stable shell skeleton
    (``mm cat <img> --mode fast --no-cache --format json``) with
    ``--profile`` / ``--model`` stripped (the profile is constant per
    benchfile run; the model lives in its own column) and file paths
    substituted with kind-based placeholders (``<img>`` / ``<vid>`` /
    ``<doc>`` / ``<aud>`` / ``<code>`` / ``<dir>``). The ``Extra
    Args`` cell holds the variant-specific knobs (``--prompt``,
    ``--generate.*``, ``--encode.*``) -- splitting them off from the
    base lets the eye land on the actual variation between rows.
    """
    from rich import box
    from rich.table import Table
    from rich.text import Text

    from mm.display import format_size

    is_dry_run = bool(target_info.get("dry_run"))
    caption: str | None = None
    if include_caption:
        wall_ms = target_info.get("total_wall_ms", 0)
        wall_str = _fmt_ms(wall_ms) if wall_ms else "—"
        caption = (
            f"{target_info['files']:,} files  "
            f"{format_size(target_info['total_bytes'])}  "
            f"rounds={target_info['rounds']}  warmup={target_info['warmup']}  "
            f"total={wall_str}"
        )
        if is_dry_run:
            caption += "  (dry run — no commands executed)"

    # Pre-compute (base, extra) for every row so we can decide which
    # columns to render based on actual content.
    cmd_cells: list[tuple[str, str]] = [_build_command_cells(r) for r in results]
    has_model = any(r.tags.get("model") for r in results)
    has_task = any(r.tags.get("task") for r in results)
    has_extra = any(extra for _base, extra in cmd_cells)

    table = Table(
        caption=caption,
        caption_style="dim",
        caption_justify="right",
        show_header=True,
        header_style="bold",
        padding=(0, 1),
        box=box.ROUNDED,
    )
    table.add_column("Group", width=10)
    if has_model:
        # ``Model`` carries identifiers like ``microsoft/Florence-2-base-ft``
        # which we want to keep visible in full -- folding rather than
        # truncating preserves the org/name namespace structure.
        table.add_column("Model", no_wrap=False, overflow="fold")
    if has_task:
        # ``Task`` is a short closed-taxonomy label (``cap`` / ``ocr`` /
        # ``det`` / ``seg`` / ``llm`` / ``pose`` / ``track`` / ``noop``)
        # so a fixed narrow column keeps it visually compact and the
        # values left-aligned for grep-ability across rows.
        table.add_column("Task", width=5)
    # Base / Extra both wrap so long invocations stay visible.
    table.add_column("Base Command", no_wrap=False, overflow="fold")
    if has_extra:
        table.add_column("Extra Args", no_wrap=False, overflow="fold")
    table.add_column("Mean", justify="right")
    table.add_column("\u00b1Std", justify="right")
    table.add_column("Min", justify="right")
    table.add_column("Max", justify="right")
    table.add_column("Speed", justify="right")
    table.add_column("MB/s", justify="right")
    table.add_column("bps", justify="right")

    prev_group = None
    for r, (base_str, extra_str) in zip(results, cmd_cells, strict=True):
        # Add section separator between groups.
        if prev_group is not None and r.group != prev_group:
            table.add_section()
        prev_group = r.group

        # Build the conditional-cell prefix in the same column order as
        # the column declarations above so the row-vs-header alignment
        # stays in sync regardless of which columns are active.
        prefix: list[Any] = [r.group]
        if has_model:
            prefix.append(r.tags.get("model", ""))
        if has_task:
            prefix.append(r.tags.get("task", ""))

        if r.skipped:
            # Show the (possibly empty) base + extra cells, then a dim
            # ``[skipped: <reason>]`` trailer in the metrics column;
            # remaining metric cells stay blank. Disabled rows ride
            # the same skipped path but get full-row dim styling so
            # the eye can quickly distinguish "intentionally muted"
            # from "no files of this kind in the bench dir".
            command_cells: list[Any] = [base_str or r.name]
            if has_extra:
                command_cells.append(extra_str)
            row_style = "dim" if r.disabled else None
            table.add_row(
                *prefix,
                *command_cells,
                Text(f"skipped: {r.skip_reason}", style="dim italic"),
                *([""] * 6),
                style=row_style,
            )
            continue

        if r.is_dry_run:
            placeholder = Text("-", style="dim")
            command_cells = [base_str]
            if has_extra:
                command_cells.append(extra_str)
            table.add_row(
                *prefix,
                *command_cells,
                *([placeholder] * 7),
            )
            continue

        color = _latency_style(r.mean_ms, r.group)
        command_cells = [base_str]
        if has_extra:
            command_cells.append(extra_str)
        table.add_row(
            *prefix,
            *command_cells,
            Text(_fmt_ms(r.mean_ms), style=f"bold {color}"),
            Text(_fmt_ms(r.std_ms)),
            Text(_fmt_ms(r.min_ms), style=color),
            Text(_fmt_ms(r.max_ms), style=color),
            Text(r.speed_str),
            Text(f"{r.mb_per_sec:.1f}" if r.mb_per_sec > 0 else "\u2014"),
            Text(r.bits_per_sec_str) if r.bits_per_sec > 0 else Text("\u2014"),
        )

    return table


def _render_table(results: list[BenchResult], target_info: dict[str, Any]) -> None:
    """Render all results as a single Rich table to ``output_console``."""
    from mm.display import output_console

    output_console.print(_build_table(results, target_info, include_caption=True))


# ── Markdown recording ──────────────────────────────────────────────


def _derive_recording_stem(profile_name: str | None) -> str:
    """Return the ``<profile>`` portion of the recording filename.

    Earlier iterations derived this from the ``--bench-file`` path
    (``benchmarks/vlmgw_bench_commands.py`` -> ``vlmgw``), but the
    profile name is what actually identifies the gateway / model
    surface the bench is hitting -- multiple benchfiles can target
    the same profile, and the same benchfile can be re-run against
    different profiles. Pinning the stem to the active profile
    keeps recordings grouped by deployment, not by author intent.
    """
    if not profile_name:
        return "default"
    # ``/`` and other path separators in profile names would punch
    # subdirectories into the recording path; normalize them out so
    # ``"a/b"`` lands at ``benchmarks/results/<date>-mm-bench-a-b-<HHMM>.md``
    # rather than ``benchmarks/results/<date>-mm-bench-a/b-<HHMM>.md``.
    safe = profile_name.replace("/", "-").replace("\\", "-")
    return safe or "default"


def _derive_recording_path(profile_name: str | None, *, root: Path | None = None) -> Path:
    """Return the markdown recording path for the active *profile_name*.

    Defaults to
    ``<cwd>/benchmarks/results/<YYMMDD>-mm-bench-<profile>-<HHMM>.md``.

    Layout rationale:

    * ``benchmarks/`` (plural) keeps the input source-of-truth --
      ``vlmgw_bench_commands.py``, ``bench_cli*.sh``, etc.
    * ``benchmarks/results/`` collects every auto-recording so a
      ``rm -rf benchmarks/results/`` only nukes generated artefacts
      and never the author-curated inputs.

    Filename rationale:

    * ``<YYMMDD>`` keeps day-level clustering for grep / archive.
    * ``<HHMM>`` (24-hour) suffix gives minute-level uniqueness so two
      runs against the same profile on the same day don't overwrite
      each other -- previously the recorder was idempotent per day,
      which was useful for "single canonical snapshot" but lossy when
      iterating on a benchfile through several runs.

    ``root`` overrides the base directory (used by tests so they can
    target a pytest tmp dir without ``monkeypatch.chdir``).
    """
    import datetime as _dt

    now = _dt.datetime.now()
    date = now.strftime("%y%m%d")
    time = now.strftime("%H%M")
    base = root if root is not None else Path("benchmarks/results")
    stem = _derive_recording_stem(profile_name)
    return base / f"{date}-mm-bench-{stem}-{time}.md"


def _stdout_fence_lang(stdout: str) -> str:
    """Pick a markdown code-fence language for *stdout*.

    Uses ``json`` for anything that *looks* JSON (leading ``{`` / ``[``
    after stripping whitespace) so renderers get syntax highlighting,
    and falls back to plain ``text`` otherwise.
    """
    s = stdout.lstrip()
    if s.startswith(("{", "[")):
        return "json"
    return "text"


def _extract_cat_content(stdout: str) -> tuple[str, str] | None:
    """Extract the ``content`` payload from ``mm cat --format json`` stdout.

    The bench harness invokes ``mm cat ... --format json`` and captures
    its stdout. The raw envelope looks like::

        [{"path": "<abs>", "mode": "<mode>", "content": "<actual output>"}]
        <perf-footer line, e.g. "1.7s • 38.2 KB • 22.9 KB/s">

    For the markdown recording we want the **content** only -- the
    ``path`` / ``mode`` keys are noise (they're already in the row's
    Rich table + ``args:`` line), and the trailing perf-footer line is
    a `mm cat` ``display_elapsed`` artifact that leaks into stdout
    because it's printed via ``output_console`` rather than stderr.

    Returns:

    * ``(pretty_body, "json")`` when we successfully extract a JSON
      payload (single content as JSON object/array, or multi-image as
      a JSON array of content values).
    * ``(text_body, "text")`` when the single extracted content is a
      plain string.
    * ``None`` when *stdout* doesn't look like a ``mm cat --format
      json`` envelope -- caller falls back to the raw stdout pipeline.

    Multi-content (``mm cat <f1> <f2>``) renders as a JSON array of
    parsed contents so the per-row block stays one cohesive code
    fence rather than a sequence of un-delimited blocks.
    """
    import json

    s = stdout.lstrip()
    if not s.startswith(("[", "{")):
        return None

    try:
        decoder = json.JSONDecoder()
        obj, _end = decoder.raw_decode(s)
    except json.JSONDecodeError:
        # Not a JSON envelope at all -- could be a model that returned
        # non-JSON to a ``--format json`` request, or a CLI error
        # before the envelope was assembled. Leave it to the caller.
        return None

    # We only know how to massage the ``mm cat`` envelope shape:
    # a non-empty list of dicts each carrying a ``content`` field.
    # Anything else (a top-level dict, an empty list, a list of
    # primitives, ...) flows through unchanged so we don't surprise
    # callers with unexpected reshaping.
    if not isinstance(obj, list) or not obj:
        return None
    if not all(isinstance(e, dict) and "content" in e for e in obj):
        return None

    contents: list[Any] = []
    for entry in obj:
        raw = entry.get("content")
        if isinstance(raw, str):
            stripped = raw.strip()
            if stripped.startswith(("{", "[")):
                # Some encoders / pipelines return JSON-as-string
                # (florence2's ``"{\"<CAPTION>\": ...}"`` shape, dots-
                # ocr's layout dumps, etc.). Parse so the recording
                # pretty-prints the structured payload rather than a
                # single line of escaped quotes.
                try:
                    contents.append(json.loads(stripped))
                    continue
                except json.JSONDecodeError:
                    pass
        contents.append(raw)

    if len(contents) == 1:
        c = contents[0]
        if isinstance(c, (dict, list)):
            return json.dumps(c, indent=2, ensure_ascii=False), "json"
        # Plain-text caption / OCR string. No JSON fence -- the
        # markdown renderer would syntax-highlight a multi-paragraph
        # caption as if it were JSON, which looks worse than a plain
        # ``text`` block.
        return str(c), "text"

    # Multi-entry: fold into a JSON array of contents. Even when
    # every content is a plain string, JSON keeps each one quoted
    # and separated by a comma -- which is far more diff-friendly
    # than concatenating raw strings.
    return json.dumps(contents, indent=2, ensure_ascii=False), "json"


def _normalize_stdout_paths(argv_str: str, stdout: str) -> str:
    """Replace absolute file paths from *argv_str* with basenames in *stdout*.

    Mirrors the path-normalization in :func:`_run_stdout_snapshot` so
    the recorded markdown stays stable across machines: absolute paths
    in shell command arguments are surfaced as basenames in both the
    snapshot tables (already handled by ``_replace_paths``) and in
    captured stdout (handled here).
    """
    if not stdout or not argv_str:
        return stdout
    try:
        argv = shlex.split(argv_str)
    except ValueError:
        return stdout
    for tok in argv:
        if not tok.startswith("/") or "/" not in tok:
            continue
        try:
            if Path(tok).is_file():
                stdout = stdout.replace(tok, Path(tok).name)
        except OSError:
            continue
    return stdout


# Per-row stdout cap for the markdown recorder. Sized so a full
# benchfile suite (~30 active rows) stays under the typical pre-commit
# ``check-added-large-files`` 100 KB threshold while still preserving
# the leading JSON / text shape of the model's response. Verbose
# captions, OCR dumps, and similar are truncated with an explicit
# ``... [N bytes truncated]`` marker so the trim is auditable.
_MAX_RECORDING_STDOUT_BYTES = 1024


def _truncate_recording_stdout(body: str) -> str:
    """Cap *body* at ``_MAX_RECORDING_STDOUT_BYTES`` and annotate the trim.

    Long model outputs (e.g. moondream2 captions, dots-ocr layout
    dumps) routinely run 4-8 KB per call, so a full benchfile run can
    blow past pre-commit's 100 KB new-file cap on the recording. Cap
    each row's stdout block at a fixed byte budget; rows that fit
    pass through unchanged.
    """
    encoded = body.encode("utf-8")
    if len(encoded) <= _MAX_RECORDING_STDOUT_BYTES:
        return body
    truncated_bytes = len(encoded) - _MAX_RECORDING_STDOUT_BYTES
    head = encoded[:_MAX_RECORDING_STDOUT_BYTES].decode("utf-8", errors="ignore").rstrip()
    return f"{head}\n... [{truncated_bytes:,} bytes truncated]"


def _format_recording_output(r: BenchResult, argv_str: str) -> tuple[str, str]:
    """Return ``(body, fence_language)`` for one row's stdout block.

    Branches on row state:

    * skipped -> ``[skipped: <reason>]`` in a ``text`` block.
    * non-zero exit -> ``[exit N]`` followed by the last 5 stderr lines.
    * empty stdout -> ``(no output)``.
    * looks like ``mm cat --format json`` envelope -> extract the
      ``content`` payload, drop ``path`` / ``mode``, drop the trailing
      perf-summary line, pretty-print structured content (JSON) or
      pass-through text content. This is what most workload rows hit.
    * everything else -> ANSI-stripped + path-normalized stdout, with
      ``json`` fence when the output starts with ``{`` / ``[`` and
      ``text`` otherwise.

    All non-skip branches end in ``_truncate_recording_stdout`` so a
    single chatty model can't blow the per-row recording budget.
    """
    if r.skipped:
        return f"[skipped: {r.skip_reason}]", "text"

    if (r.returncode or 0) != 0:
        rc = r.returncode if r.returncode is not None else "?"
        err_lines = (r.last_stderr or "").rstrip().splitlines()[-5:]
        err = "\n".join(err_lines) if err_lines else "(no stderr)"
        return f"[exit {rc}]\n{err}", "text"

    body = _strip_ansi(r.last_stdout or "").rstrip()
    body = _normalize_stdout_paths(argv_str, body)
    if not body:
        return "(no output)", "text"

    extracted = _extract_cat_content(body)
    if extracted is not None:
        # Path normalization runs again on the extracted body so any
        # paths embedded inside the model's content (rare but
        # possible -- e.g. a model that echoes the input filename)
        # still get reduced to basenames.
        ebody, lang = extracted
        ebody = _normalize_stdout_paths(argv_str, ebody)
        return _truncate_recording_stdout(ebody), lang

    lang = _stdout_fence_lang(body)
    body = _truncate_recording_stdout(body)
    return body, lang


# Short keys for the per-row ``args:`` line. ``image`` -> ``"img"``
# matches the kind placeholders the Base Command cell uses
# (``<img>``, ``<vid>``, ...) so the eye can correlate the abstract
# placeholder back to its resolved value.
_ARGS_KIND_KEY: dict[str, str] = {
    "image": "img",
    "video": "vid",
    "audio": "aud",
    "document": "doc",
    "code": "code",
}


def _build_args_line(r: BenchResult, argv: list[str]) -> str:
    """One-line JSON summary of the row's resolved data inputs + mode.

    Surfaces the values the table itself can't show -- the
    ``<img>`` / ``<vid>`` / ... placeholders in the Base Command
    collapse N data files down to one symbol; this line restores the
    actual basenames so the recording stays diffable across runs that
    pick different files. ``mode`` is included when the row uses
    ``--mode <X>`` because it's a primary axis of the bench matrix
    (metadata / fast / accurate) even though the same value also
    appears in the Base Command column.
    """
    args: dict[str, Any] = {}

    if r.data_file_paths:
        key = _ARGS_KIND_KEY.get(r.requires_kind or "", r.requires_kind or "file")
        names = [Path(p).name for p in r.data_file_paths]
        args[key] = names[0] if len(names) == 1 else names

    mode = _extract_flag(argv, "--mode") if argv else ""
    if mode:
        args["mode"] = mode

    return f"args: {json.dumps(args)}" if args else ""


def _fmt_size(n: float) -> str:
    """Compact byte formatter (KB / MB / GB)."""
    n = float(n)
    if n >= 1024**3:
        return f"{n / 1024**3:.1f} GB"
    if n >= 1024**2:
        return f"{n / 1024**2:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n:.0f} B"


def _build_footer_line(r: BenchResult) -> str:
    """``<elapsed> • <bytes> • <bytes/s>`` summary for the captured round.

    Uses the LAST round's timing (the one that produced the captured
    stdout) rather than the mean -- the line is "this particular
    invocation took X to produce that stdout", complementing the
    aggregate stats already shown in the row table above.
    """
    if not r.timings_ms:
        return ""
    last_ms = r.timings_ms[-1]
    parts = [_fmt_ms(last_ms)]
    if r.total_bytes > 0:
        parts.append(_fmt_size(r.total_bytes))
        if last_ms > 0:
            parts.append(f"{_fmt_size(r.total_bytes / (last_ms / 1000))}/s")
    return " • ".join(parts)


def _render_row_table_text(r: BenchResult, target_info: dict[str, Any], *, width: int = 240) -> str:
    """Render a single-row Rich Table as plain text (ANSI stripped).

    Uses ``Console.capture()`` so nothing is written to stdout. The
    fixed ``width=240`` matches the typical ``COLUMNS`` we use for
    bench rendering elsewhere (see tests setting
    ``monkeypatch.setenv('COLUMNS', '260')``); narrower widths would
    fold long base-command / extra-args cells across multiple lines
    in the recorded markdown.
    """
    from rich.console import Console

    console = Console(width=width, no_color=True, force_terminal=False)
    with console.capture() as cap:
        console.print(_build_table([r], target_info, include_caption=False))
    return cap.get().rstrip("\n")


def _format_host_oneline(host_info: dict[str, Any]) -> str:
    """One-line summary of the host entry for the recording header."""
    parts: list[str] = []
    if host_info.get("hostname"):
        parts.append(f"`{host_info['hostname']}`")
    cpu = host_info.get("cpu")
    if cpu:
        threads = host_info.get("cpu_threads")
        parts.append(f"{cpu} ({threads} threads)" if threads else cpu)
    if host_info.get("os"):
        parts.append(host_info["os"])
    if host_info.get("python"):
        parts.append(f"Python {host_info['python']}")
    if host_info.get("mm_version"):
        parts.append(f"mm v{host_info['mm_version']}")
    return " · ".join(parts)


def _write_bench_recording(
    results: list[BenchResult],
    target_info: dict[str, Any],
    host_info: dict[str, Any],
    bench_file: Path | None,
    *,
    root: Path | None = None,
) -> Path:
    """Write per-row Rich-table snapshots + captured stdout to markdown.

    Returns the resolved output path --
    ``benchmarks/results/<YYMMDD>-mm-bench-<profile>-<HHMM>.md`` (one
    snapshot per profile per *minute*; the ``HHMM`` suffix gives
    same-day re-runs unique filenames so iteration history isn't lost
    to overwrite). The caller decides whether to invoke this based on
    flags (``--dry-run`` / ``--host-info`` / ``--format stdout`` all
    skip). ``bench_file`` is forwarded purely so the header line can
    cite the originating benchfile when one was passed.
    """
    import datetime as _dt

    from mm.display import format_size

    profile_name = (host_info.get("profile") or {}).get("name")
    path = _derive_recording_path(profile_name, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)

    stem = _derive_recording_stem(profile_name)
    today = _dt.datetime.now().strftime("%Y-%m-%d")

    lines: list[str] = []
    lines.append(f"# mm bench recording — {stem} — {today}")
    lines.append("")

    rounds = target_info.get("rounds", "?")
    warmup = target_info.get("warmup", "?")
    files = target_info.get("files", "?")
    total_bytes = target_info.get("total_bytes", 0)
    wall_ms = target_info.get("total_wall_ms", 0)
    files_str = f"{files:,}" if isinstance(files, int) else str(files)
    lines.append(
        f"Run: `mm bench` against `{target_info.get('directory', '?')}` "
        f"(rounds={rounds}, warmup={warmup}, "
        f"{files_str} files / {format_size(total_bytes)}, "
        f"wall={_fmt_ms(wall_ms) if wall_ms else '—'})."
    )
    if bench_file is not None:
        lines.append(f"Benchfile: `{bench_file}`.")

    host_line = _format_host_oneline(host_info)
    if host_line:
        lines.append(f"Host: {host_line}.")

    prof = host_info.get("profile") or {}
    if prof.get("name"):
        lines.append(
            f"Profile: `{prof['name']}` "
            f"(`{prof.get('base_url', '?')}`, default model `{prof.get('model', '?')}`)."
        )

    # Disabled rows are render-only (visible in the live --dry-run /
    # rich table for matrix-coverage purposes) and carry no captured
    # stdout, no timing data, and no actionable diagnostics. Listing
    # them in a compact roll-up keeps the recording focused on rows
    # that actually executed while still acknowledging the disabled
    # surface area; per-row table snapshots would balloon the file
    # past pre-commit's new-file size cap on bigger suites.
    disabled = [r for r in results if r.disabled]
    active = [r for r in results if not r.disabled]
    if disabled:
        lines.append("")
        lines.append(f"## Disabled ({len(disabled)})")
        lines.append("")
        for r in disabled:
            # Bench-command names are typically already namespaced
            # (e.g. ``noop/ping`` lives in ``group="noop"``). Avoid
            # duplicating the prefix when the name already starts
            # with ``<group>/``.
            label = (
                r.name
                if r.name.startswith(f"{r.group}/") or "/" in r.name
                else f"{r.group}/{r.name}"
            )
            tag = r.tags.get("model")
            suffix = f" — `{tag}`" if tag else ""
            lines.append(f"- `{label}`{suffix}")

    lines.append("")
    lines.append("---")
    lines.append("")

    for r in active:
        # Per-row layout:
        #   <rich table verbatim, no fence>
        #   args: {"img": "...", "mode": "fast"}     (when applicable)
        #   ```json|text
        #   <captured stdout, truncated at _MAX_RECORDING_STDOUT_BYTES>
        #   ```
        #   <elapsed> • <bytes> • <bytes/s>          (real runs only)
        #
        # The table is emitted as raw markdown content (not inside a
        # ```text``` fence) so renderers display its rich box-drawing
        # characters directly -- matching the live ``mm bench`` view.
        table_text = _render_row_table_text(r, target_info)
        lines.append(table_text)

        argv_str = r.preview_lines[0] if r.preview_lines else ""
        argv = _split_argv(argv_str) if argv_str else []
        args_line = _build_args_line(r, argv)
        if args_line:
            lines.append(args_line)

        body, lang = _format_recording_output(r, argv_str)
        lines.append(f"```{lang}")
        lines.append(body)
        lines.append("```")

        footer = _build_footer_line(r)
        if footer:
            lines.append(footer)
        lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n")
    return path


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

        argv, _, _, _, _ = resolved
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
                "with --group / --task / --command via AND."
            ),
        ),
    ] = None,
    task: Annotated[
        Optional[str],
        typer.Option(
            "--task",
            help=(
                "Filter to rows whose `task` tag matches the given value "
                "(case-insensitive exact match on `BenchCommand.tags['task']`). "
                "Conventional values: `cap`, `ocr`, `det`, `seg`, `llm`, "
                "`pose`, `track`, `noop`. Cuts across groups and models, "
                "e.g. `--task ocr` keeps every OCR row regardless of which "
                "model it pins. Combines with --group / --model / --command "
                "via AND."
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
                "ignored. --group / --model / --task / --command filters "
                "still apply on top."
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
      --task TASK         keep rows where tags['task'] == TASK
                          (cap / ocr / det / seg / llm / pose / track / noop)
      --command/-c TERM   keep rows where TERM is a substring of name

    \b
    ``--bench-file PATH`` loads a Python module that exposes either
    ``COMMANDS: list[BenchCommand]`` or ``def commands(files) ->
    list[BenchCommand]`` and **fully replaces** the built-in matrix.
    ``--mode`` is ignored in this mode; the benchfile's own
    ``BenchCommand.group`` drives display grouping. ``--group`` /
    ``--model`` / ``--task`` / ``--command`` filters still apply on
    top.

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
      mm bench ~/data -b benchmarks/vlmgw_bench_commands.py --model qwen/qwen3.5-0.8b
      mm bench ~/data -b benchmarks/vlmgw_bench_commands.py -g model --model facebook/sam3
      mm bench ~/data -b benchmarks/vlmgw_bench_commands.py --task ocr
      mm bench ~/data -b benchmarks/vlmgw_bench_commands.py --task cap --model qwen/qwen3.5-0.8b
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

    if task:
        needle_t = task.lower()
        commands = [c for c in commands if c.tags.get("task", "").lower() == needle_t]
        if not commands:
            typer.echo(
                f"Error: --task {task!r} matched no benchmarks "
                "(no rows declare this value in `BenchCommand.tags['task']`). "
                "Conventional values: cap, ocr, det, seg, llm, pose, track, noop.",
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

    host_info_data = collect_host_info()
    render_host_info(host_info_data, fmt=fmt, to_stderr=True)

    # Progress callback for rich output
    if fmt == "rich":
        from mm.display import console

        status = console.status("Starting benchmarks...", spinner="dots")
        status.start()

        def on_progress(group: str, name: str) -> None:
            status.update(f"{group} [bold]{name}[/bold]")

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

    # Markdown recording: always-on for real (non-dry-run) measurement
    # runs. Skipped via early returns above for ``--host-info`` and
    # ``--format stdout`` (snapshot mode); skipped here for
    # ``--dry-run`` because there's nothing meaningful to record yet.
    if not dry_run and results:
        try:
            recording_path = _write_bench_recording(
                results, target_info, host_info_data, bench_file
            )
            typer.echo(f"Wrote recording to {recording_path}", err=True)
        except OSError as exc:
            # Don't fail the whole run on a recording-write error -- the
            # primary output (rich/json/tsv) has already been emitted
            # and is what the user came for. Surface the failure on
            # stderr so it's still visible.
            typer.echo(f"Warning: failed to write bench recording: {exc}", err=True)
