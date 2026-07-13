"""Rich formatting helpers for terminal output."""

from __future__ import annotations

import functools
import sys
from time import perf_counter
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from pyarrow import Table
    from rich.console import Console


# Color mode override: None = auto (default), True = always, False = never.
_color_override: bool | None = None


def set_color_mode(mode: str) -> None:
    """Set color output mode: 'auto', 'always', or 'never'."""
    global _color_override  # noqa: PLW0603
    if mode == "always":
        _color_override = True
    elif mode == "never":
        _color_override = False
    else:
        _color_override = None
    # Clear cached consoles so they pick up the new setting.
    _get_console.cache_clear()
    _get_output_console.cache_clear()


@functools.cache
def _get_console() -> Console:
    from rich.console import Console

    kwargs: dict[str, Any] = {"stderr": True}
    if _color_override is not None:
        kwargs["force_terminal"] = _color_override
        kwargs["no_color"] = not _color_override
    return Console(**kwargs)


@functools.cache
def _get_output_console() -> Console:
    from rich.console import Console

    kwargs: dict[str, Any] = {}
    if _color_override is not None:
        kwargs["force_terminal"] = _color_override
        kwargs["no_color"] = not _color_override
    return Console(**kwargs)


class _LazyConsole:
    """Descriptor that defers Console creation until first access."""

    def __init__(self, factory):
        self._factory = factory

    def __getattr__(self, name):
        return getattr(self._factory(), name)


console = _LazyConsole(_get_console)
output_console = _LazyConsole(_get_output_console)

KIND_ICONS: dict[str, str] = {
    "image": "img",
    "video": "vid",
    "document": "doc",
    "code": "src",
    "other": "---",
}


def resolve_stderr(stderr: bool = False):
    return sys.stderr if stderr else None


def json_dumps(obj: Any, *, indent: int | None = None) -> str:
    """Serialize to JSON — compact when piped (saves tokens), pretty in TTY.

    When *indent* is not given explicitly the function checks whether stdout
    is a TTY.  TTY → ``indent=2`` for human readability; piped → no indent
    for maximum token-efficiency when feeding output to other LLMs.
    """
    import json

    from mm.pipe import is_piped_output

    if indent is None:
        indent = None if is_piped_output() else 2
    return json.dumps(obj, indent=indent, default=str, ensure_ascii=False)


def resolve_format(fmt: str | None) -> str:
    """Resolve the effective output format.

    Priority: explicit ``--format`` flag > pipe detection > rich.

    Returns one of: ``"json"``, ``"tsv"``, ``"csv"``, ``"text"``,
    ``"dataset-jsonl"``, ``"dataset-hf"``, ``"rich"``.
    """
    from mm.pipe import is_piped_output

    if fmt:
        return fmt
    return "tsv" if is_piped_output() else "rich"


def _strval(v: object) -> str:
    return "" if v is None else str(v)


def emit_tsv(
    rows: list[dict],
    columns: list[str] | None = None,
    *,
    stderr: bool = False,
) -> None:
    """Print rows as TSV with a header line. ``None`` cells render empty."""
    if not rows:
        return
    cols = columns or list(rows[0].keys())
    print("\t".join(cols), file=resolve_stderr(stderr))
    for row in rows:
        print("\t".join(_strval(row.get(c)) for c in cols), file=resolve_stderr(stderr))


def emit_csv(
    rows: list[dict],
    columns: list[str] | None = None,
    *,
    stderr: bool = False,
) -> None:
    """Print rows as CSV with a header line. ``None`` cells render empty."""
    import csv
    import io

    if not rows:
        return
    cols = columns or list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(cols)
    for row in rows:
        writer.writerow(_strval(row.get(c)) for c in cols)
    print(buf.getvalue(), end="", file=resolve_stderr(stderr))


def emit_rows(
    fmt: str,
    rows: list[dict],
    *,
    output_dir: str = "mm_dataset",
    stderr: bool = False,
) -> None:
    """Unified emitter for json, pretty-json, dataset-jsonl, and dataset-hf formats.

    Dispatches to the appropriate serializer based on *fmt*. ``json``
    is auto-pretty/-compact based on TTY detection (compact when piped);
    ``pretty-json`` always indents with ``indent=2`` regardless of where
    stdout points -- useful when piping into a markdown fence or
    capturing into a recording file where line-broken JSON renders far
    more readably than a single-line escape soup.
    """
    import json

    if fmt == "json":
        print(json_dumps(rows), file=resolve_stderr(stderr))
    elif fmt == "pretty-json":
        print(
            json.dumps(rows, indent=2, default=str, ensure_ascii=False), file=resolve_stderr(stderr)
        )
    elif fmt == "dataset-jsonl":
        _emit_dataset_jsonl(rows, stderr=stderr)
    elif fmt == "dataset-hf":
        _emit_dataset_hf(rows, output_dir=output_dir)


