"""vlmctx context -- LLM-ready context builder (TODO: deferred, needs design)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer


def context_cmd(
    directory: Annotated[Path, typer.Argument(help="Directory to build context from")] = Path("."),
    max_tokens: Annotated[Optional[int], typer.Option("--max-tokens", "-m", help="Token budget")] = None,
    kind: Annotated[Optional[str], typer.Option("--kind", "-k", help="Filter by kind")] = None,
    ext: Annotated[Optional[str], typer.Option("--ext", "-e", help="Filter by extension")] = None,
    format: Annotated[str, typer.Option("--format", "-f", help="Output format (markdown, xml)")] = "markdown",
) -> None:
    """Build LLM-ready context payload (TODO -- needs design)."""
    typer.echo("vlmctx context is not yet implemented. Needs design.", err=True)
    raise typer.Exit(1)
