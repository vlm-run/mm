#!/usr/bin/env python3
"""Test all mm encoders across modalities in parallel.

Runs every encoder × mode combination against a sample file for each kind,
using --no-cache to force fresh execution each time.

Usage:
    uv run python scripts/test_encoders.py
    uv run python scripts/test_encoders.py --model gemini-2.5-pro
    uv run python scripts/test_encoders.py --concurrency 4
    uv run python scripts/test_encoders.py --verbose
    uv run python scripts/test_encoders.py --kind audio --encoder transcript --mode fast
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tarfile
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

try:
    from rich import box
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TimeElapsedColumn,
    )
    from rich.table import Table
    from rich.text import Text
except ImportError:
    print("rich is required: uv pip install rich", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DATA_DIR = REPO_ROOT / "benchmarks" / "data" / "mmbench-tiny"
TARBALL_URL = "https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-tiny.tar.gz"

SAMPLE_FILES: dict[str, Path] = {
    "audio": DATA_DIR / "how_to_build_an_mvp.mp3",
    "document": DATA_DIR / "attention-is-all-you-need.pdf",
    "image": DATA_DIR / "cats.jpg",
    "video": DATA_DIR / "bakery.mp4",
}

ENCODERS: dict[str, list[str]] = {
    "audio": ["transcript", "native", "gemini-native"],
    "document": ["gemini-native", "page-text", "rasterize", "rasterize-text"],
    "image": ["resize", "tile"],
    "video": [
        "captions",
        "chunked",
        "clips",
        "clips-w-transcript",
        "frames",
        "frames-w-transcript",
        "gemini-native",
        "gemini-chunked",
        "keyframes",
        "keyframes-w-transcript",
        "mosaic",
        "mosaic-w-transcript",
        "native",
        "shot-mosaic",
        "shot-mosaic-w-transcript",
        "shots",
        "shots-w-transcript",
        "summary",
        "summary-w-transcript",
        "transcript",
    ],
}

MODES = ("fast", "accurate")

KIND_COLORS = {
    "audio": "cyan",
    "document": "yellow",
    "image": "green",
    "video": "magenta",
}


@dataclass
class Result:
    kind: str
    encoder: str
    mode: str
    returncode: int
    elapsed: float
    stdout: str
    stderr: str
    cmd: list[str] = None  # type: ignore[assignment]

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def label(self) -> str:
        return f"{self.kind}/{self.encoder} [{self.mode}]"


def fetch_data(console: Console) -> None:
    """Download and extract mmbench-tiny if any sample file is missing."""
    if all(f.exists() for f in SAMPLE_FILES.values()):
        return

    missing = [f.name for f in SAMPLE_FILES.values() if not f.exists()]
    console.print(f"[dim]Fetching mmbench-tiny ({', '.join(missing)} missing)...[/dim]")

    DATA_DIR.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        with console.status(f"[dim]Downloading {TARBALL_URL}[/dim]"):
            urllib.request.urlretrieve(TARBALL_URL, tmp_path)
        with console.status("[dim]Extracting...[/dim]"):
            with tarfile.open(tmp_path, "r:gz") as tar:
                members = [
                    m for m in tar.getmembers() if not m.name.startswith("/") and ".." not in m.name
                ]
                tar.extractall(DATA_DIR.parent, members=members, filter="data")
    finally:
        tmp_path.unlink(missing_ok=True)

    still_missing = [f.name for f in SAMPLE_FILES.values() if not f.exists()]
    if still_missing:
        console.print(
            f"[red]Files not found in tarball after extraction: {', '.join(still_missing)}[/red]"
        )
        sys.exit(1)

    console.print(f"[dim]Saved to {DATA_DIR}[/dim]")


def build_cmd(kind: str, encoder: str, mode: str, model: str, profile: str) -> list[str]:
    return [
        "uv",
        "run",
        "mm",
        "--profile",
        profile,
        "cat",
        str(SAMPLE_FILES[kind]),
        "--mode",
        mode,
        "--pipeline",
        encoder,
        "--no-cache",
        "--generate.model",
        model,
    ]


async def run_encoder(
    semaphore: asyncio.Semaphore,
    kind: str,
    encoder: str,
    mode: str,
    model: str,
    profile: str,
    timeout: float,
) -> Result:
    cmd = build_cmd(kind, encoder, mode, model, profile)

    async with semaphore:
        t0 = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(REPO_ROOT),
            )
        except Exception as exc:
            return Result(kind, encoder, mode, -2, time.monotonic() - t0, "", str(exc), cmd)

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return Result(
                kind,
                encoder,
                mode,
                -1,
                time.monotonic() - t0,
                "",
                f"TIMEOUT after {timeout:.0f}s",
                cmd,
            )

        elapsed = time.monotonic() - t0

    return Result(
        kind=kind,
        encoder=encoder,
        mode=mode,
        returncode=proc.returncode,
        elapsed=elapsed,
        stdout=stdout_bytes.decode(errors="replace"),
        stderr=stderr_bytes.decode(errors="replace"),
        cmd=cmd,
    )


async def main(args: argparse.Namespace) -> int:
    console = Console()
    fetch_data(console)
    semaphore = asyncio.Semaphore(args.concurrency)

    kind_filter: set[str] = set(args.kind) if args.kind else set()
    encoder_filter: set[str] = set(args.encoder) if args.encoder else set()
    mode_filter: set[str] = set(args.mode) if args.mode else set()

    if encoder_filter:
        unknown = encoder_filter - {enc for encs in ENCODERS.values() for enc in encs}
        if unknown:
            console.print(f"[red]Unknown encoder(s): {', '.join(sorted(unknown))}[/red]")
            console.print(
                f"[dim]Available: {', '.join(sorted(enc for encs in ENCODERS.values() for enc in encs))}[/dim]"
            )
            return 1

    tasks = [
        (kind, encoder, mode)
        for kind, encoders in ENCODERS.items()
        if not kind_filter or kind in kind_filter
        for encoder in encoders
        if not encoder_filter or encoder in encoder_filter
        for mode in MODES
        if not mode_filter or mode in mode_filter
    ]

    if not tasks:
        console.print("[yellow]No matching encoder/kind combinations.[/yellow]")
        return 0

    if args.dry_run:
        console.print(f"\n[bold]Dry run[/bold] — {len(tasks)} command(s)\n")
        for kind, encoder, mode in tasks:
            color = KIND_COLORS.get(kind, "white")
            cmd_str = " ".join(build_cmd(kind, encoder, mode, args.model, args.profile))
            console.print(f"[{color}]{kind}/{encoder}[/{color}] [dim]\\[{mode}][/dim]")
            console.print(f"  [dim]$ {cmd_str}[/dim]")
        console.print()
        return 0

    console.print(
        f"\n[bold]mm encoder smoke test[/bold] — "
        f"{len(tasks)} combinations · "
        f"model=[cyan]{args.model}[/cyan] · "
        f"profile=[cyan]{args.profile}[/cyan] · "
        f"concurrency=[cyan]{args.concurrency}[/cyan]\n"
    )

    results: list[Result] = []

    with Progress(
        SpinnerColumn(),
        "[progress.description]{task.description}",
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        bar = progress.add_task("Running encoders...", total=len(tasks))

        async def run_and_track(kind: str, encoder: str, mode: str) -> Result:
            result = await run_encoder(
                semaphore,
                kind,
                encoder,
                mode,
                args.model,
                args.profile,
                args.timeout,
            )
            progress.advance(bar)
            if args.verbose or not result.ok:
                icon = "[green]✓[/green]" if result.ok else "[red]✗[/red]"
                progress.log(f"{icon} {result.label}  ({result.elapsed:.1f}s)")
                if args.verbose:
                    progress.log(f"  [dim]$ {' '.join(result.cmd)}[/dim]")
                if not result.ok and result.stderr:
                    snippet = result.stderr.strip()[:240]
                    progress.log(f"  [dim]{snippet}[/dim]")
            return result

        results = list(
            await asyncio.gather(
                *(run_and_track(kind, encoder, mode) for kind, encoder, mode in tasks)
            )
        )

    table = Table(
        title="Encoder Smoke Test Results",
        box=box.ROUNDED,
        show_lines=False,
        header_style="bold",
    )
    table.add_column("Kind", style="bold", width=10)
    table.add_column("Encoder", width=26)
    table.add_column("Mode", width=10)
    table.add_column("Status", width=8, justify="center")
    table.add_column("Time", width=8, justify="right")

    for result in sorted(results, key=lambda r: (r.kind, r.encoder, r.mode)):
        color = KIND_COLORS.get(result.kind, "white")
        status = Text("PASS", style="bold green") if result.ok else Text("FAIL", style="bold red")
        table.add_row(
            Text(result.kind, style=color),
            result.encoder,
            result.mode,
            status,
            f"{result.elapsed:.1f}s",
        )

    console.print(table)

    passed = sum(1 for r in results if r.ok)
    failed = len(results) - passed
    summary_color = "green" if failed == 0 else "red"
    suffix = f", [red]{failed} failed[/red]" if failed else ""
    console.print(
        f"\n[bold {summary_color}]{passed}/{len(results)} passed[/bold {summary_color}]{suffix}\n"
    )

    if failed and not args.verbose:
        console.print("[dim]Run with --verbose (-v) to see failure output inline.[/dim]\n")

    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test all mm encoders against sample files in parallel.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--model",
        default="qwen/qwen3.5-0.8b",
        metavar="MODEL",
        help="Model passed via --generate.model (default: qwen/qwen3.5-0.8b)",
    )
    parser.add_argument(
        "--profile",
        default="gateway",
        metavar="PROFILE",
        help="mm profile to use (default: gateway)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=8,
        metavar="N",
        help="Max parallel encoder runs (default: 8)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        metavar="SECS",
        help="Per-task timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--kind",
        action="append",
        metavar="KIND",
        choices=list(ENCODERS),
        help=f"Restrict to one kind: {', '.join(ENCODERS)}. Repeatable.",
    )
    parser.add_argument(
        "--encoder",
        action="append",
        metavar="ENCODER",
        help="Restrict to a specific encoder name (e.g. shot-mosaic). Repeatable.",
    )
    parser.add_argument(
        "--mode",
        action="append",
        metavar="MODE",
        choices=list(MODES),
        help=f"Restrict to one mode: {', '.join(MODES)}. Repeatable.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands that would run without executing them",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print each result inline as it completes",
    )
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
