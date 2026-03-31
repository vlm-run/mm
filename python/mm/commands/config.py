"""mm config -- view and manage configuration."""

from __future__ import annotations

from typing import Annotated, Optional, TypedDict

import typer

config_app = typer.Typer(
    name="config",
    help="View and manage mm configuration.",
    no_args_is_help=True,
)

profile_app = typer.Typer(
    name="profile",
    help=(
        "Manage configuration profiles.\n\n"
        "Profiles store LLM provider settings (base_url, api_key, model) so\n"
        "you can switch between providers without editing the config file.\n\n"
        "Examples:\n\n"
        "  mm config profile list\n"
        "  mm config profile add vlmrun --base-url https://api.vlm.run/v1 --model vlm-1\n"
        "  mm config profile update vlmrun --api-key sk-...\n"
        "  mm config profile use vlmrun\n"
        "  mm config profile remove vlmrun\n\n"
        "Select a profile per-command with:  mm --profile vlmrun cat photo.png -l 2\n"
        "Or via environment variable:        MM_PROFILE=vlmrun mm cat photo.png -l 2"
    ),
    no_args_is_help=True,
)
config_app.add_typer(profile_app, name="profile")


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
      mm config profile update <name> --base-url ... --model ...

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
            "[dim]Use: mm config profile update <name> --{} <value>[/dim]".format(
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


# ── Profile subcommands ────────────────────────────────────────────


@profile_app.command("list")
def profile_list(
    format: Annotated[
        Optional[str], typer.Option("--format", help="Output format: json, tsv, csv")
    ] = None,
) -> None:
    """List all configuration profiles.

    \b
    Examples:
      mm config profile list
      mm config profile list --format json
    """
    from mm.config import _read_config_file
    from mm.display import resolve_format
    from mm.profile import get_active_profile_name, get_profile_names, get_profile_section

    fmt = resolve_format(format)
    names = get_profile_names()
    active = get_active_profile_name()
    file_data = _read_config_file()

    if fmt == "json":
        from mm.display import json_dumps

        class JSONDataDict(TypedDict):
            active: str
            profiles: dict[str, dict[str, str]]

        data: JSONDataDict = {
            "active": active,
            "profiles": {name: get_profile_section(file_data, name) for name in names},
        }
        # Mask api_key values
        for p in data["profiles"].values():
            if p.get("api_key"):
                p["api_key"] = "••••"
        print(json_dumps(data))
        return

    if fmt in ("tsv", "csv"):
        sep = "\t" if fmt == "tsv" else ","
        print(f"profile{sep}active{sep}base_url{sep}model")
        for name in names:
            section = get_profile_section(file_data, name)
            is_active = "✓" if name == active else ""
            print(
                f"{name}{sep}{is_active}{sep}{section.get('base_url', '')}{sep}{section.get('model', '')}"
            )
        return

    from rich import box
    from rich.table import Table
    from rich.text import Text

    from mm.display import output_console

    tbl = Table(
        title="[bold]Profiles",
        show_lines=False,
        padding=(0, 1),
        border_style="dim",
        header_style="bold white",
        box=box.ROUNDED,
    )
    tbl.add_column("", width=2)  # active marker
    tbl.add_column("profile", style="bold")
    tbl.add_column("base_url")
    tbl.add_column("model")

    for name in names:
        section = get_profile_section(file_data, name)
        marker = Text("●", style="bold green") if name == active else Text(" ")
        style = "bold" if name == active else "dim"
        tbl.add_row(
            marker,
            Text(name, style=style),
            section.get("base_url", ""),
            section.get("model", ""),
        )
    output_console.print(tbl)


@profile_app.command("use")
def profile_use(
    name: Annotated[str, typer.Argument(help="Profile name to activate")],
) -> None:
    """Switch to a different profile.

    \b
    Examples:
      mm config profile use vlmrun
      mm config profile use default
    """
    from mm.display import output_console
    from mm.profile import set_active_profile

    try:
        path = set_active_profile(name)
        output_console.print(
            f"[green]Switched to profile:[/green] [bold]{name}[/bold]  [dim]({path})[/dim]"
        )
    except ValueError as e:
        output_console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@profile_app.command("add")
def profile_add(
    name: Annotated[str, typer.Argument(help="Profile name")],
    base_url: Annotated[str, typer.Option("--base-url", "-b", help="LLM API base URL (required)")],
    model: Annotated[str, typer.Option("--model", "-m", help="Model name (required)")],
    api_key: Annotated[str, typer.Option("--api-key", "-k", help="API key")] = "",
) -> None:
    """Add a new profile.

    \b
    Examples:
      mm config profile add vlmrun --base-url https://api.vlm.run/v1 --model vlm-1
      mm config profile add ollama --base-url http://localhost:11434 --model qwen3-vl:8b
      mm config profile add openai --base-url https://api.openai.com/v1 --api-key sk-... --model gpt-4o
    """
    from mm.display import output_console
    from mm.profile import add_profile

    try:
        path = add_profile(name, base_url=base_url, api_key=api_key, model=model)
        output_console.print(
            f"[green]Added profile:[/green] [bold]{name}[/bold]  [dim]({path})[/dim]"
        )
    except ValueError as e:
        output_console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@profile_app.command("update")
def profile_update_cmd(
    name: Annotated[str, typer.Argument(help="Profile name to update")],
    base_url: Annotated[
        Optional[str], typer.Option("--base-url", "-b", help="LLM API base URL")
    ] = None,
    api_key: Annotated[Optional[str], typer.Option("--api-key", "-k", help="API key")] = None,
    model: Annotated[Optional[str], typer.Option("--model", "-m", help="Model name")] = None,
) -> None:
    """Update one or more fields of an existing profile.

    \b
    Only the provided fields are updated; others are preserved.

    Examples:
      mm config profile update default --model qwen3-vl:8b
      mm config profile update vlmrun --api-key sk-new-key
      mm config profile update openai --base-url https://api.openai.com/v1 --model gpt-4o
    """
    from mm.display import output_console
    from mm.profile import update_profile

    try:
        path = update_profile(name, base_url=base_url, api_key=api_key, model=model)
        # Show what was updated
        updated_fields = []
        if base_url is not None:
            updated_fields.append(f"base_url={base_url}")
        if api_key is not None:
            updated_fields.append("api_key=••••")
        if model is not None:
            updated_fields.append(f"model={model}")
        output_console.print(
            f"[green]Updated profile:[/green] [bold]{name}[/bold] ({', '.join(updated_fields)})  [dim]({path})[/dim]"
        )
    except ValueError as e:
        output_console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@profile_app.command("remove")
def profile_remove(
    name: Annotated[str, typer.Argument(help="Profile name to remove")],
) -> None:
    """Remove a profile.

    \b
    Cannot remove the currently active profile — switch to another first.

    Examples:
      mm config profile remove vlmrun
    """
    from mm.display import output_console
    from mm.profile import remove_profile

    try:
        path = remove_profile(name)
        output_console.print(f"[green]Removed profile:[/green] {name}  [dim]({path})[/dim]")
    except ValueError as e:
        output_console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
