"""mm config -- view and manage configuration."""

from __future__ import annotations

from typing import Annotated, Optional

import typer

config_app = typer.Typer(
    name="config",
    help="View and manage mm configuration.",
    no_args_is_help=True,
)


@config_app.command()
def show(
    format: Annotated[
        Optional[str], typer.Option("--format", help="Output format: json, tsv, csv")
    ] = None,
) -> None:
    """Show resolved configuration with source annotations.

    \b
    Examples:
      mm config show
      mm config show --format json
    """
    from mm.config import (
        _find_config_path,
        get_full_config,
    )
    from mm.display import resolve_format

    fmt = resolve_format(format)
    cfg = get_full_config()

    if fmt == "json":
        from mm.display import json_dumps

        data = {
            "mode": {
                "fast": {
                    "whisper_model": cfg.mode_fast.whisper_model,
                    "audio_speed": cfg.mode_fast.audio_speed,
                    "beam_size": cfg.mode_fast.beam_size,
                },
                "accurate": {
                    "whisper_model": cfg.mode_accurate.whisper_model,
                    "audio_speed": cfg.mode_accurate.audio_speed,
                    "beam_size": cfg.mode_accurate.beam_size,
                },
            },
        }
        print(json_dumps(data))
        return

    if fmt in ("tsv", "csv"):
        sep = "\t" if fmt == "tsv" else ","
        print(f"key{sep}value")
        print(f"mode.fast.whisper_model{sep}{cfg.mode_fast.whisper_model}")
        print(f"mode.fast.audio_speed{sep}{cfg.mode_fast.audio_speed}")
        print(f"mode.accurate.whisper_model{sep}{cfg.mode_accurate.whisper_model}")
        print(f"mode.accurate.audio_speed{sep}{cfg.mode_accurate.audio_speed}")
        return

    from rich import box
    from rich.table import Table

    from mm.display import output_console

    config_path = _find_config_path()

    # Mode settings
    mode_tbl = Table(
        title="[bold]Extraction Modes",
        caption=str(config_path) if config_path else None,
        caption_style="dim",
        caption_justify="right",
        show_lines=False,
        padding=(0, 1),
        border_style="dim",
        header_style="bold white",
        box=box.ROUNDED,
    )
    mode_tbl.add_column("mode", style="bold")
    mode_tbl.add_column("whisper_model")
    mode_tbl.add_column("audio_speed", justify="right")
    mode_tbl.add_column("beam_size", justify="right")

    mode_tbl.add_row(
        "fast",
        cfg.mode_fast.whisper_model,
        str(cfg.mode_fast.audio_speed),
        str(cfg.mode_fast.beam_size),
    )
    mode_tbl.add_row(
        "accurate",
        cfg.mode_accurate.whisper_model,
        str(cfg.mode_accurate.audio_speed),
        str(cfg.mode_accurate.beam_size),
    )
    output_console.print(mode_tbl)


@config_app.command()
def init(
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite existing config")] = False,
) -> None:
    """Create the default config at ~/.config/mm/mm.toml.

    \b
    Examples:
      mm config init
      mm config init --force               # overwrite existing
    """
    from mm.config import _find_config_path, write_platform_config
    from mm.display import output_console

    existing = _find_config_path()
    if existing.exists() and not force:
        output_console.print(f"[yellow]Config already exists:[/yellow] {existing}")
        output_console.print("[dim]Use --force to overwrite.[/dim]")
        raise typer.Exit(1)

    path = write_platform_config()
    output_console.print(f"[green]Created[/green] {path}")


@config_app.command("reset-db")
def reset_db(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Delete all mm databases and caches.

    \b
    Removes the SQLite database under ~/.local/share/mm/.
    This action is irreversible.

    \b
    Examples:
      mm config reset-db
      mm config reset-db --yes             # skip confirmation
    """
    import shutil

    from mm.display import output_console
    from mm.store.db import MmDatabase

    targets = [MmDatabase.DB_PATH]
    # Also clean up legacy files if they exist
    legacy = MmDatabase.DB_DIR
    for name in (
        "cache.db",
        "cache.db.db",
        "cache.db.dir",
        "cache.db.bak",
        "cache.db.dat",
        "db.sock",
        "db.pid",
    ):
        p = legacy / name
        if p not in targets:
            targets.append(p)

    existing = [p for p in targets if p.exists()]
    if not existing:
        output_console.print("[dim]Nothing to reset — no databases or caches found.[/dim]")
        return

    output_console.print("[bold]The following will be deleted:[/bold]")
    for p in existing:
        output_console.print(f"  {p}")

    if not yes:
        confirm = typer.confirm(
            "\nThis leads to irreversible data loss. Continue?",
            default=False,
        )
        if not confirm:
            output_console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(1)

    for p in existing:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()

    output_console.print("[green]All databases and caches have been reset.[/green]")


@config_app.command("set")
def set_key(
    key: Annotated[str, typer.Argument(help="Key to set (e.g. mode.fast.whisper_model)")],
    value: Annotated[str, typer.Argument(help="Value to set")],
) -> None:
    """Set a mode config value.

    \b
    Mode keys:
      mm config set mode.fast.whisper_model tiny
      mm config set mode.fast.audio_speed 2.0
      mm config set mode.fast.beam_size 1
      mm config set mode.accurate.whisper_model medium
      mm config set mode.accurate.audio_speed 1.0
      mm config set mode.accurate.beam_size 5
    """
    from mm.config import update_mode_config
    from mm.display import output_console

    # Validate mode key format
    if not key.startswith("mode."):
        output_console.print(f"[red]Unknown key:[/red] {key}")
        output_console.print(
            "[dim]Valid keys: mode.{{fast,accurate}}.{{whisper_model,audio_speed,beam_size}}[/dim]"
        )
        raise typer.Exit(1)

    parts = key.split(".")
    if (
        len(parts) != 3
        or parts[1] not in ("fast", "accurate")
        or parts[2] not in ("whisper_model", "audio_speed", "beam_size")
    ):
        output_console.print(f"[red]Unknown key:[/red] {key}")
        output_console.print(
            "[dim]Valid keys: mode.{fast,accurate}.{whisper_model,audio_speed,beam_size}[/dim]"
        )
        raise typer.Exit(1)

    path = update_mode_config(key, value)
    output_console.print(f"[green]Set[/green] {key} = {value}  [dim]({path})[/dim]")
