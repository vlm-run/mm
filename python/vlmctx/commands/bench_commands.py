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


def _make_find_table(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any]:
    """Benchmark find with tabular output (Context + Arrow path)."""
    from vlmctx.context import Context

    def run():
        c = Context(directory)
        c.to_arrow()

    return run


def _preview_find_table(directory: Path, files: list, scanner_cls: type) -> list[str]:
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


def _make_find_kind_audio(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any] | None:
    if not any(f.kind == "audio" for f in files):
        return None
    resolved = str(directory.resolve())

    def run():
        s = scanner_cls(resolved)
        s.scan()
        s.to_json_fast(kind="audio")

    return run


def _make_find_kind_document(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any] | None:
    if not any(f.kind == "document" for f in files):
        return None
    resolved = str(directory.resolve())

    def run():
        s = scanner_cls(resolved)
        s.scan()
        s.to_json_fast(kind="document")

    return run


def _preview_find_kind(kind: str, directory: Path, files: list, scanner_cls: type) -> list[str]:
    matched = [f.path for f in files if f.kind == kind]
    if not matched:
        return [f"(no {kind} files)"]
    return _truncate(matched, len(matched))


def _make_sql_size_by_kind(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any]:
    from vlmctx.context import Context

    def run():
        c = Context(directory)
        c.sql("SELECT kind, COUNT(*) as n, SUM(size) as total_bytes, ROUND(AVG(size)) as avg_bytes FROM files GROUP BY kind ORDER BY total_bytes DESC")

    return run


def _preview_sql_size_by_kind(directory: Path, files: list, scanner_cls: type) -> list[str]:
    from collections import Counter, defaultdict
    counts: Counter = Counter()
    sizes: dict[str, int] = defaultdict(int)
    for f in files:
        counts[f.kind] += 1
        sizes[f.kind] += getattr(f, 'size', 0) if hasattr(f, 'size') else 0
    lines = [f"{'kind':<12} {'n':>5}  {'total':>12}"]
    for kind, n in counts.most_common():
        from vlmctx.display import format_size
        lines.append(f"{kind:<12} {n:>5}  {format_size(sizes[kind]):>12}")
    return lines


def _make_sql_top_k_largest(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any]:
    from vlmctx.context import Context

    def run():
        c = Context(directory)
        c.sql("SELECT name, kind, size FROM files ORDER BY size DESC LIMIT 10")

    return run


def _preview_sql_top_k(directory: Path, files: list, scanner_cls: type) -> list[str]:
    from vlmctx.display import format_size
    sorted_files = sorted(files, key=lambda f: getattr(f, 'size', 0) if hasattr(f, 'size') else 0, reverse=True)[:5]
    lines = []
    for f in sorted_files:
        sz = getattr(f, 'size', 0) if hasattr(f, 'size') else 0
        lines.append(f"{f.path:<50} {format_size(sz):>10}")
    return lines


def _make_sql_ext_breakdown(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any]:
    from vlmctx.context import Context

    def run():
        c = Context(directory)
        c.sql("SELECT ext, COUNT(*) as n, SUM(size) as total_bytes FROM files GROUP BY ext ORDER BY n DESC")

    return run


def _preview_sql_ext(directory: Path, files: list, scanner_cls: type) -> list[str]:
    from collections import Counter
    counts = Counter(f.ext for f in files)
    return [f"{ext:<8} {n:>5}" for ext, n in counts.most_common(5)]


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
        from vlmctx.commands.cat import _l1_pdf_fallback as _l1_pdf
        _l1_pdf(full_path)

    return run


def _preview_cat_pdf(directory: Path, files: list, scanner_cls: type) -> list[str]:
    doc = next((f for f in files if f.kind == "document"), None)
    if not doc:
        return []
    # Try to extract first few lines of text
    try:
        from vlmctx.commands.cat import _l1_pdf_fallback as _l1_pdf
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


# ── L1 audio + batch factories ──────────────────────────────────────


def _make_cat_audio(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any] | None:
    aud_path = _pick_file_by_kind(files, "audio")
    if not aud_path:
        return None
    resolved = str(directory.resolve())
    scanner = scanner_cls(resolved)
    scanner.scan()

    def run():
        scanner.extract_l1(aud_path)

    return run


