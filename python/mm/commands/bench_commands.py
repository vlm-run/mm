"""Benchmark command definitions for mm bench.

Each benchmark is a declarative shell command template. The runner resolves
placeholders ({dir}, {file}, {files}) from a pre-scan, then executes via
subprocess for true end-to-end measurement.

Add new benchmarks by appending to L0_COMMANDS, L1_COMMANDS, or L2_COMMANDS.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BenchCommand:
    """A single benchmark as a shell command template.

    Placeholders:
        {dir}    — resolved absolute directory path
        {file}   — single file picked by ``requires_kind``
        {files}  — space-separated list of files (batch commands)

    Attributes:
        name:          Display name shown in output.
        group:         Grouping label (``L0``, ``L1``, ``L2``).
        cmd_template:  Shell command with placeholders.
        requires_kind: File kind needed for {file}/{files}. None = directory-only.
        batch:         Number of files for {files} (0 = single {file}).
        smallest:      If True, pick the smallest file of requires_kind.
        skip_reason:   Reason shown when skipped.
    """

    name: str
    group: str
    cmd_template: str
    requires_kind: str | None = None
    batch: int = 0
    smallest: bool = False
    skip_reason: str = "not applicable"


# ── Resolution ─────────────────────────────────────────────────────


def _pick_file(files: list, kind: str) -> str | None:
    """Pick the first file matching kind."""
    for f in files:
        if f.kind == kind:
            return f.path
    return None


def _pick_smallest(files: list, kind: str, directory: Path) -> str | None:
    """Pick the smallest file of kind (by file size)."""
    candidates = [f for f in files if f.kind == kind]
    if not candidates:
        return None
    candidates.sort(
        key=lambda f: (directory.resolve() / f.path).stat().st_size
        if (directory.resolve() / f.path).exists()
        else float("inf")
    )
    return candidates[0].path


def _pick_files(files: list, kind: str, limit: int) -> list[str]:
    """Pick up to limit files matching kind."""
    return [f.path for f in files if f.kind == kind][:limit]


def _get_media_duration(directory: Path, rel_path: str) -> float:
    """Get media duration in seconds via Rust L1 extraction."""
    try:
        from mm._mm import Scanner
        scanner = Scanner(str(directory.resolve()))
        scanner.scan()
        r = scanner.extract_l1(rel_path)
        return r.duration_s or 0.0
    except Exception:
        return 0.0


_MEDIA_KINDS = frozenset(("video", "audio"))


def resolve_command(
    cmd: BenchCommand,
    directory: Path,
    files: list,
) -> tuple[list[str], int, int, float] | None:
    """Resolve a command template into (argv, files_count, total_bytes, media_duration_s).

    Returns None if the command should be skipped (missing files).
    """
    resolved_dir = str(directory.resolve())
    template = cmd.cmd_template
    media_duration_s = 0.0

    if cmd.requires_kind is not None:
        # Check kind exists (for skip logic even on directory-level commands)
        if not any(f.kind == cmd.requires_kind for f in files):
            return None

        if cmd.batch > 0 and "{files}" in template:
            picked = _pick_files(files, cmd.requires_kind, cmd.batch)
            abs_paths = [str(directory.resolve() / p) for p in picked]
            template = template.replace("{files}", " ".join(shlex.quote(p) for p in abs_paths))
            count = len(picked)
            total = sum(
                (directory.resolve() / p).stat().st_size
                for p in picked
                if (directory.resolve() / p).exists()
            )
        elif "{file}" in template:
            if cmd.smallest:
                picked_one = _pick_smallest(files, cmd.requires_kind, directory)
            else:
                picked_one = _pick_file(files, cmd.requires_kind)
            if not picked_one:
                return None
            abs_path = str(directory.resolve() / picked_one)
            template = template.replace("{file}", shlex.quote(abs_path))
            count = 1
            total = (directory.resolve() / picked_one).stat().st_size if (directory.resolve() / picked_one).exists() else 0
            if cmd.requires_kind in _MEDIA_KINDS:
                media_duration_s = _get_media_duration(directory, picked_one)
        else:
            # Directory-level command with requires_kind just for skip logic
            count = len(files)
            total = sum(
                (directory.resolve() / f.path).stat().st_size
                for f in files
                if (directory.resolve() / f.path).exists()
            )
    else:
        count = len(files)
        total = sum(
            (directory.resolve() / f.path).stat().st_size
            for f in files
            if (directory.resolve() / f.path).exists()
        )

    template = template.replace("{dir}", shlex.quote(resolved_dir))
    argv = shlex.split(template)
    return argv, count, total, media_duration_s


# ── Command registries ──────────────────────────────────────────────

L0_COMMANDS: list[BenchCommand] = [
    BenchCommand("mm find .", "L0",
                 "mm find {dir} --format json"),
    BenchCommand("mm find . (table)", "L0",
                 "mm find {dir} --format tsv"),
    BenchCommand("mm wc .", "L0",
                 "mm wc {dir} --format json"),
    BenchCommand("mm sql 'GROUP BY kind'", "L0",
                 "mm sql 'SELECT kind, COUNT(*) as n FROM files GROUP BY kind' --dir {dir} --format json"),
    BenchCommand("mm sql 'SUM(size) BY kind'", "L0",
                 "mm sql 'SELECT kind, COUNT(*) as n, SUM(size) as total_bytes, ROUND(AVG(size)) as avg_bytes FROM files GROUP BY kind ORDER BY total_bytes DESC' --dir {dir} --format json"),
    BenchCommand("mm sql 'TOP 10 largest'", "L0",
                 "mm sql 'SELECT name, kind, size FROM files ORDER BY size DESC LIMIT 10' --dir {dir} --format json"),
    BenchCommand("mm sql 'GROUP BY ext'", "L0",
                 "mm sql 'SELECT ext, COUNT(*) as n, SUM(size) as total_bytes FROM files GROUP BY ext ORDER BY n DESC' --dir {dir} --format json"),
    BenchCommand("mm find --kind image", "L0",
                 "mm find {dir} --kind image --format json"),
    BenchCommand("mm find --kind audio", "L0",
                 "mm find {dir} --kind audio --format json",
                 requires_kind="audio", skip_reason="no audio files"),
    BenchCommand("mm find --kind document", "L0",
                 "mm find {dir} --kind document --format json",
                 requires_kind="document", skip_reason="no document files"),
]

L1_COMMANDS: list[BenchCommand] = [
    BenchCommand("mm cat <code> (x20)", "L1",
                 "mm cat {files} --format json",
                 requires_kind="code", batch=20, skip_reason="no code files"),
    BenchCommand("mm cat <image>", "L1",
                 "mm cat {file} --format json",
                 requires_kind="image", skip_reason="no image files"),
    BenchCommand("mm cat <image> (x20)", "L1",
                 "mm cat {files} --format json",
                 requires_kind="image", batch=20, skip_reason="no image files"),
    BenchCommand("mm cat <audio>", "L1",
                 "mm cat {file} --format json",
                 requires_kind="audio", skip_reason="no audio files"),
    BenchCommand("mm cat <video>", "L1",
                 "mm cat {file} --format json",
                 requires_kind="video", skip_reason="no video files"),
    BenchCommand("mm cat <pdf>", "L1",
                 "mm cat {file} --format json",
                 requires_kind="document", skip_reason="no PDF files"),
    BenchCommand("mm cat <pdf> (x10)", "L1",
                 "mm cat {files} --format json",
                 requires_kind="document", batch=10, skip_reason="no PDF files"),
    BenchCommand("mm grep /pattern/", "L1",
                 "mm grep 'import|include|require' {dir} --format json"),
]

L2_COMMANDS: list[BenchCommand] = [
    BenchCommand("mm cat <image> -l2 --mode fast", "L2",
                 "mm cat {file} -l 2 --mode fast --format json",
                 requires_kind="image", skip_reason="no image files"),
    BenchCommand("mm cat <image> -l2 --mode accurate", "L2",
                 "mm cat {file} -l 2 --mode accurate --format json",
                 requires_kind="image", skip_reason="no image files"),
    BenchCommand("mm cat <audio> -l2 --mode fast", "L2",
                 "mm cat {file} -l 2 --mode fast --format json",
                 requires_kind="audio", smallest=True, skip_reason="no audio files"),
    BenchCommand("mm cat <audio> -l2 --mode accurate", "L2",
                 "mm cat {file} -l 2 --mode accurate --format json",
                 requires_kind="audio", smallest=True, skip_reason="no audio files"),
    BenchCommand("mm cat <video> -l2 --mode fast", "L2",
                 "mm cat {file} -l 2 --mode fast --format json",
                 requires_kind="video", skip_reason="no video files"),
    BenchCommand("mm cat <video> -l2 --mode accurate", "L2",
                 "mm cat {file} -l 2 --mode accurate --format json",
                 requires_kind="video", skip_reason="no video files"),
]

ALL_COMMANDS: list[BenchCommand] = L0_COMMANDS + L1_COMMANDS + L2_COMMANDS
