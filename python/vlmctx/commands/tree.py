"""vlmctx tree -- hierarchical directory tree (TODO: deferred)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer


def tree_cmd(
    directory: Annotated[Path, typer.Argument(help="Directory to display")] = Path("."),
    kind: Annotated[Optional[str], typer.Option("--kind", "-k", help="Filter by kind")] = None,
    depth: Annotated[int, typer.Option("-L", help="Max depth")] = 3,
) -> None:
    """Hierarchical directory tree with file metadata (TODO)."""
    typer.echo("vlmctx tree is not yet implemented. Coming soon.", err=True)
    raise typer.Exit(1)