def _preview_cat_audio(directory: Path, files: list, scanner_cls: type) -> list[str]:
    aud = next((f for f in files if f.kind == "audio"), None)
    if not aud:
        return []
    return [aud.path]


def _cat_audio_count(directory: Path, files: list) -> int:
    return 1 if _pick_file_by_kind(files, "audio") else 0


def _cat_audio_bytes(directory: Path, files: list) -> int:
    p = _pick_file_by_kind(files, "audio")
    return (directory.resolve() / p).stat().st_size if p else 0


def _make_cat_images_batch(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any] | None:
    img_files = [f.path for f in files if f.kind == "image"][:20]
    if not img_files:
        return None
    resolved = str(directory.resolve())
    scanner = scanner_cls(resolved)
    scanner.scan()

    def run():
        for p in img_files:
            scanner.extract_l1(p)

    return run


def _cat_images_batch_count(directory: Path, files: list) -> int:
    return min(len([f for f in files if f.kind == "image"]), 20)


def _cat_images_batch_bytes(directory: Path, files: list) -> int:
    img_files = [f.path for f in files if f.kind == "image"][:20]
    return sum(
        (directory.resolve() / p).stat().st_size
        for p in img_files
        if (directory.resolve() / p).exists()
    )


def _preview_cat_images_batch(directory: Path, files: list, scanner_cls: type) -> list[str]:
    img_files = [f.path for f in files if f.kind == "image"][:20]
    return _truncate(img_files, len(img_files))


def _make_cat_pdfs_batch(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any] | None:
    doc_files = [f for f in files if f.kind == "document"][:10]
    if not doc_files:
        return None
    resolved_dir = directory.resolve()

    def run():
        from vlmctx.commands.cat import _l1_pdf_fallback as _l1_pdf
        for f in doc_files:
            _l1_pdf(resolved_dir / f.path)

    return run


def _cat_pdfs_batch_count(directory: Path, files: list) -> int:
    return min(len([f for f in files if f.kind == "document"]), 10)


def _cat_pdfs_batch_bytes(directory: Path, files: list) -> int:
    doc_files = [f.path for f in files if f.kind == "document"][:10]
    return sum(
        (directory.resolve() / p).stat().st_size
        for p in doc_files
        if (directory.resolve() / p).exists()
    )


def _preview_cat_pdfs_batch(directory: Path, files: list, scanner_cls: type) -> list[str]:
    doc_files = [f.path for f in files if f.kind == "document"][:10]
    return _truncate(doc_files, len(doc_files), "PDFs")


# ── Command registries ──────────────────────────────────────────────

L0_COMMANDS: list[BenchCommand] = [
    BenchCommand("vlmctx find .", "L0", _make_find, "empty directory", _preview_find, _all_count, _all_bytes),
    BenchCommand("vlmctx find . (table)", "L0", _make_find_table, "empty directory", _preview_find_table, _all_count, _all_bytes),
    BenchCommand("vlmctx wc .", "L0", _make_wc, "empty directory", _preview_wc, _all_count, _all_bytes),
    BenchCommand("vlmctx sql 'GROUP BY kind'", "L0", _make_sql, "empty directory", _preview_sql, _all_count, _all_bytes),
    BenchCommand("vlmctx sql 'SUM(size) BY kind'", "L0", _make_sql_size_by_kind, "empty directory", _preview_sql_size_by_kind, _all_count, _all_bytes),
    BenchCommand("vlmctx sql 'TOP 10 largest'", "L0", _make_sql_top_k_largest, "empty directory", _preview_sql_top_k, _all_count, _all_bytes),
    BenchCommand("vlmctx sql 'GROUP BY ext'", "L0", _make_sql_ext_breakdown, "empty directory", _preview_sql_ext, _all_count, _all_bytes),
    BenchCommand("vlmctx find --kind image", "L0", _make_find_kind_image, "empty directory", _preview_find_kind_image, _all_count, _all_bytes),
    BenchCommand("vlmctx find --kind audio", "L0", _make_find_kind_audio, "no audio files", lambda d, f, s: _preview_find_kind("audio", d, f, s), _all_count, _all_bytes),
    BenchCommand("vlmctx find --kind document", "L0", _make_find_kind_document, "no document files", lambda d, f, s: _preview_find_kind("document", d, f, s), _all_count, _all_bytes),
]

