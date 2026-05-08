"""Benchmark command definitions for mm bench.

Each benchmark is a declarative shell command template. The runner resolves
placeholders ({dir}, {file}, {files}) from a pre-scan, then executes via
subprocess for true end-to-end measurement.

Add new benchmarks by appending to METADATA_COMMANDS, FAST_COMMANDS, or
ACCURATE_COMMANDS.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mm.context import FileEntry


@dataclass
class BenchCommand:
    """A single benchmark as a shell command template.

    Placeholders:
        {dir}    — resolved absolute directory path
        {file}   — single file picked by ``requires_kind``
        {files}  — space-separated list of files (batch commands)

    Attributes:
        name:          Display name shown in output.
        group:         Grouping label (``metadata``, ``fast``, ``accurate``).
        cmd_template:  Shell command with placeholders.
        requires_kind: File kind needed for {file}/{files}. None = directory-only.
        batch:         Number of files for {files} (0 = single {file}).
        smallest:      If True, pick the smallest file of requires_kind.
        skip_reason:   Reason shown when skipped.
        tags:          Free-form ``{key: value}`` annotations surfaced as
                       extra columns in the rich table (and a ``tags``
                       field in JSON output) when any row in the run
                       declares them. The renderer collects the union of
                       keys across all rows in first-seen order, so
                       benchfile authors control the column ordering by
                       defining tags in the order they want displayed.

                       Two keys are first-class: ``model`` and ``task``.
                       Both render as their own dedicated columns
                       (``Model`` immediately after ``Group``, ``Task``
                       immediately after ``Model``) and both are
                       filterable via the ``--model`` / ``--task`` CLI
                       flags. ``task`` is conventionally one of
                       ``cap``, ``ocr``, ``det``, ``seg``, ``llm``,
                       ``pose``, ``track``, or ``noop`` -- a closed
                       taxonomy describing what the row exercises:
                       captioning, OCR, detection, segmentation,
                       text-only LLM, pose estimation, tracking, or
                       passthrough/round-trip cost. Other tag keys
                       still flow through to JSON output but don't
                       participate in column rendering or filtering.
        disabled:      When True, the row appears in the rendered table
                       (dimmed, with ``skipped: disabled`` in the metrics
                       column) but the harness never invokes its argv.
                       Use to keep declarative coverage of variants whose
                       upstream dependency is currently broken without
                       polluting timing data; flip back to False once the
                       deployment is healthy again.
    """

    name: str
    group: str
    cmd_template: str
    requires_kind: str | None = None
    batch: int = 0
    smallest: bool = False
    skip_reason: str = "not applicable"
    tags: dict[str, str] = field(default_factory=dict)
    disabled: bool = False


# ── Resolution ─────────────────────────────────────────────────────


def _pick_file(files: list[FileEntry], kind: str) -> str | None:
    """Pick the first file matching kind."""
    for f in files:
        if f.kind == kind:
            return f.path
    return None


def _pick_smallest(files: list[FileEntry], kind: str, directory: Path) -> str | None:
    """Pick the smallest file of kind (by file size)."""
    candidates = [f for f in files if f.kind == kind]
    if not candidates:
        return None
    candidates.sort(
        key=lambda f: (
            (directory.resolve() / f.path).stat().st_size
            if (directory.resolve() / f.path).exists()
            else float("inf")
        )
    )
    return candidates[0].path


def _pick_files(files: list[FileEntry], kind: str, limit: int) -> list[str]:
    """Pick up to limit files matching kind."""
    return [f.path for f in files if f.kind == kind][:limit]


@dataclass
class MediaInfo:
    """Media properties extracted via fast extraction for throughput calculations.

    ``pixel_bits`` is the total uncompressed raw-pixel bit count for the
    benchmark target — ``W*H*24`` for a single image, ``W*H*24*fps*duration``
    for video, and the **sum** over all picked files in a batch. It gives a
    consistent throughput metric independent of compression ratio, so batch
    and single-file image benchmarks can be compared directly.
    """

    duration_s: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    pixel_bits: float = 0.0


def _get_media_info(directory: Path, rel_path: str) -> MediaInfo:
    """Get media properties via Rust fast extraction."""
    try:
        from mm._mm import Scanner

        scanner = Scanner(str(directory.resolve()))
        scanner.scan()
        r = scanner.extract_metadata(rel_path)
        w, h = 0, 0
        if r.dimensions:
            parts = r.dimensions.split("x")
            if len(parts) == 2:
                w, h = int(parts[0]), int(parts[1])

        duration = r.duration_s or 0.0
        fps = r.fps or 0.0
        if w > 0 and h > 0:
            base = float(w * h * 24)
            pixel_bits = base * fps * duration if (duration > 0 and fps > 0) else base
        else:
            pixel_bits = 0.0
        return MediaInfo(
            duration_s=duration,
            width=w,
            height=h,
            fps=fps,
            pixel_bits=pixel_bits,
        )
    except Exception:
        return MediaInfo()


_MEDIA_KINDS = frozenset(("video", "audio", "image"))


def resolve_command(
    cmd: BenchCommand,
    directory: Path,
    files: list[FileEntry],
) -> tuple[list[str], int, int, MediaInfo, list[str]] | None:
    """Resolve a command template into ``(argv, files_count, total_bytes, media_info, data_file_paths)``.

    The fifth element is the absolute paths the harness substituted
    into ``{file}`` / ``{files}`` placeholders -- i.e. the row's
    actual data inputs. Renderers use this to distinguish data-file
    paths (which become ``<img>`` / ``<vid>`` / ... placeholders in
    the displayed Base Command) from any other absolute paths the
    template may legitimately contain (helper script paths,
    interpreter paths, ...).

    Returns None if the command should be skipped (missing files).
    """
    resolved_dir = str(directory.resolve())
    template = cmd.cmd_template
    media = MediaInfo()
    data_file_paths: list[str] = []

    if cmd.requires_kind is not None:
        # Check kind exists (for skip logic even on directory-level commands)
        if not any(f.kind == cmd.requires_kind for f in files):
            return None

        if cmd.batch > 0 and "{files}" in template:
            picked = _pick_files(files, cmd.requires_kind, cmd.batch)
            abs_paths = [str(directory.resolve() / p) for p in picked]
            data_file_paths = list(abs_paths)
            template = template.replace("{files}", " ".join(shlex.quote(p) for p in abs_paths))
            count = len(picked)
            total = sum(
                (directory.resolve() / p).stat().st_size
                for p in picked
                if (directory.resolve() / p).exists()
            )
            # Accumulate pixel_bits across the batch so the throughput metric
            # matches the single-file semantics (raw uncompressed bits / sec).
            if cmd.requires_kind in _MEDIA_KINDS:
                total_pixel_bits = 0.0
                for p in picked:
                    info = _get_media_info(directory, p)
                    total_pixel_bits += info.pixel_bits
                if total_pixel_bits > 0:
                    media = MediaInfo(pixel_bits=total_pixel_bits)
        elif "{file}" in template:
            if cmd.smallest:
                picked_one = _pick_smallest(files, cmd.requires_kind, directory)
            else:
                picked_one = _pick_file(files, cmd.requires_kind)
            if not picked_one:
                return None
            abs_path = str(directory.resolve() / picked_one)
            data_file_paths = [abs_path]
            template = template.replace("{file}", shlex.quote(abs_path))
            count = 1
            total = (
                (directory.resolve() / picked_one).stat().st_size
                if (directory.resolve() / picked_one).exists()
                else 0
            )
            if cmd.requires_kind in _MEDIA_KINDS:
                media = _get_media_info(directory, picked_one)
        else:
            # Directory-level command with requires_kind just for skip logic
            count = len(files)
            total = sum(
                (directory.resolve() / f.path).stat().st_size
                for f in files
                if (directory.resolve() / f.path).exists()
            )
    else:
        if "{dir}" in template:
            count = len(files)
            total = sum(
                (directory.resolve() / f.path).stat().st_size
                for f in files
                if (directory.resolve() / f.path).exists()
            )
        else:
            count = 0
            total = 0

    template = template.replace("{dir}", shlex.quote(resolved_dir))
    argv = shlex.split(template)
    return argv, count, total, media, data_file_paths


# ── Command registries ──────────────────────────────────────────────

OVERHEAD_COMMANDS: list[BenchCommand] = [
    BenchCommand("python -c 'import mm'", "overhead", "python -c 'import mm'"),
    BenchCommand("mm --help", "overhead", "mm --help"),
    BenchCommand("mm --version", "overhead", "mm --version"),
]

METADATA_COMMANDS: list[BenchCommand] = [
    BenchCommand("mm find .", "metadata", "mm find {dir} --format json"),
    BenchCommand("mm find . (table)", "metadata", "mm find {dir} --format tsv"),
    BenchCommand("mm wc .", "metadata", "mm wc {dir} --format json"),
    BenchCommand(
        "mm sql 'GROUP BY kind'",
        "metadata",
        "mm sql 'SELECT kind, COUNT(*) as n FROM files GROUP BY kind' --dir {dir} --format json",
    ),
    BenchCommand(
        "mm sql 'SUM(size) BY kind'",
        "metadata",
        "mm sql 'SELECT kind, COUNT(*) as n, SUM(size) as total_bytes, ROUND(AVG(size)) as avg_bytes FROM files GROUP BY kind ORDER BY total_bytes DESC' --dir {dir} --format json",
    ),
    BenchCommand(
        "mm sql 'TOP 10 largest'",
        "metadata",
        "mm sql 'SELECT name, kind, size FROM files ORDER BY size DESC LIMIT 10' --dir {dir} --format json",
    ),
    BenchCommand(
        "mm sql 'GROUP BY ext'",
        "metadata",
        "mm sql 'SELECT ext, COUNT(*) as n, SUM(size) as total_bytes FROM files GROUP BY ext ORDER BY n DESC' --dir {dir} --format json",
    ),
    BenchCommand("mm find --kind image", "metadata", "mm find {dir} --kind image --format json"),
    BenchCommand(
        "mm find --kind audio",
        "metadata",
        "mm find {dir} --kind audio --format json",
        requires_kind="audio",
        skip_reason="no audio files",
    ),
    BenchCommand(
        "mm find --kind document",
        "metadata",
        "mm find {dir} --kind document --format json",
        requires_kind="document",
        skip_reason="no document files",
    ),
    # Plain ``mm grep`` (no --semantic) is a regex pattern search over file
    # contents — Unix-comparable to ``grep -r``, no LLM.
    BenchCommand(
        "mm grep /pattern/", "metadata", "mm grep 'import|include|require' {dir} --format json"
    ),
    BenchCommand(
        "mm grep /pattern/ --ignore-case",
        "metadata",
        "mm grep 'import|include|require' {dir} --ignore-case --format json",
    ),
    BenchCommand(
        "mm peek <image>",
        "metadata",
        "mm peek {file} --format json",
        requires_kind="image",
        skip_reason="no image files",
    ),
    BenchCommand(
        "mm peek <image> (x20)",
        "metadata",
        "mm peek {files} --format json",
        requires_kind="image",
        batch=20,
        skip_reason="no image files",
    ),
    BenchCommand(
        "mm peek <video>",
        "metadata",
        "mm peek {file} --format json",
        requires_kind="video",
        skip_reason="no video files",
    ),
    BenchCommand(
        "mm peek <audio>",
        "metadata",
        "mm peek {file} --format json",
        requires_kind="audio",
        skip_reason="no audio files",
    ),
    BenchCommand(
        "mm peek <pdf>",
        "metadata",
        "mm peek {file} --format json",
        requires_kind="document",
        skip_reason="no PDF files",
    ),
    BenchCommand(
        "mm peek <code> (x20)",
        "metadata",
        "mm peek {files} --format json",
        requires_kind="code",
        batch=20,
        skip_reason="no code files",
    ),
]

FAST_COMMANDS: list[BenchCommand] = [
    BenchCommand(
        "mm cat <code> (x20)",
        "fast",
        "mm cat {files} --mode fast --no-cache --format json",
        requires_kind="code",
        batch=20,
        skip_reason="no code files",
    ),
    BenchCommand(
        "mm cat <image>",
        "fast",
        "mm cat {file} --mode fast --no-cache --format json",
        requires_kind="image",
        skip_reason="no image files",
    ),
    BenchCommand(
        "mm cat <image> (x20)",
        "fast",
        "mm cat {files} --mode fast --no-cache --format json",
        requires_kind="image",
        batch=20,
        skip_reason="no image files",
    ),
    BenchCommand(
        "mm cat <audio>",
        "fast",
        "mm cat {file} --mode fast --no-cache --format json",
        requires_kind="audio",
        skip_reason="no audio files",
    ),
    BenchCommand(
        "mm cat <video>",
        "fast",
        "mm cat {file} --mode fast --no-cache --format json",
        requires_kind="video",
        skip_reason="no video files",
    ),
    BenchCommand(
        "mm cat <pdf>",
        "fast",
        "mm cat {file} --mode fast --no-cache --format json",
        requires_kind="document",
        skip_reason="no PDF files",
    ),
    BenchCommand(
        "mm cat <pdf> (x10)",
        "fast",
        "mm cat {files} --mode fast --no-cache --format json",
        requires_kind="document",
        batch=10,
        skip_reason="no PDF files",
    ),
]

ACCURATE_COMMANDS: list[BenchCommand] = [
    BenchCommand(
        "mm cat <image>",
        "accurate",
        "mm cat {file} --mode accurate --no-cache --format json",
        requires_kind="image",
        skip_reason="no image files",
    ),
    BenchCommand(
        "mm cat <audio>",
        "accurate",
        "mm cat {file} --mode accurate --no-cache --format json",
        requires_kind="audio",
        smallest=True,
        skip_reason="no audio files",
    ),
    BenchCommand(
        "mm cat <video>",
        "accurate",
        "mm cat {file} --mode accurate --no-cache --format json",
        requires_kind="video",
        skip_reason="no video files",
    ),
]

ALL_COMMANDS: list[BenchCommand] = (
    OVERHEAD_COMMANDS + METADATA_COMMANDS + FAST_COMMANDS + ACCURATE_COMMANDS
)


_DEFAULT_STDOUT_KINDS: tuple[str, ...] = ("video", "image", "audio", "document")


def build_encoder_cat_commands(
    files: list[FileEntry],
    *,
    kinds: tuple[str, ...] = _DEFAULT_STDOUT_KINDS,
    mode: str = "fast",
    no_generate: bool = True,
) -> list[BenchCommand]:
    """Synthesise one ``mm cat`` BenchCommand per registered encoder.

    For each registered encoder whose ``media_types`` intersect ``kinds`` and
    where the directory contains at least one file of that kind, emit a
    ``mm cat <file> -p <encoder>`` command. The encoder name is used as both
    the bench name and the trailing ``# encoder`` comment in stdout output.

    Args:
        files: Files discovered in the bench directory (used purely to filter
            encoders down to kinds we actually have material for).
        kinds: Media kinds to include. Defaults to all four binary kinds.
        mode: ``"fast"`` (default) or ``"accurate"``. Controls the LLM
            ``--mode`` flag passed through to ``mm cat`` so the same encoder
            can be sampled at both quality tiers.
        no_generate: When True (default) appends ``--no-generate`` so each
            command emits raw encoder text without invoking the LLM. The
            resulting snapshot is deterministic, fast, and offline-friendly
            — ideal for ``tests/stdout/cat.md``. Set to False to capture
            full LLM-rendered output (slow; depends on profile/model).

    Returns:
        BenchCommand list ordered by ``(kind, encoder name)`` for stable
        output across runs. Each command is single-file (``batch=0``) and
        ``smallest=True`` so the snapshot picks the cheapest representative.
    """
    from mm.encoders import _REGISTRY, _ensure_discovered

    _ensure_discovered()

    have_kind = {k for k in kinds if any(f.kind == k for f in files)}
    if not have_kind:
        return []

    extras = " --no-generate" if no_generate else ""

    cmds: list[BenchCommand] = []
    for encoder_name in sorted(_REGISTRY):
        strat = _REGISTRY[encoder_name]
        for media_type in strat.media_types:
            if media_type not in have_kind:
                continue
            cmds.append(
                BenchCommand(
                    name=f"mm cat <{media_type}> -p {encoder_name}",
                    group=f"snapshot/{media_type}",
                    cmd_template=(
                        f"mm cat {{file}} --mode {mode} --pipeline {encoder_name}"
                        f" --no-cache{extras} --format json"
                    ),
                    requires_kind=media_type,
                    smallest=True,
                    skip_reason=f"no {media_type} files",
                )
            )
            break

    cmds.sort(key=lambda c: (c.group, c.name))
    return cmds
