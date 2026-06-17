"""mm grep -- content search across files (presentation surface)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Optional

import typer

from mm.utils import Format


def grep_cmd(
    pattern: Annotated[str, typer.Argument(help="Search pattern (regex)")],
    directory: Annotated[Optional[Path], typer.Argument(help="Directory to search")] = None,
    kind: Annotated[
        Optional[str],
        typer.Option(
            "--kind",
            "-k",
            help="Filter by file kind (supports comma-separated, e.g. image,document)",
        ),
    ] = None,
    ext: Annotated[
        Optional[str], typer.Option("--ext", "-e", help="Filter by extension(s)")
    ] = None,
    context_lines: Annotated[int, typer.Option("-C", help="Context lines around match")] = 0,
    count: Annotated[
        bool, typer.Option("--count", "-c", help="Show only match counts per file")
    ] = False,
    do_semantic: Annotated[
        bool, typer.Option("--semantic", "-s", help="Do a semantic (vector) search")
    ] = False,
    pre_index: Annotated[
        bool,
        typer.Option("--pre-index", help="Index unindexed files before semantic search (max 50)"),
    ] = False,
    ignore_case: Annotated[
        bool,
        typer.Option("--ignore-case", "-i", help="Force case-insensitive matching"),
    ] = False,
    no_ignore: Annotated[
        bool, typer.Option("--no-ignore", help="Don't respect .gitignore rules")
    ] = False,
    format: Annotated[
        Optional[Format],
        typer.Option(
            "--format", "-f", help="Output format: json, tsv, csv, dataset-jsonl, dataset-hf"
        ),
    ] = None,
) -> None:
    """Search file contents -- text and semantic (like rg/grep).

    When --semantic/-s is passed and binary files (images, video, audio,
    documents) are present, semantic (vector) search runs alongside the
    normal text search.

    \b
    Examples:
      mm grep "TODO" ~/project                          # search all files
      mm grep "import.*torch" ~/project --kind code     # code files only
      mm grep "attention" ~/papers --ext .pdf           # search PDF text
      mm grep "error|warn" ~/logs -C 2                  # context lines
      mm grep "Quantum Phase" ~/data -s                 # semantic search on binaries
      mm grep "Quantum Phase" ~/data -s --pre-index     # index first, then semantic search
      mm grep "def main" ~/src --count                  # match counts only
      mm grep "Quantum" ~/docs -i                       # case-insensitive
      mm grep "secret" ~/docs --no-ignore               # ignore .gitignore
    """

    from mm.context import Context, FileEntry
    from mm.display import resolve_format
    from mm.pipe import read_paths_from_stdin, resolve_piped_paths
    from mm.search import compile_pattern, search_content
    from mm.utils import is_binary_content

    fmt = resolve_format(format.value if format else None)
    stdin_paths = read_paths_from_stdin()
    _directory = directory or Path("./")

    try:
        regex = compile_pattern(pattern, ignore_case=ignore_case)
    except re.error as e:
        typer.echo(f"Invalid regex: {e}", err=True)
        raise typer.Exit(1)

    files_to_search: list[FileEntry] = []
    seen_paths: set[str] = set()

    # Directory scan (when provided). Reuse the Context's scanner-backed
    # filter so the library does the row selection.
    if directory:
        scoped = Context(_directory, no_ignore=no_ignore)
        if kind:
            scoped = scoped.filter(kind=kind)
        if ext:
            scoped = scoped.filter(ext=ext)
        for f in scoped.files:
            if f.path.startswith("."):
                continue
            resolved = str((_directory.resolve() / f.path).resolve())
            if resolved not in seen_paths:
                seen_paths.add(resolved)
                files_to_search.append(f)

    # Piped paths (deduped against directory scan)
    if stdin_paths:
        from mm.utils import file_kind_with_code

        for item in resolve_piped_paths(stdin_paths):
            if item in seen_paths:
                continue
            fkind = file_kind_with_code(Path(item))
            if kind and kind != fkind:
                continue
            if ext and not item.endswith(ext):
                continue
            seen_paths.add(item)
            files_to_search.append(
                FileEntry(
                    row=dict(
                        path=item,
                        kind=fkind,
                        is_binary=is_binary_content(kind=fkind),
                    )
                )
            )

    result = search_content(
        pattern,
        files=files_to_search,
        root=_directory,
        regex=regex,
        context_lines=context_lines,
        count=count,
        kind=kind,
        ext=ext,
        semantic=do_semantic,
        pre_index=pre_index,
        no_ignore=no_ignore,
        stdin_paths=stdin_paths,
        quiet=fmt not in ("rich",),
    )

    all_matches = [m.to_dict() for m in result.matches]
    file_counts = result.file_counts
    has_matches = result.has_matches

    if fmt in ("json", "dataset-jsonl", "dataset-hf"):
        from mm.display import emit_rows

        if count:
            if fmt == "json":
                from mm.display import json_dumps

                print(json_dumps(file_counts))
            else:
                emit_rows(fmt, [{"path": p, "count": c} for p, c in file_counts.items()])
        else:
            emit_rows(fmt, all_matches)
        if not has_matches:
            raise typer.Exit(1)
        return

    if count:
        if fmt == "rich":
            from rich import box
            from rich.table import Table as RichTable

            from mm.display import output_console

            t = RichTable(
                caption=f"{sum(file_counts.values())} matches in {len(file_counts)} files",
                caption_style="dim",
                caption_justify="right",
                show_lines=False,
                padding=(0, 1),
                header_style="bold",
                box=box.ROUNDED,
            )
            t.add_column("file")
            t.add_column("matches", justify="right")
            for path, cnt in sorted(file_counts.items(), key=lambda x: -x[1]):
                t.add_row(path, str(cnt))
            output_console.print(t)
        else:
            for path, cnt in sorted(file_counts.items()):
                print(f"{path}:{cnt}")
        return

    total_matches = result.total_matches
    total_files = result.total_files

    if fmt == "rich":
        from rich.text import Text

        from mm.display import output_console

        output_console.print()
        current_file = None
        for m in all_matches:
            if m["path"] != current_file:
                current_file = m["path"]
                output_console.print(f"[bold]{current_file}[/bold]")

            line_text = Text()
            line_text.append(f" {m['line_number']:>4} ")

            line = m["line"]
            parts = regex.split(line)
            found = regex.findall(line)
            for j, part in enumerate(parts):
                line_text.append(part)
                if j < len(found):
                    line_text.append(found[j], style="bold")
            output_console.print(line_text)

        output_console.print()
        output_console.print(
            f"{total_matches} match{'es' if total_matches != 1 else ''} "
            f"in {total_files} file{'s' if total_files != 1 else ''}"
        )
    else:
        for m in all_matches:
            print(f"{m['path']}:{m['line_number']}:{m['line']}")

    if not has_matches:
        raise typer.Exit(1)