L1_COMMANDS: list[BenchCommand] = [
    BenchCommand("vlmctx cat <code> (x20)", "L1", _make_cat_code, "no code files", _preview_cat_code, _cat_code_count, _cat_code_bytes),
    BenchCommand("vlmctx cat <image>", "L1", _make_cat_image, "no image files", _preview_cat_image, _cat_image_count, _cat_image_bytes),
    BenchCommand("vlmctx cat <image> (x20)", "L1", _make_cat_images_batch, "no image files", _preview_cat_images_batch, _cat_images_batch_count, _cat_images_batch_bytes),
    BenchCommand("vlmctx cat <audio>", "L1", _make_cat_audio, "no audio files", _preview_cat_audio, _cat_audio_count, _cat_audio_bytes),
    BenchCommand("vlmctx cat <video>", "L1", _make_cat_video, "no video files", _preview_cat_video, _cat_video_count, _cat_video_bytes),
    BenchCommand("vlmctx cat <pdf>", "L1", _make_cat_pdf, "no PDF files", _preview_cat_pdf, _cat_pdf_count, _cat_pdf_bytes),
    BenchCommand("vlmctx cat <pdf> (x10)", "L1", _make_cat_pdfs_batch, "no PDF files", _preview_cat_pdfs_batch, _cat_pdfs_batch_count, _cat_pdfs_batch_bytes),
    BenchCommand("vlmctx grep /pattern/", "L1", _make_grep, "no text files", _preview_grep, _grep_count, _grep_bytes),
]

# ── L2 modal command factories ──────────────────────────────────────


def _make_cat_image_l2_fast(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any] | None:
    img_path = _pick_file_by_kind(files, "image")
    if not img_path:
        return None
    full_path = directory.resolve() / img_path

    def run():
        from vlmctx.commands.cat import _CatOpts, _extract
        opts = _CatOpts(
            level=2, n=None, detail=False, output_dir=None,
            max_pages=None, mosaic_tile="4x4", image_width=160,
            mosaic_count=1, mosaic_strategy="uniform",
            audio_speed=2.0, audio_sample_rate=16000,
            mode="fast", format="json",
        )
        _extract(full_path, opts)

    return run


def _make_cat_image_l2_accurate(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any] | None:
    img_path = _pick_file_by_kind(files, "image")
    if not img_path:
        return None
    full_path = directory.resolve() / img_path

    def run():
        from vlmctx.commands.cat import _CatOpts, _extract
        opts = _CatOpts(
            level=2, n=None, detail=False, output_dir=None,
            max_pages=None, mosaic_tile="4x4", image_width=160,
            mosaic_count=1, mosaic_strategy="uniform",
            audio_speed=2.0, audio_sample_rate=16000,
            mode="accurate", format="json",
        )
        _extract(full_path, opts)

    return run


def _make_cat_video_l2_fast(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any] | None:
    vid_path = _pick_file_by_kind(files, "video")
    if not vid_path:
        return None
    full_path = directory.resolve() / vid_path

    def run():
        from vlmctx.commands.cat import _CatOpts, _extract
        opts = _CatOpts(
            level=2, n=None, detail=False, output_dir=None,
            max_pages=None, mosaic_tile="4x4", image_width=160,
            mosaic_count=1, mosaic_strategy="uniform",
            audio_speed=2.0, audio_sample_rate=16000,
            mode="fast", format="json",
        )
        _extract(full_path, opts)

    return run


def _make_cat_video_l2_accurate(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any] | None:
    vid_path = _pick_file_by_kind(files, "video")
    if not vid_path:
        return None
    full_path = directory.resolve() / vid_path

    def run():
        from vlmctx.commands.cat import _CatOpts, _extract
        opts = _CatOpts(
            level=2, n=None, detail=False, output_dir=None,
            max_pages=None, mosaic_tile="4x4", image_width=160,
            mosaic_count=8, mosaic_strategy="uniform",
            audio_speed=1.0, audio_sample_rate=16000,
            mode="accurate", format="json",
        )
        _extract(full_path, opts)

    return run


