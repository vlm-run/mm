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

    fmt = resolve_format(format)
    cfg = get_full_config()

    if fmt == "json":
        from mm.display import json_dumps

        rows = get_provider_with_sources()
        data = {
            "provider": {r[0]: {"value": r[1], "source": r[2]} for r in rows},
            "mode": {
                "fast": {"whisper_model": cfg.mode_fast.whisper_model, "audio_speed": cfg.mode_fast.audio_speed, "beam_size": cfg.mode_fast.beam_size},
                "accurate": {"whisper_model": cfg.mode_accurate.whisper_model, "audio_speed": cfg.mode_accurate.audio_speed, "beam_size": cfg.mode_accurate.beam_size},
            },
        }
        print(json_dumps(data))
        return

    if fmt in ("tsv", "csv"):
        sep = "\t" if fmt == "tsv" else ","
        rows = get_provider_with_sources()
        print(f"key{sep}value{sep}source")
        for key, val, src, _ in rows:
            print(f"{key}{sep}{val}{sep}{src}")
        print(f"mode.fast.whisper_model{sep}{cfg.mode_fast.whisper_model}{sep}config")
        print(f"mode.fast.audio_speed{sep}{cfg.mode_fast.audio_speed}{sep}config")
        print(f"mode.accurate.whisper_model{sep}{cfg.mode_accurate.whisper_model}{sep}config")
        print(f"mode.accurate.audio_speed{sep}{cfg.mode_accurate.audio_speed}{sep}config")
        return

    from rich import box
    from rich.table import Table
    from rich.text import Text

    from mm.display import output_console

    SOURCE_STYLES = {
        "cli": "bold bright_green",
        "env": "bright_yellow",
        "file": "cyan",
        "default": "dim",
    }

    config_path = _find_config_path()

    tbl = Table(
        title="[bold]Provider",
        caption=str(config_path) if config_path else None,
        caption_style="dim",
        caption_justify="right",
        show_lines=False, padding=(0, 1), border_style="dim", header_style="bold white",
        box=box.ROUNDED,
    )
    tbl.add_column("key", style="bold")
    tbl.add_column("value")
    tbl.add_column("source", justify="right")

    rows = get_provider_with_sources()
    for key, val, src, _ in rows:
        style = SOURCE_STYLES.get(src, "")
        tbl.add_row(key, Text(val, style=style), Text(src, style=style))
    output_console.print(tbl)
    output_console.print()

    # Mode settings
    mode_tbl = Table(
        title="[bold]Extraction Modes",
        show_lines=False, padding=(0, 1), border_style="dim", header_style="bold white",
        box=box.ROUNDED,
    )
    mode_tbl.add_column("mode", style="bold")
    mode_tbl.add_column("whisper_model")
    mode_tbl.add_column("audio_speed", justify="right")
    mode_tbl.add_column("beam_size", justify="right")

    mode_tbl.add_row("fast", cfg.mode_fast.whisper_model, str(cfg.mode_fast.audio_speed), str(cfg.mode_fast.beam_size))
    mode_tbl.add_row("accurate", cfg.mode_accurate.whisper_model, str(cfg.mode_accurate.audio_speed), str(cfg.mode_accurate.beam_size))
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
    from mm.config import CONFIG_PATH_XDG, _find_config_path, write_platform_config
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
    key: Annotated[str, typer.Argument(help="Key to set (e.g. base_url, model, mode.fast.whisper_model)")],
    value: Annotated[str, typer.Argument(help="Value to set")],
) -> None:
    """Set a config value.

    \b
    Provider keys:
      mm config set base_url http://localhost:11434
      mm config set model qwen3-vl:8b
      mm config set api_key sk-...

    Mode keys:
      mm config set mode.fast.whisper_model tiny
      mm config set mode.fast.audio_speed 2.0
      mm config set mode.accurate.whisper_model medium
      mm config set mode.accurate.audio_speed 1.0
    """
    from mm.config import DEFAULTS, _find_config_path, _read_config_file
    from mm.display import output_console

    # Parse dotted keys for mode settings
    if key.startswith("mode."):
        parts = key.split(".")
        if len(parts) != 3 or parts[1] not in ("fast", "accurate") or parts[2] not in ("whisper_model", "audio_speed", "beam_size"):
            output_console.print(f"[red]Unknown key:[/red] {key}")
            output_console.print("[dim]Valid mode keys: mode.{fast,accurate}.{whisper_model,audio_speed,beam_size}[/dim]")
            raise typer.Exit(1)

        path = _update_mode_key(parts[1], parts[2], value)
        display_val = value
        output_console.print(f"[green]Set[/green] {key} = {display_val}  [dim]({path})[/dim]")
        return

    # Provider keys
    valid_keys = set(DEFAULTS.keys())
    if key not in valid_keys:
        output_console.print(f"[red]Unknown key:[/red] {key}")
        output_console.print(f"[dim]Valid keys: {', '.join(sorted(valid_keys))}, mode.fast.*, mode.accurate.*[/dim]")
        raise typer.Exit(1)

    from mm.config import update_config

    path = update_config(key, value)
    display_val = "••••" if key == "api_key" else value
    output_console.print(f"[green]Set[/green] {key} = {display_val}  [dim]({path})[/dim]")


def _update_mode_key(mode: str, key: str, value: str) -> str:
    """Update a mode-specific key in the config file."""
    from mm.config import _find_config_path, _read_config_file

    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

    path = _find_config_path()
    file_data = _read_config_file()

    # Ensure nested structure
    if "mode" not in file_data:
        file_data["mode"] = {}
    if mode not in file_data["mode"]:
        file_data["mode"][mode] = {}

    # Coerce types
    if key == "audio_speed":
        file_data["mode"][mode][key] = float(value)
    elif key == "beam_size":
        file_data["mode"][mode][key] = int(value)
    else:
        file_data["mode"][mode][key] = value

    # Write back — reconstruct TOML manually to preserve comments
    lines: list[str] = []

    # [provider]
    provider = file_data.get("provider", {})
    lines.append("[provider]")
    for k in ("base_url", "api_key", "model"):
        v = provider.get(k, "")
        lines.append(f'{k} = "{v}"')
    lines.append("")

    # [mode.fast] and [mode.accurate]
    for m in ("fast", "accurate"):
        mode_data = file_data.get("mode", {}).get(m, {})
        if mode_data:
            lines.append(f"[mode.{m}]")
            for mk, mv in mode_data.items():
                if isinstance(mv, (int, float)):
                    lines.append(f"{mk} = {mv}")
                else:
                    lines.append(f'{mk} = "{mv}"')
            lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return str(path)
