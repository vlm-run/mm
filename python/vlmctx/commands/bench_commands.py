"""Benchmark command definitions for vlmctx bench.

Each benchmark is a BenchCommand dataclass that describes what to run and how.
Add new benchmarks by appending to L0_COMMANDS or L1_COMMANDS, or by creating
new groups entirely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# Maximum preview lines shown per command.
_MAX_PREVIEW_LINES = 5


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
        preview_fn: Optional factory ``(directory, files, scanner_cls) -> list[str]``
            that returns representative output lines for display.
        skip_reason: Reason shown when ``make_fn`` returns *None*.
        files_count_fn: Optional callable ``(directory, files) -> int``.
        total_bytes_fn: Optional callable ``(directory, files) -> int``.
    """

    name: str
    group: str
    make_fn: Callable[..., Callable[[], Any] | None]
    skip_reason: str = "not applicable"
    preview_fn: Callable[..., list[str]] | None = None
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


def _truncate(lines: list[str], total: int, unit: str = "files") -> list[str]:
    """Truncate a list of lines and add a summary if needed."""
    if len(lines) <= _MAX_PREVIEW_LINES:
        return lines
    result = lines[:_MAX_PREVIEW_LINES]
    result.append(f"... ({total:,} {unit})")
    return result


# ── L0 command factories ────────────────────────────────────────────


def _make_find(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any]:
    resolved = str(directory.resolve())

    def run():
        s = scanner_cls(resolved)
        s.scan()
        s.to_json_fast()

    return run


def _preview_find(directory: Path, files: list, scanner_cls: type) -> list[str]:
    paths = [f.path for f in files]
    return _truncate(paths, len(paths))


def _make_ls(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any]:
    from vlmctx.context import Context

    def run():
        c = Context(directory)
        c.to_arrow()

    return run


def _preview_ls(directory: Path, files: list, scanner_cls: type) -> list[str]:
    from vlmctx.display import format_size
    lines = []
    for f in files[:_MAX_PREVIEW_LINES]:
        size = format_size((directory.resolve() / f.path).stat().st_size) if (directory.resolve() / f.path).exists() else "?"
        lines.append(f"{f.path:<40} {f.kind:<8} {size:>8}")
    if len(files) > _MAX_PREVIEW_LINES:
        lines.append(f"... ({len(files):,} rows)")
    return lines


def _make_wc(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any]:
    import json as json_mod

    resolved = str(directory.resolve())

    def run():
        s = scanner_cls(resolved)
        s.scan()
        json_mod.loads(s.to_json_fast())

    return run


def _preview_wc(directory: Path, files: list, scanner_cls: type) -> list[str]:
    from vlmctx.display import format_size
    total_bytes = sum(
        (directory.resolve() / f.path).stat().st_size
        for f in files
        if (directory.resolve() / f.path).exists()
    )
    return [f"{len(files):,} files  {format_size(total_bytes)}"]


def _make_sql(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any]:
    from vlmctx.context import Context

    def run():
        c = Context(directory)
        c.sql("SELECT kind, COUNT(*) as n FROM files GROUP BY kind")

    return run


def _preview_sql(directory: Path, files: list, scanner_cls: type) -> list[str]:
    from collections import Counter
    counts = Counter(f.kind for f in files)
    lines = [f"{'kind':<12} {'n':>5}"]
    for kind, n in counts.most_common():
        lines.append(f"{kind:<12} {n:>5}")
    return lines


def _make_find_kind_image(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any]:
    resolved = str(directory.resolve())

    def run():
        s = scanner_cls(resolved)
        s.scan()
        s.to_json_fast(kind="image")

    return run


def _preview_find_kind_image(directory: Path, files: list, scanner_cls: type) -> list[str]:
    img_files = [f.path for f in files if f.kind == "image"]
    if not img_files:
        return ["(no image files)"]
    return _truncate(img_files, len(img_files))


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


