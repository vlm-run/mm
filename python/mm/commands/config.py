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
    """Show resolved configuration with source annotations."""
    from mm.config import (
        _find_config_path,
        get_full_config,
        get_provider_with_sources,
    )
    from mm.display import resolve_format
    from mm.profile import get_active_profile_name, get_profile_names

    fmt = resolve_format(format)
    cfg = get_full_config()
    active_profile = get_active_profile_name()
    all_profiles = get_profile_names()

    if fmt == "json":
        from mm.display import json_dumps

        rows = get_provider_with_sources()
        data = {
            "active_profile": active_profile,
            "profiles": all_profiles,
            "provider": {r[0]: r[1] for r in rows},
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
        rows = get_provider_with_sources()
        print(f"key{sep}value")
        print(f"active_profile{sep}{active_profile}")
        for key, val, _src, _ in rows:
            print(f"{key}{sep}{val}")
        print(f"mode.fast.whisper_model{sep}{cfg.mode_fast.whisper_model}")
        print(f"mode.fast.audio_speed{sep}{cfg.mode_fast.audio_speed}")
        print(f"mode.accurate.whisper_model{sep}{cfg.mode_accurate.whisper_model}")
        print(f"mode.accurate.audio_speed{sep}{cfg.mode_accurate.audio_speed}")
        return

    from rich import box
    from rich.table import Table
    from rich.text import Text

    from mm.display import output_console

    config_path = _find_config_path()

    # Profile info line
    profiles_display = ", ".join(
        f"[bold green]{p}[/bold green]" if p == active_profile else f"[dim]{p}[/dim]"
        for p in all_profiles
    )
    output_console.print(f"[bold]Profile:[/bold] {active_profile}  [dim]({profiles_display})[/dim]")
    output_console.print()

    tbl = Table(
        title=f"[bold]Provider[/bold] [dim](profile: {active_profile})[/dim]",
        caption=str(config_path) if config_path else None,
        caption_style="dim",
        caption_justify="right",
        show_lines=False,
        padding=(0, 1),
        border_style="dim",
        header_style="bold white",
        box=box.ROUNDED,
    )
    tbl.add_column("key", style="bold")
    tbl.add_column("value")

    rows = get_provider_with_sources()
    for key, val, _src, _ in rows:
        tbl.add_row(key, Text(val, style="cyan"))
    output_console.print(tbl)
    output_console.print()

    # Mode settings
    mode_tbl = Table(
        title="[bold]Extraction Modes",
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
    """Create platform-aware config at ~/.config/mm/mm.toml.

    \b
    macOS:  Ollama + qwen3.5:0.8b
    Linux:  vLLM + Qwen/Qwen3.5-0.8B (placeholder)
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


@config_app.command("set")
def set_key(
    key: Annotated[str, typer.Argument(help="Key to set (e.g. mode.fast.whisper_model)")],
    value: Annotated[str, typer.Argument(help="Value to set")],
) -> None:
    """Set a mode config value.

    \b
    Provider keys (base_url, api_key, model) are set per-profile:
      mm profile update <name> --base-url ... --model ...

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
    from mm.profile import PROFILE_KEYS

    # Reject provider keys — redirect to profile update
    if key in PROFILE_KEYS:
        output_console.print(f"[red]Provider key '{key}' must be set per-profile.[/red]")
        output_console.print(
            "[dim]Use: mm profile update <name> --{} <value>[/dim]".format(
                key.replace("_", "-")
            )
        )
        raise typer.Exit(1)

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
