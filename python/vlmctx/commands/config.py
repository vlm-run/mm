"""vlmctx config -- view and manage configuration."""

from __future__ import annotations

from typing import Annotated

import typer

config_app = typer.Typer(
    name="config",
    help="View and manage vlmctx configuration.",
    no_args_is_help=True,
)


@config_app.command()
def show(
    json_output: Annotated[bool, typer.Option("--json", help="JSON output")] = False,
) -> None:
    """Show resolved configuration with source annotations."""
    from vlmctx.config import CONFIG_PATH, get_provider_with_sources
    from vlmctx.pipe import is_piped_output

    rows = get_provider_with_sources()

    if json_output:
        import json

        print(json.dumps(
            {r[0]: {"value": r[1], "source": r[2]} for r in rows},
            indent=2,
        ))
        return

    if is_piped_output():
        print("key\tvalue\tsource")
        for key, val, src, _ in rows:
            print(f"{key}\t{val}\t{src}")
        return

    from rich.table import Table
    from rich.text import Text

    from vlmctx.display import output_console

    SOURCE_STYLES = {
        "cli": "bold bright_green",
        "env": "bright_yellow",
        "file": "cyan",
        "default": "dim",
    }

    from rich import box

    tbl = Table(
        caption=f"[dim]{CONFIG_PATH}[/dim]",
        show_lines=False, padding=(0, 1), border_style="dim", header_style="bold",
        box=box.ROUNDED,
    )
    tbl.add_column("key", style="bold")
    tbl.add_column("value")
    tbl.add_column("source", justify="right")

    for key, val, src, _ in rows:
        style = SOURCE_STYLES.get(src, "")
        tbl.add_row(key, Text(val, style=style), Text(src, style=style))

    output_console.print(tbl)


@config_app.command()
def init(
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite existing config")] = False,
) -> None:
    """Create ~/.vlmctx/config.toml with defaults."""
    from vlmctx.config import CONFIG_PATH, DEFAULTS, write_config

    if CONFIG_PATH.exists() and not force:
        from vlmctx.display import output_console

        output_console.print(f"[yellow]Config already exists:[/yellow] {CONFIG_PATH}")
        output_console.print("[dim]Use --force to overwrite.[/dim]")
        raise typer.Exit(1)

    path = write_config(**DEFAULTS)

    from vlmctx.display import output_console

    output_console.print(f"[green]Created[/green] {path}")


@config_app.command("set")
def set_key(
    key: Annotated[str, typer.Argument(help="Key to set (base_url, api_key, model)")],
    value: Annotated[str, typer.Argument(help="Value to set")],
) -> None:
    """Set a provider config value.

    \b
    Examples:
      vlmctx config set model qwen3-vl:8b
      vlmctx config set base_url https://api.openai.com/v1
      vlmctx config set api_key sk-...
    """
    from vlmctx.config import DEFAULTS, update_config

    valid_keys = set(DEFAULTS.keys())
    if key not in valid_keys:
        from vlmctx.display import output_console

        output_console.print(f"[red]Unknown key:[/red] {key}")
        output_console.print(f"[dim]Valid keys: {', '.join(sorted(valid_keys))}[/dim]")
        raise typer.Exit(1)

    path = update_config(key, value)

    from vlmctx.display import output_console

    display_val = "••••" if key == "api_key" else value
    output_console.print(f"[green]Set[/green] {key} = {display_val}  [dim]({path})[/dim]")
