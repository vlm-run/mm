"""vlmctx info -- summary statistics panel."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from vlmctx.context import Context


def info_cmd(
    directory: Annotated[Path, typer.Argument(help="Directory to inspect")] = Path("."),
) -> None:
    """Display summary statistics for a directory."""
    ctx = Context(directory)
    ctx.info()
