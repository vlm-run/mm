"""mm bench -- benchmark all subcommands with statistical analysis."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from mm.commands.bench_commands import BenchCommand
from mm.commands.bench_render import (
    _build_args_line,
    _build_command_cells,
    _build_footer_line,
    _derive_recording_path,
    _derive_recording_stem,
    _extract_cat_content,
    _extract_flag,
    _fmt_ms,
    _format_recording_output,
    _format_stdout_block,
    _kind_placeholder,
    _normalize_stdout_paths,
    _render_table,
    _replace_paths,
    _run_stdout_snapshot,
    _split_base_extra,
    _stdout_fence_lang,
    _strip_ansi,
    _strip_flag,
    _write_bench_recording,
)
from mm.commands.bench_runner import BenchResult, _run_benchmarks
from mm.utils import BaseFormat

__all__ = [
    "BenchResult",
    "_build_args_line",
    "_build_command_cells",
    "_build_footer_line",
    "_derive_recording_path",
    "_derive_recording_stem",
    "_extract_cat_content",
    "_extract_flag",
    "_fmt_ms",
    "_format_recording_output",
    "_format_stdout_block",
    "_kind_placeholder",
    "_load_benchfile",
    "_normalize_stdout_paths",
    "_render_table",
    "_replace_paths",
    "_run_benchmarks",
    "_run_stdout_snapshot",
    "_split_base_extra",
    "_stdout_fence_lang",
    "_strip_ansi",
    "_strip_flag",
    "_write_bench_recording",
    "bench_cmd",
]


def _load_benchfile(
    path: Path,
    files: list | None = None,
) -> list[BenchCommand]:
    """Load an external benchfile and return its ``BenchCommand`` list.

    A benchfile is an ordinary Python module that exposes ONE of:

    * ``commands(files: list[FileEntry]) -> list[BenchCommand]`` — file-aware
      factory; preferred when present so the benchfile can short-circuit
      based on which kinds are available on disk.
    * ``COMMANDS: list[BenchCommand]`` — static list, sufficient for matrices
      that only depend on placeholder substitution.

    The factory takes precedence: a file may define both, but if
    ``commands`` is callable we always call it. ``files`` may be ``None``
    when the loader runs before the directory pre-scan (e.g. when the
    pre-scan itself wants the command count); the factory should tolerate
    an empty list in that case.

    Raises ``typer.Exit(1)`` with a friendly stderr message when:
      * The path doesn't exist or isn't a ``.py`` file
      * Importing the module raises
      * Neither ``commands`` nor ``COMMANDS`` is defined
      * The result isn't a list of ``BenchCommand`` instances
    """
    if not path.exists():
        typer.echo(f"Error: --bench-file {path} not found.", err=True)
        raise typer.Exit(code=1)
    if path.suffix != ".py":
        typer.echo(
            f"Error: --bench-file must be a .py file (got {path.suffix or '<no suffix>'}).",
            err=True,
        )
        raise typer.Exit(code=1)

    module_name = f"_mm_benchfile_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        typer.echo(f"Error: could not load benchfile {path} (invalid module spec).", err=True)
        raise typer.Exit(code=1)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as e:  # pragma: no cover - exercised via tests with bad files
        sys.modules.pop(module_name, None)
        typer.echo(f"Error: failed to import benchfile {path}: {e}", err=True)
        raise typer.Exit(code=1) from e

    factory = getattr(module, "commands", None)
    if callable(factory):
        try:
            commands = factory(files or [])
        except Exception as e:
            typer.echo(f"Error: benchfile {path} `commands(files)` raised: {e}", err=True)
            raise typer.Exit(code=1) from e
    elif hasattr(module, "COMMANDS"):
        commands = module.COMMANDS
    else:
        typer.echo(
            f"Error: benchfile {path} must define either "
            f"`COMMANDS: list[BenchCommand]` or `def commands(files) -> list[BenchCommand]`.",
            err=True,
        )
        raise typer.Exit(code=1)

    if not isinstance(commands, list):
        typer.echo(
            f"Error: benchfile {path} produced {type(commands).__name__}, expected a list.",
            err=True,
        )
        raise typer.Exit(code=1)
    bad = [(i, c) for i, c in enumerate(commands) if not isinstance(c, BenchCommand)]
    if bad:
        i, c = bad[0]
        typer.echo(
            f"Error: benchfile {path} entry [{i}] is {type(c).__name__}, "
            f"expected mm.commands.bench_commands.BenchCommand.",
            err=True,
        )
        raise typer.Exit(code=1)
    return commands


def bench_cmd(
    directory: Annotated[Path, typer.Argument(help="Directory to benchmark")] = Path("."),
    rounds: Annotated[int, typer.Option("--rounds", "-r", help="Measurement rounds")] = 3,
    warmup: Annotated[int, typer.Option("--warmup", "-w", help="Warmup rounds")] = 1,
    mode: Annotated[
        Optional[str],
        typer.Option(
            "--mode",
            "-m",
            help="Groups to bench: metadata (default), fast, accurate, all",
        ),
    ] = None,
    command: Annotated[
        Optional[str],
        typer.Option(
            "--command",
            "-c",
            help=(
                "Substring filter on bench-command names "
                "(e.g. 'cat' to keep only `mm cat ...` benchmarks)."
            ),
        ),
    ] = None,
    group: Annotated[
        Optional[str],
        typer.Option(
            "--group",
            "-g",
            help=(
                "Filter to a single group (case-insensitive exact match on "
                "`BenchCommand.group`). Useful for scoping a benchfile run "
                "to one bucket, e.g. `--group model` or `--group cache`."
            ),
        ),
    ] = None,
    model: Annotated[
        Optional[str],
        typer.Option(
            "--model",
            help=(
                "Filter to rows whose `model` tag matches the given value "
                "(case-insensitive exact match on `BenchCommand.tags['model']`). "
                "Cuts across groups, e.g. `--model qwen3.5-0.8b` keeps every "
                "row pinned to that model regardless of its group. Combines "
                "with --group / --task / --command via AND."
            ),
        ),
    ] = None,
    task: Annotated[
        Optional[str],
        typer.Option(
            "--task",
            help=(
                "Filter to rows whose `task` tag matches the given value "
                "(case-insensitive exact match on `BenchCommand.tags['task']`). "
                "Conventional values: `cap`, `ocr`, `det`, `seg`, `llm`, "
                "`pose`, `track`, `noop`. Cuts across groups and models, "
                "e.g. `--task ocr` keeps every OCR row regardless of which "
                "model it pins. Combines with --group / --model / --command "
                "via AND."
            ),
        ),
    ] = None,
    format: Annotated[
        Optional[BaseFormat],
        typer.Option("--format", "-f", help="Output format: rich, json, tsv, csv, stdout"),
    ] = None,
    timeout: Annotated[
        float,
        typer.Option(
            "--timeout",
            help="Per-command timeout in seconds (stdout snapshot mode only)",
        ),
    ] = 600.0,
    with_generate: Annotated[
        bool,
        typer.Option(
            "--with-generate",
            help=(
                "Stdout snapshot mode: include the LLM generate step in each "
                "cat invocation. Default omits it (`--no-generate`) so the "
                "snapshot is fast, deterministic, and offline-friendly."
            ),
        ),
    ] = False,
    bench_file: Annotated[
        Optional[Path],
        typer.Option(
            "--bench-file",
            "-b",
            help=(
                "Python file exposing `COMMANDS: list[BenchCommand]` or "
                "`def commands(files) -> list[BenchCommand]`. Replaces the "
                "built-in overhead+metadata+mode set entirely; --mode is "
                "ignored. --group / --model / --task / --command filters "
                "still apply on top."
            ),
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help=(
                "Resolve the benchmark plan and render the same table with "
                "`-` placeholders, without executing any commands. Useful "
                "for inspecting an external --bench-file before running it."
            ),
        ),
    ] = False,
    host_info: Annotated[
        bool,
        typer.Option("--host-info", help="Show host system info and exit"),
    ] = False,
) -> None:
    """Benchmark all subcommands with statistical analysis.

    \b
    overhead + metadata always run; ``--mode`` picks which extraction tier joins:
      metadata (default)  overhead + metadata (Unix-comparable: find/wc/sql/grep)
      fast                overhead + metadata + fast
      accurate            overhead + metadata + accurate
      all                 overhead + metadata + fast + accurate

    \b
    ``--format stdout`` switches to *snapshot* mode: each cat-encoder
    variant runs once and its stdout is recorded between ``---`` separators
    — handy for refreshing ``tests/stdout/cat.md``.

    \b
    Filtering (combined via AND):
      --group/-g GROUP    keep rows where BenchCommand.group == GROUP
      --model MODEL       keep rows where tags['model'] == MODEL
      --task TASK         keep rows where tags['task'] == TASK
                          (cap / ocr / det / seg / llm / pose / track / noop)
      --command/-c TERM   keep rows where TERM is a substring of name

    \b
    ``--bench-file PATH`` loads a Python module that exposes either
    ``COMMANDS: list[BenchCommand]`` or ``def commands(files) ->
    list[BenchCommand]`` and **fully replaces** the built-in matrix.
    ``--mode`` is ignored in this mode; the benchfile's own
    ``BenchCommand.group`` drives display grouping. ``--group`` /
    ``--model`` / ``--task`` / ``--command`` filters still apply on
    top.

    \b
    ``--dry-run`` resolves the plan without timing — every row renders
    with ``-`` placeholders (or ``dry_run: true`` in JSON), great for
    inspecting a new benchfile before running it.

    \b
    Examples:
      mm bench ~/data                              # overhead + metadata (default)
      mm bench ~/data --mode metadata              # Unix-comparable subset (no LLM)
      mm bench ~/data --mode accurate              # overhead + metadata + accurate
      mm bench ~/data --mode all                   # full suite
      mm bench ~/data --rounds 5                   # more rounds for stability
      mm bench ~/data --format json                # JSON output for archival
      mm bench ~/data --command cat --format stdout > tests/stdout/cat.md
      mm bench ~/data -b benchmarks/vlmgw_bench_commands.py --dry-run
      mm bench ~/data -b benchmarks/vlmgw_bench_commands.py -r 1 -w 0
      mm bench ~/data -b benchmarks/vlmgw_bench_commands.py --group cache
      mm bench ~/data -b benchmarks/vlmgw_bench_commands.py --model qwen/qwen3.5-0.8b
      mm bench ~/data -b benchmarks/vlmgw_bench_commands.py -g model --model facebook/sam3
      mm bench ~/data -b benchmarks/vlmgw_bench_commands.py --task ocr
      mm bench ~/data -b benchmarks/vlmgw_bench_commands.py --task cap --model qwen/qwen3.5-0.8b
      mm bench --host-info                         # print host spec and exit
      mm bench --host-info --format json           # host spec as JSON
    """
    from mm.commands.bench_commands import (
        ACCURATE_COMMANDS,
        FAST_COMMANDS,
        METADATA_COMMANDS,
        OVERHEAD_COMMANDS,
    )
    from mm.display import resolve_format

    fmt = resolve_format(format.value if format else None)

    if host_info:
        from mm.bench_utils import collect_host_info, render_host_info

        render_host_info(collect_host_info(), fmt=fmt)
        return

    if fmt == "stdout":
        _run_stdout_snapshot(
            directory=directory,
            mode=mode or "fast",
            command_filter=command,
            timeout_s=timeout,
            with_generate=with_generate,
        )
        return

    if bench_file is not None:
        commands = _load_benchfile(bench_file)
        if mode is not None:
            typer.echo(
                "Note: --mode is ignored when --bench-file is set; "
                "the benchfile's BenchCommand.group drives display grouping.",
                err=True,
            )
    else:
        bench_mode = mode or "metadata"
        if bench_mode == "metadata":
            extraction: list = []
        elif bench_mode == "fast":
            extraction = FAST_COMMANDS
        elif bench_mode == "accurate":
            extraction = ACCURATE_COMMANDS
        elif bench_mode == "all":
            extraction = FAST_COMMANDS + ACCURATE_COMMANDS
        else:
            typer.echo(
                f"Error: Unknown --mode {bench_mode!r}. "
                "Use 'metadata', 'fast', 'accurate', or 'all'.",
                err=True,
            )
            raise typer.Exit(code=1)

        commands = OVERHEAD_COMMANDS + METADATA_COMMANDS + extraction

    if group:
        needle_g = group.lower()
        commands = [c for c in commands if c.group.lower() == needle_g]
        if not commands:
            typer.echo(f"Error: --group {group!r} matched no benchmarks.", err=True)
            raise typer.Exit(code=1)

    if model:
        needle_m = model.lower()
        commands = [c for c in commands if c.tags.get("model", "").lower() == needle_m]
        if not commands:
            typer.echo(
                f"Error: --model {model!r} matched no benchmarks "
                "(no rows declare this value in `BenchCommand.tags['model']`).",
                err=True,
            )
            raise typer.Exit(code=1)

    if task:
        needle_t = task.lower()
        commands = [c for c in commands if c.tags.get("task", "").lower() == needle_t]
        if not commands:
            typer.echo(
                f"Error: --task {task!r} matched no benchmarks "
                "(no rows declare this value in `BenchCommand.tags['task']`). "
                "Conventional values: cap, ocr, det, seg, llm, pose, track, noop.",
                err=True,
            )
            raise typer.Exit(code=1)

    if command:
        needle = command.lower()
        commands = [c for c in commands if needle in c.name.lower()]
        if not commands:
            typer.echo(
                f"Error: --command {command!r} matched no benchmark names.",
                err=True,
            )
            raise typer.Exit(code=1)

    from mm.bench_utils import collect_host_info, render_host_info

    host_info_data = collect_host_info()
    render_host_info(host_info_data, fmt=fmt, to_stderr=True)

    if fmt == "rich":
        from mm.display import console

        status = console.status("Starting benchmarks...", spinner="dots")
        status.start()

        def on_progress(group: str, name: str) -> None:
            status.update(f"{group} [bold]{name}[/bold]")

        try:
            results, target_info = _run_benchmarks(
                directory,
                rounds,
                warmup,
                on_progress,
                commands,
                dry_run=dry_run,
            )
        finally:
            status.stop()

        _render_table(results, target_info)
    elif fmt == "json":
        results, target_info = _run_benchmarks(
            directory, rounds, warmup, commands=commands, dry_run=dry_run
        )

        from mm.display import json_dumps

        output = {
            **target_info,
            "results": [r.to_dict() for r in results],
        }
        print(json_dumps(output))
    else:
        results, target_info = _run_benchmarks(
            directory, rounds, warmup, commands=commands, dry_run=dry_run
        )

        from mm.display import emit_tsv

        rows = [r.to_dict() for r in results if not r.skipped]
        emit_tsv(
            rows,
            columns=[
                "group",
                "name",
                "mean_ms",
                "std_ms",
                "min_ms",
                "max_ms",
                "speed",
                "mb_per_sec",
            ],
        )

    if not dry_run and results:
        try:
            recording_path = _write_bench_recording(
                results, target_info, host_info_data, bench_file
            )
            typer.echo(f"Wrote recording to {recording_path}", err=True)
        except OSError as exc:
            typer.echo(f"Warning: failed to write bench recording: {exc}", err=True)