def _preview_cat_code(directory: Path, files: list, scanner_cls: type) -> list[str]:
    code_files = [f for f in files if f.kind == "code"][:20]
    if not code_files:
        return []
    # Show first few lines of the first code file
    first = directory.resolve() / code_files[0].path
    try:
        src_lines = first.read_text(errors="replace").splitlines()[:4]
        lines = [f"# {code_files[0].path}"] + src_lines
        if len(code_files) > 1:
            lines.append(f"... ({len(code_files)} files)")
        return lines
    except Exception:
        return [code_files[0].path]


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


def _preview_cat_image(directory: Path, files: list, scanner_cls: type) -> list[str]:
    img = next((f for f in files if f.kind == "image"), None)
    if not img:
        return []
    return [img.path]


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


def _preview_cat_video(directory: Path, files: list, scanner_cls: type) -> list[str]:
    vid = next((f for f in files if f.kind == "video"), None)
    if not vid:
        return []
    return [vid.path]


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


def _preview_cat_pdf(directory: Path, files: list, scanner_cls: type) -> list[str]:
    doc = next((f for f in files if f.kind == "document"), None)
    if not doc:
        return []
    # Try to extract first few lines of text
    try:
        from vlmctx.commands.cat import _l1_pdf
        text = _l1_pdf(directory.resolve() / doc.path)
        lines = [f"# {doc.path}"] + text.splitlines()[:4]
        return lines
    except Exception:
        return [doc.path]


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


def _preview_grep(directory: Path, files: list, scanner_cls: type) -> list[str]:
    import re
    text_files = [f for f in files if not f.is_binary or f.kind == "document"][:50]
    regex = re.compile(r"import|include|require")
    hits: list[str] = []
    resolved_dir = directory.resolve()
    for f in text_files:
        try:
            for i, line in enumerate((resolved_dir / f.path).read_text(errors="replace").splitlines(), 1):
                if regex.search(line):
                    hits.append(f"{f.path}:{i}:{line.strip()}")
                    if len(hits) >= _MAX_PREVIEW_LINES:
                        break
        except Exception:
            continue
        if len(hits) >= _MAX_PREVIEW_LINES:
            break
    total_files = len(text_files)
    if len(hits) >= _MAX_PREVIEW_LINES:
        hits.append(f"... ({total_files} files searched)")
    return hits


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
    BenchCommand("vlmctx find .", "L0", _make_find, "empty directory", _preview_find, _all_count, _all_bytes),
    BenchCommand("vlmctx ls .", "L0", _make_ls, "empty directory", _preview_ls, _all_count, _all_bytes),
    BenchCommand("vlmctx wc .", "L0", _make_wc, "empty directory", _preview_wc, _all_count, _all_bytes),
    BenchCommand("vlmctx sql 'GROUP BY kind'", "L0", _make_sql, "empty directory", _preview_sql, _all_count, _all_bytes),
    BenchCommand("vlmctx find --kind image", "L0", _make_find_kind_image, "empty directory", _preview_find_kind_image, _all_count, _all_bytes),
]

L1_COMMANDS: list[BenchCommand] = [
    BenchCommand("vlmctx cat <code> (x20)", "L1", _make_cat_code, "no code files", _preview_cat_code, _cat_code_count, _cat_code_bytes),
    BenchCommand("vlmctx cat <image>", "L1", _make_cat_image, "no image files", _preview_cat_image, _cat_image_count, _cat_image_bytes),
    BenchCommand("vlmctx cat <video>", "L1", _make_cat_video, "no video files", _preview_cat_video, _cat_video_count, _cat_video_bytes),
    BenchCommand("vlmctx cat <pdf>", "L1", _make_cat_pdf, "no PDF files", _preview_cat_pdf, _cat_pdf_count, _cat_pdf_bytes),
    BenchCommand("vlmctx grep /pattern/", "L1", _make_grep, "no text files", _preview_grep, _grep_count, _grep_bytes),
]

ALL_COMMANDS: list[BenchCommand] = L0_COMMANDS + L1_COMMANDS
