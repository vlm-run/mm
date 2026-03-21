"""Benchmark command definitions for vlmctx bench.

Each benchmark is a BenchCommand dataclass that describes what to run and how.
Add new benchmarks by appending to L0_COMMANDS or L1_COMMANDS, or by creating
new groups entirely.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class BenchCommand:
    """A single benchmark command definition.

    Attributes:
        name: Display name (e.g. ``vlmctx find .``).
        group: Grouping label (``L0``, ``L1``, etc.).
        make_fn: Factory that receives ``(directory, files, scanner_factory)``
            and returns either a zero-arg callable to benchmark, or *None* to
            skip.  Returning *None* means the command is not applicable (e.g.
            no image files for ``cat image``).
        skip_reason_fn: Optional callable returning a skip reason string when
            ``make_fn`` returns *None*.  Defaults to a generic message.
        files_count_fn: Optional callable ``(directory, files) -> int`` for the
            result's ``files_count``.
        total_bytes_fn: Optional callable ``(directory, files) -> int`` for the
            result's ``total_bytes``.
    """

    name: str
    group: str
    make_fn: Callable[..., Callable[[], Any] | None]
    skip_reason: str = "not applicable"
    files_count_fn: Callable[..., int] | None = None
    total_bytes_fn: Callable[..., int] | None = None


# ── Helpers ──────────────────────────────────────────────────────────


def _pick_file_by_kind(files: list, kind: str) -> str | None:
    for f in files:
        if f.kind == kind:
            return f.path
    return None


def _all_count(directory: Path, files: list) -> int:
    return len(files)


def _all_bytes(directory: Path, files: list) -> int:
    return sum(
        (directory.resolve() / f.path).stat().st_size
        for f in files
        if (directory.resolve() / f.path).exists()
    )


# ── L0 command factories ────────────────────────────────────────────


def _make_find(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any]:
    resolved = str(directory.resolve())

    def run():
        s = scanner_cls(resolved)
        s.scan()
        s.to_json_fast()

    return run


def _make_ls(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any]:
    from vlmctx.context import Context

    def run():
        c = Context(directory)
        c.to_arrow()

    return run


def _make_wc(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any]:
    import json as json_mod

    resolved = str(directory.resolve())

    def run():
        s = scanner_cls(resolved)
        s.scan()
        json_mod.loads(s.to_json_fast())

    return run


def _make_sql(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any]:
    from vlmctx.context import Context

    def run():
        c = Context(directory)
        c.sql("SELECT kind, COUNT(*) as n FROM files GROUP BY kind")

    return run


def _make_find_kind_image(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any]:
    resolved = str(directory.resolve())

    def run():
        s = scanner_cls(resolved)
        s.scan()
        s.to_json_fast(kind="image")

    return run


# ── L1 command factories ────────────────────────────────────────────


def _make_cat_code(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any] | None:
    code_files = [f.path for f in files if f.kind == "code"][:20]
    if not code_files:
        return None
    resolved = str(directory.resolve())
    scanner = scanner_cls(resolved)
    scanner.scan()

    def run():
        for p in code_files:
            scanner.extract_l1(p)

    return run


def _cat_code_count(directory: Path, files: list) -> int:
    return min(len([f for f in files if f.kind == "code"]), 20)


def _cat_code_bytes(directory: Path, files: list) -> int:
    code_files = [f.path for f in files if f.kind == "code"][:20]
    return sum(
        (directory.resolve() / p).stat().st_size
        for p in code_files
        if (directory.resolve() / p).exists()
    )


def _make_cat_image(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any] | None:
    img_path = _pick_file_by_kind(files, "image")
    if not img_path:
        return None
    resolved = str(directory.resolve())
    scanner = scanner_cls(resolved)
    scanner.scan()

    def run():
        scanner.extract_l1(img_path)

    return run


def _cat_image_count(directory: Path, files: list) -> int:
    return 1 if _pick_file_by_kind(files, "image") else 0


def _cat_image_bytes(directory: Path, files: list) -> int:
    p = _pick_file_by_kind(files, "image")
    return (directory.resolve() / p).stat().st_size if p else 0


def _make_cat_video(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any] | None:
    vid_path = _pick_file_by_kind(files, "video")
    if not vid_path:
        return None
    resolved = str(directory.resolve())
    scanner = scanner_cls(resolved)
    scanner.scan()

    def run():
        scanner.extract_l1(vid_path)

    return run


def _cat_video_count(directory: Path, files: list) -> int:
    return 1 if _pick_file_by_kind(files, "video") else 0


def _cat_video_bytes(directory: Path, files: list) -> int:
    p = _pick_file_by_kind(files, "video")
    return (directory.resolve() / p).stat().st_size if p else 0


def _make_cat_pdf(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any] | None:
    doc_path = _pick_file_by_kind(files, "document")
    if not doc_path:
        return None
    full_path = directory.resolve() / doc_path

    def run():
        from vlmctx.commands.cat import _l1_pdf
        _l1_pdf(full_path)

    return run


def _cat_pdf_count(directory: Path, files: list) -> int:
    return 1 if _pick_file_by_kind(files, "document") else 0


def _cat_pdf_bytes(directory: Path, files: list) -> int:
    p = _pick_file_by_kind(files, "document")
    return (directory.resolve() / p).stat().st_size if p else 0


def _make_grep(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any] | None:
    text_files = [f for f in files if not f.is_binary or f.kind == "document"][:50]
    if not text_files:
        return None
    resolved_dir = directory.resolve()

    def run():
        import re
        regex = re.compile(r"import|include|require")
        for f in text_files:
            try:
                content = (resolved_dir / f.path).read_text(errors="replace")
                for line in content.splitlines():
                    regex.search(line)
            except Exception:
                continue

    return run


def _grep_count(directory: Path, files: list) -> int:
    return min(len([f for f in files if not f.is_binary or f.kind == "document"]), 50)


def _grep_bytes(directory: Path, files: list) -> int:
    text_files = [f for f in files if not f.is_binary or f.kind == "document"][:50]
    return sum(
        (directory.resolve() / f.path).stat().st_size
        for f in text_files
        if (directory.resolve() / f.path).exists()
    )


# ── Command registries ──────────────────────────────────────────────

L0_COMMANDS: list[BenchCommand] = [
    BenchCommand("vlmctx find .", "L0", _make_find, "empty directory", _all_count, _all_bytes),
    BenchCommand("vlmctx ls .", "L0", _make_ls, "empty directory", _all_count, _all_bytes),
    BenchCommand("vlmctx wc .", "L0", _make_wc, "empty directory", _all_count, _all_bytes),
    BenchCommand("vlmctx sql 'GROUP BY kind'", "L0", _make_sql, "empty directory", _all_count, _all_bytes),
    BenchCommand("vlmctx find --kind image", "L0", _make_find_kind_image, "empty directory", _all_count, _all_bytes),
]

L1_COMMANDS: list[BenchCommand] = [
    BenchCommand("vlmctx cat <code> (x20)", "L1", _make_cat_code, "no code files", _cat_code_count, _cat_code_bytes),
    BenchCommand("vlmctx cat <image>", "L1", _make_cat_image, "no image files", _cat_image_count, _cat_image_bytes),
    BenchCommand("vlmctx cat <video>", "L1", _make_cat_video, "no video files", _cat_video_count, _cat_video_bytes),
    BenchCommand("vlmctx cat <pdf>", "L1", _make_cat_pdf, "no PDF files", _cat_pdf_count, _cat_pdf_bytes),
    BenchCommand("vlmctx grep /pattern/", "L1", _make_grep, "no text files", _grep_count, _grep_bytes),
]

ALL_COMMANDS: list[BenchCommand] = L0_COMMANDS + L1_COMMANDS
