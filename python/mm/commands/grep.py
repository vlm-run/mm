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

    fmt = resolve_format(format.value if format else None)
    stdin_paths = read_paths_from_stdin()
    _directory = directory or Path("./")
    _dir_str = str(_directory) if _directory != Path(".") else ""

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

    scan_root = _directory.resolve()

    # Rust JSON fast path: grep only needs (path, kind, is_binary), so it
    # skips the Arrow build and the pyarrow import entirely.
    if directory:
        import json as json_mod

        from mm._mm import Scanner

        scanner = Scanner(str(scan_root), None, no_ignore=no_ignore)
        scanner.scan()
        exts = [e.strip() for e in ext.split(",")] if ext else []
        rows = json_mod.loads(
            scanner.to_json_fast(kind=kind, ext=exts[0] if len(exts) == 1 else None)
        )
        for row in rows:
            if row["path"].startswith("."):
                continue
            if len(exts) > 1 and row["ext"] not in exts:
                continue
            resolved = str(scan_root / row["path"])
            if resolved not in seen_paths:
                seen_paths.add(resolved)
                files_to_search.append(
                    FileEntry(
                        row=dict(
                            path=row["path"],
                            kind=row["kind"],
                            is_binary=row["is_binary"],
                        )
                    )
                )

    # Piped paths (deduped against directory scan)
    if stdin_paths:
        from mm._mm import scan_one

        for item in resolve_piped_paths(stdin_paths):
            if item in seen_paths:
                continue
            row = scan_one(item)
            if row is None:
                continue
            if kind and kind != row["kind"]:
                continue
            if ext and not item.endswith(ext):
                continue
            seen_paths.add(item)
            files_to_search.append(
                FileEntry(
                    row=dict(
                        path=item,
                        kind=row["kind"],
                        is_binary=row["is_binary"],
                    )
                )
            )

    # MULTILINE keeps ^/$ anchored at line boundaries (per-line semantics).
    ml_regex = re.compile(pattern, regex.flags | re.MULTILINE)

    def _matching_lines(content: str) -> list[int]:
        """Sorted unique 0-based indices of lines containing a match —
        one finditer pass, so zero-match files skip splitlines entirely."""
        import bisect

        hits: list[int] = []
        starts: list[int] | None = None
        for m in ml_regex.finditer(content):
            if starts is None:
                starts = [0]
                pos = content.find("\n")
                while pos != -1:
                    starts.append(pos + 1)
                    pos = content.find("\n", pos + 1)
            idx = bisect.bisect_right(starts, m.start()) - 1
            if not hits or hits[-1] != idx:
                hits.append(idx)
        return hits

    for f in files_to_search:
        try:
            fp = Path(f.path)
            full_path = fp if fp.is_absolute() else (scan_root / fp)
            if f.is_binary and f.kind not in ("document",):
                continue

            if f.kind == "document":
                from mm.cat_utils.extract_meta import extract_meta

                content = extract_meta(full_path, "document")
            elif f.is_binary:
                continue
            else:
                content = full_path.read_text(errors="replace")

            hit_idxs = _matching_lines(content)
            if not hit_idxs:
                continue

            if not count:
                lines = content.splitlines()
                for i in hit_idxs:
                    match_entry: dict = {
                        "path": f"{_dir_str}/{f.path}" if _dir_str else f.path,
                        "line_number": i + 1,
                        "line": lines[i],
                    }
                    if context_lines > 0:
                        start = max(0, i - context_lines)
                        end = min(len(lines), i + context_lines + 1)
                        match_entry["context"] = lines[start:end]
                    all_matches.append(match_entry)

            display_path = f"{_dir_str}/{f.path}" if _dir_str else f.path
            file_counts[display_path] = len(hit_idxs)
        except Exception:
            continue

    # FTS + semantic both query indexed chunks.
    has_indexable = bool(files_to_search)
    seen_chunk_keys: set[tuple[str, int]] = set()

    def _merge_chunk_hits(hits: list[dict]) -> None:
        for r in hits:
            rel_path = r["path"]
            try:
                rel_path = str(Path(rel_path).relative_to(scan_root))
            except ValueError:
                pass
            display_path = f"{_dir_str}/{rel_path}" if _dir_str else rel_path
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
            all_matches.append({"path": display_path, "line_number": r["index"], "line": line_text})
            file_counts[display_path] = file_counts.get(display_path, 0) + 1

    # FTS5 token search over indexed chunks — Silent on missing FTS5 / empty index.
    if has_indexable:
        from mm.fts import fts_search

        try:
            scope = (
                {"uri": str(scan_root)} if _directory.is_file() else {"uri_prefix": str(scan_root)}
            )
            _merge_chunk_hits(fts_search(pattern, limit=5, kind=kind, ext=ext, **scope))
        except Exception:
            pass

    if do_semantic and has_indexable:
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
                output_console.print(f"[bold]{current_file}[/bold]")

            line_text = Text()
            line_text.append(f" {m['line_number']:>4} ")

            line = m["line"]
            pos = 0
            for hit in regex.finditer(line):
                line_text.append(line[pos : hit.start()])
                line_text.append(hit.group(0), style="bold")
                pos = hit.end()
                if hit.start() == hit.end():
                    break
            line_text.append(line[pos:])
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