def _emit_dataset_jsonl(
    rows: list[dict],
    *,
    stderr: bool = False,
) -> None:
    """Print rows as newline-delimited JSON (one JSON object per line).

    Suitable for ``datasets.load_dataset("json", data_files=...)``.
    """
    import json

    for row in rows:
        print(json.dumps(row, default=str, ensure_ascii=False), file=resolve_stderr(stderr))


def _emit_dataset_hf(rows: list[dict], output_dir: str = "mm_dataset") -> None:
    """Save rows as a HuggingFace Dataset (Parquet + metadata on disk).

    Saves to *output_dir* and prints the path to stderr.

    Requires: pip install mm-ctx[experimental]
    """
    from pathlib import Path

    from mm.deps import try_import_or_raise

    datasets_mod = try_import_or_raise("datasets", extra="experimental", package="datasets")
    Dataset = datasets_mod.Dataset

    if not rows:
        import sys

        print("No data to export.", file=sys.stderr)
        return

    ds = Dataset.from_list(rows)
    out = Path(output_dir)
    ds.save_to_disk(str(out))
    import sys

    print(f"Saved HuggingFace Dataset ({len(rows)} rows) → {out.resolve()}", file=sys.stderr)


def format_size(size_bytes: int | float) -> str:
    """Format bytes as human-readable size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            if unit == "B":
                return f"{int(size_bytes)} B"
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def format_number(n: int | float) -> str:
    """Format a large number with human-readable suffix (K, M, B, T)."""
    if isinstance(n, float):
        if n >= 1_000_000_000:
            return f"{n / 1_000_000_000:.1f}B"
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}K"
        return f"{n:,.1f}"
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,}"


def _style_cell(col: str, val: Any):
    """Apply per-column styling to a cell value."""
    from rich.text import Text

    if val is None:
        return Text("")

    if col == "size" and isinstance(val, (int, float)):
        return Text(format_size(int(val)), justify="right")

    if col in ("depth", "line_count", "word_count", "pages"):
        return Text(str(val), justify="right")

    if col == "is_binary":
        return Text("yes" if val else "no")

    if col in ("modified", "created"):
        s = str(val)
        return Text(s[:19] if len(s) > 19 else s)

    return Text(str(val))


def autoselect_cols(table: Table):
    """auto select a subset of columns to display based on terminal width, prioritizing the most useful ones."""
    import shutil

    cols_set: list[str] = []
    term_width = shutil.get_terminal_size((120, 40)).columns
    all_cols = table.column_names
    # ~12 chars minimum per column, cap at 10 for readability
    max_cols = min(max(term_width // 12, 4), 10)

    if len(all_cols) > max_cols:
        # In order of display relevance/significance
        _PREFERRED = [
            "uri",
            "name",
            "ext",
            "size",
            "kind",
            "mime",
            "depth",
            "modified",
            "content_hash",
            "dimensions",
            "language",
            "duration_s",
            "pages",
            "line_count",
            "parent",
        ]

        for c in _PREFERRED:
            if c in all_cols and len(cols_set) < max_cols:
                cols_set.append(c)
        # Fill remaining with any columns not yet included
        for c in all_cols:
            if c not in cols_set and len(cols_set) < max_cols:
                cols_set.append(c)

    return cols_set


def arrow_table_to_rich(
    table: Table,
    columns: list[str] | None = None,
    limit: int | None = None,
    title: str | None = None,
):
    """Convert a PyArrow table to a Rich table for terminal display."""
    from rich.table import Table

    total = table.num_rows
    num_rows = total if limit is None else min(limit, total)
    if columns is None:
        columns = autoselect_cols(table)

    # Build caption with row count + total size if available
    parts = []
    if limit is not None and total > limit:
        parts.append(f"showing {num_rows} of {total}")
    elif total > 0:
        parts.append(f"{total:,} file{'s' if total != 1 else ''}")
    if "size" in table.column_names and total > 0:
        total_bytes = sum(int(r.as_py()) for r in table.column("size") if r.as_py() is not None)
        if total_bytes > 0:
            parts.append(format_size(total_bytes))
    subtitle = "  ".join(parts) if parts else None

    from rich import box

    rich_table = Table(
        title=title,
        caption=subtitle,
        caption_style="dim",
        caption_justify="right",
        show_lines=False,
        padding=(0, 1),
        header_style="bold",
        box=box.ROUNDED,
    )

    cols = columns or table.column_names
    nowrap_cols = {"ext", "mime", "kind", "size", "depth", "parent", "is_binary"}
    wrap_cols = {"path", "uri", "file_uri", "name"}
    min_widths = {"size": 8, "kind": 8, "ext": 5}
    for col in cols:
        justify: Literal["left", "right"] = (
            "right"
            if col
            in (
                "size",
                "line_count",
                "word_count",
                "depth",
                "pages",
                "n",
                "mb",
                "avg_kb",
                "total_mb",
                "count",
            )
            else "left"
        )
        rich_table.add_column(
            col,
            justify=justify,
            no_wrap=col in nowrap_cols,
            overflow="fold" if col in wrap_cols else "ellipsis",
            min_width=min_widths.get(col),
        )

    for i in range(num_rows):
        row_vals = []
        for col in cols:
            val = table.column(col)[i].as_py()
            row_vals.append(_style_cell(col, val))
        rich_table.add_row(*row_vals)

    return rich_table


def info_panel(stats: dict[str, Any], title: str = "mm"):
    """Build a Rich panel with summary statistics."""
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.text import Text

    parts: list[Any] = []

    root = stats.pop("Root", "")
    total_files = stats.pop("Files", 0)
    total_size = stats.pop("Total Size", "")
    top_ext = stats.pop("Top Extensions", "")

    header = Text()
    header.append(f"  {total_files}", style="bold")
    header.append(" files  ", style="bold")
    header.append(f"{total_size}", style="bold")
    header.append(f"\n  {root}\n")
    parts.append(header)

    parts.append(Rule())

    kind_text = Text()
    for kind_name, count in stats.items():
        kind_text.append(f"  {kind_name:<12}", style="bold")
        kind_text.append(f"{count:>5}\n")
    parts.append(kind_text)

    parts.append(Rule())

    ext_text = Text()
    ext_text.append(f"  {top_ext}")
    parts.append(ext_text)

    from rich.console import Group

    content = Group(*parts)
    from rich import box

    return Panel(
        content,
        title=f"[bold]{title}[/bold]",
        title_align="left",
        expand=False,
        padding=(1, 2),
        box=box.ROUNDED,
    )


def format_time(elapsed_ms: float) -> str:
    """Format elapsed time with adaptive ms/s units"""
    if elapsed_ms >= 1000:
        return f"{elapsed_ms / 1000:,.1f}s"
    return f"{elapsed_ms:,.0f}ms"


def display_elapsed(
    start_time: float, total_bytes: int = 0, cached: bool = False, *, prefix: str | None = None
) -> None:
    """display elapsed time since start_time with throughput metrics.

    Only prints when the command completed successfully.

    Args:
        start_time: start time in seconds (from time.perf_counter())
        total_bytes: total bytes processed (for throughput calculation)
        cached: whether the result was served from cache
        prefix: optional leading text (e.g. ``"took "`` for grep)
    """
    assert start_time > 0
    elapsed_ms = (perf_counter() - start_time) * 1000
    elapsed_s = elapsed_ms / 1000.0
    output_parts: list[str] = []
    if cached:
        output_parts.append("cached")
    output_parts.append(format_time(elapsed_ms))

    if total_bytes > 0:
        size_str = format_size(total_bytes)
        output_parts.append(size_str)

        throughput_bytes_s = total_bytes / elapsed_s if elapsed_s > 0 else 0

        if throughput_bytes_s < 1024:
            throughput_str = f"{throughput_bytes_s:.1f} B/s"
        elif throughput_bytes_s < 1024 * 1024:
            throughput_str = f"{throughput_bytes_s / 1024:.1f} KB/s"
        elif throughput_bytes_s < 1024 * 1024 * 1024:
            throughput_str = f"{throughput_bytes_s / (1024 * 1024):.1f} MB/s"
        else:
            throughput_str = f"{throughput_bytes_s / (1024 * 1024 * 1024):.1f} GB/s"

        output_parts.append(throughput_str)

    output_text = " \u2022 ".join(output_parts)
    output_text = f"{prefix} {output_text}" if prefix else output_text
    console.print(output_text)


def display_elapsed_wrapper(start_time: float, prefix: str | None = None):
    successful = [True]
    original_exit = sys.exit

    def check_exit(code: int | None = 0):
        if code not in (None, 0):
            successful[0] = False
        original_exit(code)

    def display_if_successful():
        if successful[0]:
            total_bytes = 0
            cached = False
            try:
                from mm.commands import cat as cat_module

                total_bytes = getattr(cat_module, "_total_bytes_processed", 0)
                cached = getattr(cat_module, "_was_cached", False)
            except (ImportError, AttributeError):
                pass

            display_elapsed(start_time, total_bytes, cached, prefix=prefix)

            try:
                from mm.commands import cat as cat_module

                for msg in getattr(cat_module, "_report_output", []):
                    console.print(f"[dim]{msg}[/dim]")
            except (ImportError, AttributeError):
                pass

    return check_exit, display_if_successful


def root_progress():
    if not _get_console().is_terminal:
        return

    import atexit

    from rich.live import Live
    from rich.spinner import Spinner

    _real_stdout = sys.stdout
    _live = Live(
        Spinner("dots", style="green"),
        console=_get_console(),
        redirect_stdout=False,
        transient=True,
    )
    _live.start()

    class _StopOnWrite:
        def write(self, s: str) -> int:
            sys.stdout = _real_stdout
            _live.stop()
            return _real_stdout.write(s)

        def flush(self) -> None:
            _real_stdout.flush()

        def __getattr__(self, name: str):
            return getattr(_real_stdout, name)

    sys.stdout = _StopOnWrite()
    atexit.register(_live.stop)
