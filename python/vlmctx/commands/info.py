"""vlmctx info -- summary statistics panel."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer


def info_cmd(
    directory: Annotated[Path, typer.Argument(help="Directory to inspect")] = Path("."),
) -> None:
    """Display summary statistics for a directory."""
    from vlmctx.context import Context

    ctx = Context(directory)
    ctx.info()
