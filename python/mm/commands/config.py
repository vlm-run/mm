"""mm config -- view and manage configuration."""

from __future__ import annotations

from typing import Annotated, Optional

import typer

from mm.utils import BaseFormat

config_app = typer.Typer(
    name="config",
    help="View and manage mm configuration.",
    no_args_is_help=True,
)


@config_app.command()
def show(
    format: Annotated[
        Optional[BaseFormat],
        typer.Option("--format", help="Output format: json, tsv, csv"),
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

    fmt = resolve_format(format.value if format else None)
    cfg = get_full_config()
    masked_api_key = "••••" if cfg.transcription.api_key else None

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
            "transcription": {
                "backend": cfg.transcription.backend,
                "base_url": cfg.transcription.base_url,
                "api_key": masked_api_key,
            },
        }
        print(json_dumps(data))
        return

    if fmt in ("tsv", "csv"):
        sep = "\t" if fmt == "tsv" else ","
        print(f"key{sep}value")
        print(f"mode.fast.whisper_model{sep}{cfg.mode_fast.whisper_model}")
        print(f"mode.fast.audio_speed{sep}{cfg.mode_fast.audio_speed}")
        print(f"mode.fast.beam_size{sep}{cfg.mode_fast.beam_size}")
        print(f"mode.accurate.whisper_model{sep}{cfg.mode_accurate.whisper_model}")
        print(f"mode.accurate.audio_speed{sep}{cfg.mode_accurate.audio_speed}")
        print(f"mode.accurate.beam_size{sep}{cfg.mode_accurate.beam_size}")
        print(f"transcription.backend{sep}{cfg.transcription.backend or ''}")
        print(f"transcription.base_url{sep}{cfg.transcription.base_url or ''}")
        print(f"transcription.api_key{sep}{masked_api_key or ''}")
        return

    from rich import box
    from rich.table import Table

    from mm.display import output_console

    config_path = _find_config_path()

    # Mode settings
    mode_tbl = Table(
        title="[bold]Extraction Modes[/bold]",
        caption=str(config_path) if config_path else None,
        caption_style="dim",
        caption_justify="right",
        show_lines=False,
        padding=(0, 1),
        header_style="bold",
        box=box.ROUNDED,
    )
    mode_tbl.add_column("mode")
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

    # Transcription settings
    tx_tbl = Table(
        title="[bold]Transcription[/bold]",
        show_lines=False,
        padding=(0, 1),
        header_style="bold",
        box=box.ROUNDED,
    )
    tx_tbl.add_column("key")
    tx_tbl.add_column("value")
    tx_tbl.add_row("backend", cfg.transcription.backend or "[dim](unset)[/dim]")
    tx_tbl.add_row("base_url", cfg.transcription.base_url or "[dim](unset)[/dim]")
    tx_tbl.add_row("api_key", masked_api_key or "[dim](unset)[/dim]")
    output_console.print(tx_tbl)


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
        output_console.print(f"Config already exists: {existing}")
        output_console.print("Use --force to overwrite.")
        raise typer.Exit(1)

    path = write_platform_config()
    output_console.print(f"Created {path}")


def _find_db_files() -> list:
    """Return existing database and cache file paths."""
    from pathlib import Path

    from mm.store.db import MmDatabase

    targets: list[Path] = [MmDatabase.DB_PATH]
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
    return [p for p in targets if p.exists()]


def _delete_paths(paths: list) -> None:
    """Delete a list of file/directory paths."""
    import shutil

    for p in paths:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()


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
    from mm.display import output_console

    existing = _find_db_files()
    if not existing:
        output_console.print("Nothing to reset — no databases or caches found.")
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
            output_console.print("Aborted.")
            raise typer.Exit(1)

    _delete_paths(existing)

    output_console.print("All databases and caches have been reset.")


@config_app.command("reset-profiles")
def reset_profiles(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Reset all profiles to built-in defaults.

    \b
    Removes custom profiles, restores reserved profiles to their default
    values, and sets the active profile back to the default.
    Mode settings are preserved.

    \b
    Examples:
      mm config reset-profiles
      mm config reset-profiles --yes         # skip confirmation
    """
    from mm.display import output_console
    from mm.profile import RESERVED_PROFILES, get_profile_names, reset_profiles

    names = get_profile_names()
    custom = [n for n in names if n not in RESERVED_PROFILES]

    output_console.print("[bold]This will:[/bold]")
    output_console.print("  • Restore all reserved profiles to their default values")
    output_console.print("  • Set active profile back to default")
    if custom:
        output_console.print(f"  • Remove custom profiles: {', '.join(custom)}")

    if not yes:
        confirm = typer.confirm("\nContinue?", default=False)
        if not confirm:
            output_console.print("Aborted.")
            raise typer.Exit(1)

    path = reset_profiles()
    output_console.print(f"All profiles have been reset to defaults.  ({path})")


@config_app.command("reset")
def reset_all(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Reset everything: clear databases and restore profiles to defaults.

    \b
    Combines reset-db and reset-profiles into a single operation.
    This action is irreversible.

    \b
    Examples:
      mm config reset
      mm config reset --yes                  # skip confirmation
    """
    from mm.display import output_console
    from mm.profile import RESERVED_PROFILES, get_profile_names, reset_profiles

    existing_db = _find_db_files()
    names = get_profile_names()
    custom = [n for n in names if n not in RESERVED_PROFILES]

    output_console.print("[bold]This will:[/bold]")
    if existing_db:
        output_console.print("  • Delete databases and caches:")
        for p in existing_db:
            output_console.print(f"    {p}")
    output_console.print("  • Restore all reserved profiles to their default values")
    output_console.print("  • Set active profile back to default")
    if custom:
        output_console.print(f"  • Remove custom profiles: {', '.join(custom)}")

    if not yes:
        confirm = typer.confirm(
            "\nThis leads to irreversible data loss. Continue?",
            default=False,
        )
        if not confirm:
            output_console.print("Aborted.")
            raise typer.Exit(1)

    _delete_paths(existing_db)
    path = reset_profiles()

    if existing_db:
        output_console.print("All databases and caches have been reset.")
    output_console.print(f"All profiles have been reset to defaults.  ({path})")


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

    \b
    Transcription keys:
      mm config set transcription.backend openai
      mm config set transcription.base_url http://localhost:11434/v1
      mm config set transcription.api_key sk-...
    """
    from mm.config import update_config_key
    from mm.display import output_console

    _VALID_PREFIXES = ("mode.", "transcription.")
    if not any(key.startswith(p) for p in _VALID_PREFIXES):
        output_console.print(f"Unknown key: {key}")
        output_console.print(
            "Valid keys: mode.{fast,accurate}.{whisper_model,audio_speed,beam_size}, "
            "transcription.{backend,base_url,api_key}"
        )
        raise typer.Exit(1)

    parts = key.split(".")

    if key.startswith("mode.") and (
        len(parts) != 3
        or parts[1] not in ("fast", "accurate")
        or parts[2] not in ("whisper_model", "audio_speed", "beam_size")
    ):
        output_console.print(f"Unknown key: {key}")
        output_console.print(
            "Valid keys: mode.{fast,accurate}.{whisper_model,audio_speed,beam_size}"
        )
        raise typer.Exit(1)

    if key.startswith("transcription.") and (
        len(parts) != 2 or parts[1] not in ("backend", "base_url", "api_key")
    ):
        output_console.print(f"Unknown key: {key}")
        output_console.print("Valid keys: transcription.{backend,base_url,api_key}")
        raise typer.Exit(1)

    path = update_config_key(key, value)
    output_console.print(f"Set {key} = {value}  ({path})")


@config_app.command("doctor")
def doctor(
    format: Annotated[
        Optional[BaseFormat],
        typer.Option("--format", help="Output format: json, tsv, csv"),
    ] = None,
) -> None:
    """Run environment health checks and print a diagnostic table."""
    import platform
    import shutil
    import subprocess

    from mm.display import resolve_format

    fmt = resolve_format(format.value if format else None)
    checks: list[dict[str, str]] = []

    def _ok(name: str, detail: str) -> None:
        checks.append({"name": name, "status": "ok", "detail": detail})

    def _warn(name: str, detail: str) -> None:
        checks.append({"name": name, "status": "warn", "detail": detail})

    def _fail(name: str, detail: str) -> None:
        checks.append({"name": name, "status": "fail", "detail": detail})

    # Rust extension
    try:
        import mm._mm  # noqa: F401

        _ok("rust_extension", "loaded")
    except ImportError as e:
        _fail("rust_extension", str(e))

    # mm version
    from mm import __version__

    _ok("mm_version", __version__)

    # ffmpeg
    if shutil.which("ffmpeg"):
        try:
            out = subprocess.run(
                ["ffmpeg", "-version"], capture_output=True, text=True, timeout=5
            ).stdout.split("\n")[0]
            _ok("ffmpeg", out)
        except Exception as e:
            _warn("ffmpeg", f"found but error: {e}")
    else:
        _warn("ffmpeg", "not found (needed for accurate video/audio)")

    # Config file
    try:
        from mm.config import _find_config_path

        cfg_path = _find_config_path()
        _ok("config_file", str(cfg_path)) if cfg_path.exists() else _warn(
            "config_file", "no config file (using defaults)"
        )
    except Exception as e:
        _fail("config_file", str(e))

    # Database
    try:
        from mm.store.db import MmDatabase

        db_path = MmDatabase.DB_PATH
        _ok("database", str(db_path)) if db_path.exists() else _warn(
            "database", f"not yet created ({db_path})"
        )
    except Exception as e:
        _fail("database", str(e))

    # Active profile + reachability
    try:
        from mm.profile import get_profile

        prof = get_profile()
        _ok("profile", f"{prof.name} -> {prof.model} @ {prof.base_url}")
        # Lightweight reachability: single completion with max_tokens=1
        try:
            from openai import OpenAI

            client = OpenAI(base_url=prof.base_url, api_key=prof.api_key or "unused", timeout=10)
            client.chat.completions.create(
                model=prof.model, messages=[{"role": "user", "content": "hi"}], max_tokens=1
            )
            _ok("profile_reachable", "endpoint responded")
        except Exception as e:
            _warn("profile_reachable", str(e)[:120])
    except Exception as e:
        _warn("profile", str(e))

    # Optional deps
    for mod_name, purpose in [
        ("scenedetect", "shot detection"),
        ("faster_whisper", "local Whisper"),
        ("cv2", "OpenCV"),
    ]:
        try:
            __import__(mod_name)
            _ok(f"opt:{mod_name}", purpose)
        except ImportError:
            checks.append(
                {
                    "name": f"opt:{mod_name}",
                    "status": "skip",
                    "detail": f"not installed ({purpose})",
                }
            )

    _ok("python", platform.python_version())

    # Render output
    if fmt == "json":
        from mm.display import json_dumps

        print(json_dumps(checks))
        return
    if fmt in ("tsv", "csv"):
        sep = "\t" if fmt == "tsv" else ","
        print(f"check{sep}status{sep}detail")
        for c in checks:
            print(f"{c['name']}{sep}{c['status']}{sep}{c['detail']}")
        return

    from rich import box
    from rich.table import Table

    from mm.display import output_console

    icons = {
        "ok": "[green]✓[/green]",
        "warn": "[yellow]![/yellow]",
        "fail": "[red]✗[/red]",
        "skip": "[dim]–[/dim]",
    }
    tbl = Table(title="[bold]mm config doctor[/bold]", box=box.ROUNDED, padding=(0, 1))
    tbl.add_column("check")
    tbl.add_column("", justify="center")
    tbl.add_column("detail")
    for c in checks:
        tbl.add_row(c["name"], icons.get(c["status"], c["status"]), c["detail"])
    output_console.print(tbl)

    fails = sum(1 for c in checks if c["status"] == "fail")
    if fails:
        output_console.print(f"\n[red]{fails} check(s) failed.[/red]")