def _pick_smallest_audio(files: list, directory: Path, max_duration_s: float = 600) -> str | None:
    """Pick the smallest audio file under max_duration_s for benchmarking.

    Avoids GPU timeouts from running whisper on multi-hour podcasts.
    """
    audio_files = [f for f in files if f.kind == "audio"]
    if not audio_files:
        return None
    # Sort by file size (smallest first) as proxy for duration
    audio_files.sort(key=lambda f: (directory.resolve() / f.path).stat().st_size if (directory.resolve() / f.path).exists() else float("inf"))
    return audio_files[0].path


def _make_cat_audio_l2_fast(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any] | None:
    aud_path = _pick_smallest_audio(files, directory)
    if not aud_path:
        return None
    full_path = directory.resolve() / aud_path

    def run():
        from vlmctx.commands.cat import _CatOpts, _extract
        opts = _CatOpts(
            level=2, n=None, detail=False, output_dir=None,
            max_pages=None, mosaic_tile="4x4", image_width=160,
            mosaic_count=1, mosaic_strategy="uniform",
            audio_speed=2.0, audio_sample_rate=16000,
            mode="fast", format="json",
        )
        _extract(full_path, opts)

    return run


def _make_cat_audio_l2_accurate(directory: Path, files: list, scanner_cls: type) -> Callable[[], Any] | None:
    aud_path = _pick_smallest_audio(files, directory)
    if not aud_path:
        return None
    full_path = directory.resolve() / aud_path

    def run():
        from vlmctx.commands.cat import _CatOpts, _extract
        opts = _CatOpts(
            level=2, n=None, detail=False, output_dir=None,
            max_pages=None, mosaic_tile="4x4", image_width=160,
            mosaic_count=1, mosaic_strategy="uniform",
            audio_speed=1.0, audio_sample_rate=16000,
            mode="accurate", format="json",
        )
        _extract(full_path, opts)

    return run


def _l2_preview(kind: str, mode: str, directory: Path, files: list, scanner_cls: type) -> list[str]:
    f = next((f for f in files if f.kind == kind), None)
    if not f:
        return []
    return [f"{f.path}  (mode={mode})"]


L2_COMMANDS: list[BenchCommand] = [
    BenchCommand(
        "vlmctx cat <image> -l2 --mode fast", "L2",
        _make_cat_image_l2_fast, "no image files",
        lambda d, f, s: _l2_preview("image", "fast", d, f, s),
        _cat_image_count, _cat_image_bytes,
    ),
    BenchCommand(
        "vlmctx cat <image> -l2 --mode accurate", "L2",
        _make_cat_image_l2_accurate, "no image files",
        lambda d, f, s: _l2_preview("image", "accurate", d, f, s),
        _cat_image_count, _cat_image_bytes,
    ),
    BenchCommand(
        "vlmctx cat <video> -l2 --mode fast", "L2",
        _make_cat_video_l2_fast, "no video files",
        lambda d, f, s: _l2_preview("video", "fast", d, f, s),
        _cat_video_count, _cat_video_bytes,
    ),
    BenchCommand(
        "vlmctx cat <video> -l2 --mode accurate", "L2",
        _make_cat_video_l2_accurate, "no video files",
        lambda d, f, s: _l2_preview("video", "accurate", d, f, s),
        _cat_video_count, _cat_video_bytes,
    ),
    BenchCommand(
        "vlmctx cat <audio> -l2 --mode fast", "L2",
        _make_cat_audio_l2_fast, "no audio files",
        lambda d, f, s: [f"{_pick_smallest_audio(f, d) or '?'}  (mode=fast, smallest audio)"],
        _cat_audio_count, _cat_audio_bytes,
    ),
    BenchCommand(
        "vlmctx cat <audio> -l2 --mode accurate", "L2",
        _make_cat_audio_l2_accurate, "no audio files",
        lambda d, f, s: [f"{_pick_smallest_audio(f, d) or '?'}  (mode=accurate, smallest audio)"],
        _cat_audio_count, _cat_audio_bytes,
    ),
]

ALL_COMMANDS: list[BenchCommand] = L0_COMMANDS + L1_COMMANDS + L2_COMMANDS
