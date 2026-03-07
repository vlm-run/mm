"""vlmctx wc -- count files, lines, words, tokens (TODO: deferred)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer


def wc_cmd(
    directory: Annotated[Path, typer.Argument(help="Directory to count")] = Path("."),
    kind: Annotated[Optional[str], typer.Option("--kind", "-k", help="Filter by kind")] = None,
    tokens: Annotated[
        bool, typer.Option("--tokens", help="Count tokens for LLM budgeting")
    ] = False,
) -> None:
    """Count files, lines, words, tokens (TODO)."""
    typer.echo("vlmctx wc is not yet implemented. Coming soon.", err=True)
    raise typer.Exit(1)
