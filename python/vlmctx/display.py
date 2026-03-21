"""Rich formatting helpers for terminal output."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pyarrow as pa
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

KIND_STYLES: dict[str, str] = {
    "image": "green",
    "video": "magenta",
    "document": "cyan",
    "code": "yellow",
    "other": "dim",
}

KIND_ICONS: dict[str, str] = {
    "image": "img",
    "video": "vid",
    "document": "doc",
    "code": "src",
    "other": "---",
}


def json_dumps(obj: Any, *, indent: int | None = None) -> str:
    """Serialize to JSON — compact when piped (saves tokens), pretty in TTY.

    When *indent* is not given explicitly the function checks whether stdout
    is a TTY.  TTY → ``indent=2`` for human readability; piped → no indent
    for maximum token-efficiency when feeding output to other LLMs.
    """
    import json

    from vlmctx.pipe import is_piped_output

    if indent is None:
        indent = None if is_piped_output() else 2
    return json.dumps(obj, indent=indent, default=str, ensure_ascii=False)


def resolve_format(fmt: str | None) -> str:
    """Resolve the effective output format.

    Priority: explicit ``--format`` flag > pipe detection > rich.

    Returns one of: ``"json"``, ``"tsv"``, ``"csv"``, ``"text"``, ``"rich"``.
    """
    from vlmctx.pipe import is_piped_output

    if fmt:
        return fmt
    return "tsv" if is_piped_output() else "rich"


def emit_tsv(rows: list[dict], columns: list[str] | None = None) -> None:
    """Print rows as TSV with a header line."""
    import csv
    import io

    if not rows:
        return
    cols = columns or list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter="\t")
    writer.writerow(cols)
    for row in rows:
        writer.writerow(str(row.get(c, "")) for c in cols)
    print(buf.getvalue(), end="")


def emit_csv(rows: list[dict], columns: list[str] | None = None) -> None:
    """Print rows as CSV with a header line."""
    import csv
    import io

    if not rows:
        return
    cols = columns or list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(cols)
    for row in rows:
        writer.writerow(str(row.get(c, "")) for c in cols)
    print(buf.getvalue(), end="")


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
        return Text("", style="dim")

    if col == "size" and isinstance(val, (int, float)):
        return Text(format_size(int(val)), style="bright_blue", justify="right")

    if col == "kind":
        style = KIND_STYLES.get(str(val), "dim")
        return Text(str(val), style=style)

    if col in ("mime", "ext"):
        return Text(str(val), style="dim cyan")

    if col == "path":
        return Text(str(val), style="white")

    if col == "name":
        return Text(str(val), style="bold")

    if col in ("depth", "line_count", "word_count", "pages"):
        return Text(str(val), style="bright_blue", justify="right")

    if col == "is_binary":
        return Text("yes" if val else "no", style="dim")

    if col in ("modified", "created"):
        s = str(val)
        return Text(s[:19] if len(s) > 19 else s, style="dim")

    return Text(str(val))


def arrow_table_to_rich(
    table: pa.Table,
    columns: list[str] | None = None,
    limit: int | None = None,
    title: str | None = None,
):
    """Convert a PyArrow table to a Rich table for terminal display."""
    from rich.table import Table

    total = table.num_rows
    num_rows = total if limit is None else min(limit, total)

    subtitle = None
    if limit is not None and total > limit:
        subtitle = f"showing {num_rows} of {total}"
    elif total > 0:
        subtitle = f"{total} row{'s' if total != 1 else ''}"

    from rich import box

    rich_table = Table(
        title=title,
        caption=subtitle,
        caption_style="dim",
        show_lines=False,
        padding=(0, 1),
        border_style="dim",
        header_style="bold",
        box=box.ROUNDED,
    )

    cols = columns or table.column_names
    nowrap_cols = {"ext", "mime", "kind", "size", "depth", "parent", "is_binary"}
    min_widths = {"size": 8, "kind": 8, "ext": 5}
    for col in cols:
        justify = (
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
        style = "dim" if col in ("modified", "created") else None
        rich_table.add_column(
            col,
            justify=justify,
            style=style,
            no_wrap=col in nowrap_cols,
            min_width=min_widths.get(col),
        )

    for i in range(num_rows):
        row_vals = []
        for col in cols:
            val = table.column(col)[i].as_py()
            row_vals.append(_style_cell(col, val))
        rich_table.add_row(*row_vals)

    return rich_table


def info_panel(stats: dict[str, Any], title: str = "vlmctx"):
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
    header.append(f"  {total_files}", style="bold bright_blue")
    header.append(" files  ", style="bold")
    header.append(f"{total_size}", style="bold bright_green")
    header.append(f"\n  {root}\n", style="dim")
    parts.append(header)

    parts.append(Rule(style="dim"))

    kind_text = Text()
    for kind_name, count in stats.items():
        color = KIND_STYLES.get(kind_name.lower(), "white")
        kind_text.append(f"  {kind_name:<12}", style=f"bold {color}")
        kind_text.append(f"{count:>5}\n", style="bright_blue")
    parts.append(kind_text)

    parts.append(Rule(style="dim"))

    ext_text = Text()
    ext_text.append(f"  {top_ext}", style="dim")
    parts.append(ext_text)

    from rich.console import Group

    content = Group(*parts)
    from rich import box

    return Panel(content, title=f"[bold]{title}[/bold]", title_align="left", expand=False, padding=(1, 2), box=box.ROUNDED)
