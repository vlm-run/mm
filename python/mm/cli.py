"""mm CLI -- Unix-philosophy multi-modal context management."""

from __future__ import annotations

from typing import Annotated, Optional

import typer

from mm.commands import bench, cat, find, grep, sql, wc
from mm.commands.config import config_app

app = typer.Typer(
    name="mm",
    help="High-performance multi-modal context management.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


@app.callback()
def _main(
    base_url: Annotated[Optional[str], typer.Option("--base-url", help="LLM API base URL")] = None,
    api_key: Annotated[Optional[str], typer.Option("--api-key", help="LLM API key")] = None,
    model: Annotated[Optional[str], typer.Option("--model", help="LLM model name")] = None,
    color: Annotated[
        str, typer.Option("--color", help="Color output: auto, always, never")
    ] = "auto",
) -> None:
    """High-performance multi-modal context management."""
    from mm.config import set_cli_overrides
    from mm.display import set_color_mode

    set_cli_overrides(base_url=base_url, api_key=api_key, model=model)
    if color != "auto":
        set_color_mode(color)


app.command(name="bench")(bench.bench_cmd)
app.command(name="find")(find.find_cmd)
app.command(name="cat")(cat.cat_cmd)
app.command(name="grep")(grep.grep_cmd)
app.command(name="sql")(sql.sql_cmd)
app.command(name="wc")(wc.wc_cmd)
app.add_typer(config_app, name="config")


if __name__ == "__main__":
    app()
