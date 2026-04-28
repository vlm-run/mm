"""mm grep -- content search across files."""

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

    from mm.context import FileEntry
    from mm.display import resolve_format
    from mm.pipe import read_paths_from_stdin, resolve_piped_paths
    from mm.utils import is_binary_content

    fmt = resolve_format(format.value if format else None)
    stdin_paths = read_paths_from_stdin()
    _directory = directory or Path("./")

    # Smart-case: default to case-insensitive matching when -i is not passed and the pattern has no uppercase
    # letters. Any uppercase letter in the pattern preserves case-sensitivity
    pattern_literals = re.sub(r"\\.", "", pattern, flags=re.DOTALL)
    smart_case = not ignore_case and not any(c.isupper() for c in pattern_literals)
    re_flags = re.IGNORECASE if (ignore_case or smart_case) else 0
    try:
        regex = re.compile(pattern, re_flags)
    except re.error as e:
        typer.echo(f"Invalid regex: {e}", err=True)
        raise typer.Exit(1)

    all_matches: list[dict] = []
    file_counts: dict[str, int] = {}
    files_to_search: list[FileEntry] = []
    seen_paths: set[str] = set()

    # Directory scan (when provided)
    if directory:
        from mm.context import Context

        ctx = Context(_directory, no_ignore=no_ignore)
        if kind:
            ctx = ctx.filter(kind=kind)
        if ext:
            ctx = ctx.filter(ext=ext)
        for f in ctx.files:
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

    for f in files_to_search:
        try:
            fp = Path(f.path)
            full_path = fp if fp.is_absolute() else (_directory.resolve() / fp)
            if f.is_binary and f.kind not in ("document",):
                continue

            if f.kind == "document":
                from mm.commands.cat import _l1_document

                content = _l1_document(full_path)
            elif f.is_binary:
                continue
            else:
                content = full_path.read_text(errors="replace")
            lines = content.splitlines()

            file_match_count = 0
            for i, line in enumerate(lines):
                if regex.search(line):
                    file_match_count += 1
                    if not count:
                        match_entry: dict = {
                            "path": f.path,
                            "line_number": i + 1,
                            "line": line,
                        }
                        if context_lines > 0:
                            start = max(0, i - context_lines)
                            end = min(len(lines), i + context_lines + 1)
                            match_entry["context"] = lines[start:end]
                        all_matches.append(match_entry)

            if file_match_count > 0:
                file_counts[f.path] = file_match_count
        except Exception:
            continue

    # FTS + semantic both query indexed chunks.
    has_binary = any(is_binary_content(kind=f.kind) for f in files_to_search)
    scan_root = _directory.resolve()
    seen_chunk_keys: set[tuple[str, int]] = set()

    def _merge_chunk_hits(hits: list[dict]) -> None:
        for r in hits:
            rel_path = r["path"]
            try:
                rel_path = str(Path(rel_path).relative_to(scan_root))
            except ValueError:
                pass
            key = (rel_path, r["index"])
            if key in seen_chunk_keys:
                continue
            seen_chunk_keys.add(key)
            snippet = r.get("snippet")
            if snippet:
                line_text = snippet.replace("\n", " ")
            else:
                raw = r["match"].replace("\n", " ")
                match = regex.search(raw)
                if match:
                    start = match.start()
                    context = 40
                    snippet_start = max(0, start - context)
                    snippet_end = min(len(raw), start + len(match.group(0)) + context)
                    line_text = raw[snippet_start:snippet_end]
                    if snippet_start > 0:
                        line_text = "..." + line_text
                    if snippet_end < len(raw):
                        line_text += "..."
                else:
                    line_text = f"{raw[:90]}...{raw[-50:]}" if len(raw) > 140 else raw[:140]
            all_matches.append({"path": rel_path, "line_number": r["index"], "line": line_text})
            file_counts[rel_path] = file_counts.get(rel_path, 0) + 1

    # FTS5 token search over indexed chunks — Silent on missing FTS5 / empty index.
    if has_binary:
        from mm.fts import fts_search

        try:
            scope = (
                {"uri": str(scan_root)} if _directory.is_file() else {"uri_prefix": str(scan_root)}
            )
            _merge_chunk_hits(fts_search(pattern, limit=5, kind=kind, ext=ext, **scope))
        except Exception:
            pass

    if do_semantic and has_binary:
        from mm.semantic import build_hint_cmd, grep_semantic

        try:
            _merge_chunk_hits(
                grep_semantic(
                    pattern,
                    _directory,
                    kind,
                    ext,
                    limit=5,
                    stdin_paths=stdin_paths,
                    no_ignore=no_ignore,
                    do_index=pre_index,
                    quiet=fmt not in ("rich",),
                    cmd_hint=build_hint_cmd(pattern, _directory, kind, ext, ignore_case),
                )
            )
        except (SystemExit, Exception):
            pass

    # Exit 1 on no matches (standard grep/rg behaviour for composability).
    has_matches = bool(file_counts)

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
                border_style="dim",
                header_style="bold white",
                box=box.ROUNDED,
            )
            t.add_column("file", style="white")
            t.add_column("matches", justify="right", style="bright_blue")
            for path, cnt in sorted(file_counts.items(), key=lambda x: -x[1]):
                t.add_row(path, str(cnt))
            output_console.print(t)
        else:
            for path, cnt in sorted(file_counts.items()):
                print(f"{path}:{cnt}")
        return

    total_matches = len(all_matches)
    total_files = len(file_counts)

    if fmt == "rich":
        from rich.text import Text

        from mm.display import output_console

        output_console.print()
        current_file = None
        for m in all_matches:
            if m["path"] != current_file:
                current_file = m["path"]
                output_console.print(f"[bold magenta]{current_file}[/bold magenta]")

            line_text = Text()
            line_text.append(f" {m['line_number']:>4} ", style="dim green")

            line = m["line"]
            parts = regex.split(line)
            found = regex.findall(line)
            for j, part in enumerate(parts):
                line_text.append(part)
                if j < len(found):
                    line_text.append(found[j], style="bold red on bright_black")
            output_console.print(line_text)

        output_console.print()
        output_console.print(
            f"[dim]{total_matches} match{'es' if total_matches != 1 else ''} "
            f"in {total_files} file{'s' if total_files != 1 else ''}[/dim]"
        )
    else:
        for m in all_matches:
            print(f"{m['path']}:{m['line_number']}:{m['line']}")

    if not has_matches:
        raise typer.Exit(1)
