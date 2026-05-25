"""mm profile -- manage configuration profiles."""

from __future__ import annotations

from typing import Annotated, Optional, TypedDict

import typer

from mm.utils import BaseFormat

profile_app = typer.Typer(
    name="profile",
    help=(
        "Manage configuration profiles.\n\n"
        "Profiles store LLM API settings (base_url, api_key, model) so\n"
        "you can switch between endpoints/models without editing the config file.\n\n"
        "Examples:\n\n"
        "  mm profile list\n"
        "  mm profile use ollama\n"
        "  mm profile use gemini\n"
        "  mm profile update ollama --model qwen3.5:0.8\n"
        "  mm profile add openai --base-url https://api.openai.com/v1 --model gpt-4o\n"
        "  mm profile remove openai\n\n"
        "Select a profile per-command with:  mm --profile openrouter cat photo.png -m accurate\n"
        "Or via environment variable:        MM_PROFILE=ollama mm cat photo.png -m accurate\n"
        "Resolution order: CLI --profile > MM_PROFILE env > active_profile > 'ollama'"
    ),
    no_args_is_help=True,
)


@profile_app.command("list")
def profile_list(
    format: Annotated[
        Optional[BaseFormat],
        typer.Option("--format", "-f", help="Output format: rich (default), json, tsv, csv"),
    ] = None,
) -> None:
    """List all configuration profiles.

    \b
    Examples:
      mm profile list
      mm profile list --format json
    """
    from mm.display import resolve_format
    from mm.profile import (
        get_active_profile_name,
        get_profile_names,
        get_profile_section,
        load_profile_config,
    )

    fmt = resolve_format(format.value if format else None)
    names = get_profile_names()
    active = get_active_profile_name()
    file_data = load_profile_config()

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
        title="[bold]Profiles[/bold]",
        show_lines=False,
        padding=(0, 1),
        header_style="bold",
        box=box.ROUNDED,
    )
    tbl.add_column("", width=2)
    tbl.add_column("profile")
    tbl.add_column("base_url")
    tbl.add_column("model")

    for name in names:
        section = get_profile_section(file_data, name)
        marker = Text("●", style="bold") if name == active else Text(" ")
        style = "bold" if name == active else ""
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
      mm profile use openrouter
      mm profile use ollama
      mm profile use gemini
    """
    from mm.display import output_console
    from mm.profile import set_active_profile

    try:
        path = set_active_profile(name)
        output_console.print(f"Switched to profile: [bold]{name}[/bold]  ({path})")
    except ValueError as e:
        output_console.print(f"{e}")
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
      mm profile add openrouter --base-url https://openrouter.ai/api/v1 --model Qwen/Qwen3.5-0.8B
      mm profile add ollama --base-url http://localhost:11434 --model qwen3-vl:8b
      mm profile add openai --base-url https://api.openai.com/v1 --api-key sk-... --model gpt-4o
    """
    from mm.display import output_console
    from mm.profile import add_profile

    try:
        path = add_profile(name, base_url=base_url, api_key=api_key, model=model)
        output_console.print(f"Added profile: [bold]{name}[/bold]  ({path})")
    except ValueError as e:
        output_console.print(f"{e}")
        raise typer.Exit(1)


@profile_app.command("update")
def profile_update(
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
      mm profile update ollama --model qwen3.5:0.8
      mm profile update ollama --api-key sk-new-key
      mm profile update openai --base-url https://api.openai.com/v1 --model gpt-4o
    """
    from mm.display import output_console
    from mm.profile import update_profile

    try:
        path = update_profile(name, base_url=base_url, api_key=api_key, model=model)
        updated_fields = []
        if base_url is not None:
            updated_fields.append(f"base_url={base_url}")
        if api_key is not None:
            updated_fields.append("api_key=••••")
        if model is not None:
            updated_fields.append(f"model={model}")
        output_console.print(
            f"Updated profile: [bold]{name}[/bold] ({', '.join(updated_fields)})  ({path})"
        )
    except ValueError as e:
        output_console.print(f"{e}")
        raise typer.Exit(1)


@profile_app.command("clone")
def profile_clone(
    source: Annotated[str, typer.Argument(help="Profile to clone from")],
    dest: Annotated[str, typer.Argument(help="Name for the new profile")],
    base_url: Annotated[
        Optional[str], typer.Option("--base-url", "-b", help="Override base URL")
    ] = None,
    api_key: Annotated[
        Optional[str], typer.Option("--api-key", "-k", help="Override API key")
    ] = None,
    model: Annotated[
        Optional[str], typer.Option("--model", "-m", help="Override model name")
    ] = None,
) -> None:
    """Clone a profile, optionally overriding individual fields.

    \b
    All fields are copied from the source profile. Any option provided on the
    command line overwrites the corresponding field in the clone; unspecified
    fields inherit the source value unchanged.

    Examples:
      mm profile clone ollama my-ollama                          # exact copy
      mm profile clone ollama my-ollama --model qwen3-vl:8b     # different model
      mm profile clone openai openai-dev --api-key sk-dev-...   # different key
      mm profile clone openai openai-eu --base-url https://eu.openai.com/v1
    """
    from mm.display import output_console
    from mm.profile import clone_profile

    try:
        path = clone_profile(source, dest, base_url=base_url, api_key=api_key, model=model)
        overrides = []
        if base_url is not None:
            overrides.append(f"base_url={base_url}")
        if api_key is not None:
            overrides.append("api_key=••••")
        if model is not None:
            overrides.append(f"model={model}")
        suffix = f" ({', '.join(overrides)})" if overrides else ""
        output_console.print(
            f"Cloned profile: [bold]{source}[/bold] → [bold]{dest}[/bold]{suffix}  ({path})"
        )
    except ValueError as e:
        output_console.print(f"{e}")
        raise typer.Exit(1)


@profile_app.command("remove")
def profile_remove(
    name: Annotated[str, typer.Argument(help="Profile name to remove")],
) -> None:
    """Remove a profile.

    \b
    Cannot remove the currently active profile — switch to another first.

    Examples:
      mm profile remove openai
    """
    from mm.display import output_console
    from mm.profile import remove_profile

    try:
        path = remove_profile(name)
        output_console.print(f"Removed profile: {name}  ({path})")
    except ValueError as e:
        output_console.print(f"{e}")
        raise typer.Exit(1)
