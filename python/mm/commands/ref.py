"""``mm ref`` -- resolve and inspect global ``<session_id>/<ref_id>`` handles.

Usage::

    mm ref my-session-uuid/img_a1b2c3              # show one file row
    mm ref --session my-session-uuid               # list all files in a session
    mm ref my-session/img_a1b2c3 --format json     # machine-readable output

Refs are produced by saving a :class:`mm.Context` constructed with
``session_id="..."``. The handle resolves to the same row globally —
across users, machines, and absolute paths — by looking up the row
directly in the mm SQLite database via ``(session_id, ref_id)``.
"""

from __future__ import annotations

import json as json_mod
from typing import Annotated, Optional

import typer

from mm.utils import BaseFormat


def ref_cmd(
    handle: Annotated[
        Optional[str],
        typer.Argument(help="Global ref of the form '<session_id>/<ref_id>'"),
    ] = None,
    session: Annotated[
        Optional[str],
        typer.Option("--session", "-s", help="List all refs in a given session id"),
    ] = None,
    format: Annotated[
        Optional[BaseFormat],
        typer.Option("--format", "-f", help="Output format"),
    ] = None,
) -> None:
    """Resolve a ``<session_id>/<ref_id>`` handle to its file row."""
    from mm.refs import GlobalRef
    from mm.store import MmDatabase

    db = MmDatabase()
    fmt = format or BaseFormat.rich

    if session and not handle:
        rows = db.list_session_files(session)
        _print_rows(rows, fmt=fmt, title=f"session={session}")
        if not rows:
            raise typer.Exit(code=1)
        return

    if not handle:
        raise typer.BadParameter(
            "Provide either a global ref ('<session_id>/<ref_id>') or --session <id>."
        )

    try:
        parsed = GlobalRef.parse(handle)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    row = db.get_file_by_ref(parsed.session_id, parsed.ref_id)
    if row is None:
        typer.echo(f"No file found for ref {handle!r}", err=True)
        raise typer.Exit(code=1)

    _print_rows([row], fmt=fmt, title=str(parsed))


def _print_rows(rows: list[dict], *, fmt: BaseFormat, title: str) -> None:
    if fmt == BaseFormat.json:
        typer.echo(json_mod.dumps(rows, indent=2, default=str))
        return

    if fmt in (BaseFormat.tsv, BaseFormat.csv):
        if not rows:
            return
        sep = "\t" if fmt == BaseFormat.tsv else ","
        cols = ["session_id", "ref_id", "kind", "uri", "size"]
        typer.echo(sep.join(cols))
        for r in rows:
            typer.echo(sep.join(str(r.get(c, "")) for c in cols))
        return

    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title=title, show_lines=False)
    for col in ("ref_id", "kind", "size", "uri"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            str(r.get("ref_id") or "-"),
            str(r.get("kind") or "-"),
            str(r.get("size") or 0),
            str(r.get("uri") or "-"),
        )
    console.print(table)
