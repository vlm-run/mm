"""Content search core shared by ``Context.grep`` and ``mm grep``.

The library owns all of the search logic — smart-case regex compilation,
text/document line scanning, and the full-text + semantic chunk merge.
The CLI is a pure presentation surface that compiles the pattern, calls
:func:`search_content`, and renders the resulting :class:`GrepResult`.

Reading indexed chunks (FTS / vector) is a query, not a write, so it lives
here; persisting extractions/embeddings remains the caller's concern.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from mm.results import GrepMatch, GrepResult

if TYPE_CHECKING:
    from mm.context import FileEntry


def compile_pattern(pattern: str, *, ignore_case: bool = False) -> re.Pattern[str]:
    """Compile ``pattern`` applying smart-case semantics.

    Smart-case: when ``ignore_case`` is not forced and the pattern contains
    no uppercase letters (ignoring escaped chars), matching is
    case-insensitive. Any uppercase letter preserves case sensitivity.

    Args:
        pattern: Regular expression source.
        ignore_case: Force case-insensitive matching.

    Returns:
        A compiled :class:`re.Pattern`.

    Raises:
        re.error: If ``pattern`` is not a valid regular expression.
    """
    literals = re.sub(r"\\.", "", pattern, flags=re.DOTALL)
    smart_case = not ignore_case and not any(c.isupper() for c in literals)
    flags = re.IGNORECASE if (ignore_case or smart_case) else 0
    return re.compile(pattern, flags)


def search_content(
    pattern: str,
    *,
    files: list[FileEntry],
    root: Path,
    regex: re.Pattern[str] | None = None,
    ignore_case: bool = False,
    context_lines: int = 0,
    count: bool = False,
    kind: str | None = None,
    ext: str | None = None,
    semantic: bool = False,
    pre_index: bool = False,
    no_ignore: bool = False,
    stdin_paths: list[str] | None = None,
    quiet: bool = True,
) -> GrepResult:
    """Search ``files`` for ``pattern`` and merge indexed-chunk hits.

    Source of truth for ``mm grep``. Scans text and document files line by
    line, then layers full-text (FTS5) and, when requested, semantic
    (vector) hits over the same indexed chunks.

    Args:
        pattern: Regular expression source.
        files: Files to scan (directory-scan entries and/or piped paths).
        root: Search root used to relativize chunk hits and scope FTS.
        regex: Pre-compiled pattern (dependency injection from the CLI fast
            path). When ``None``, one is compiled via :func:`compile_pattern`.
        ignore_case: Force case-insensitive matching (used only when
            ``regex`` is ``None``).
        context_lines: Lines of context to attach around each match.
        count: When ``True``, only per-file counts are produced (no lines).
        kind: Optional kind filter forwarded to FTS / semantic search.
        ext: Optional extension filter forwarded to FTS / semantic search.
        semantic: Also run a semantic (vector) search over indexed chunks.
        pre_index: Index unindexed files before semantic search.
        no_ignore: Don't respect ``.gitignore`` during semantic indexing.
        stdin_paths: Raw piped paths forwarded to semantic search.
        quiet: Suppress semantic-search progress messages.

    Returns:
        A :class:`~mm.results.GrepResult` with matches and per-file counts.
    """
    if regex is None:
        regex = compile_pattern(pattern, ignore_case=ignore_case)

    result = GrepResult()
    _scan_files(result, files, root, regex, context_lines=context_lines, count=count)

    if not files:
        return result

    scan_root = root.resolve()
    seen_chunk_keys: set[tuple[str, int]] = set()

    from mm.fts import fts_search

    try:
        scope = {"uri": str(scan_root)} if root.is_file() else {"uri_prefix": str(scan_root)}
        _merge_chunk_hits(
            result,
            fts_search(pattern, limit=5, kind=kind, ext=ext, **scope),
            regex,
            scan_root,
            seen_chunk_keys,
        )
    except Exception:  # noqa: BLE001
        pass

    if semantic:
        from mm.semantic import build_hint_cmd, grep_semantic

        try:
            _merge_chunk_hits(
                result,
                grep_semantic(
                    pattern,
                    root,
                    kind,
                    ext,
                    limit=5,
                    stdin_paths=stdin_paths,
                    no_ignore=no_ignore,
                    do_index=pre_index,
                    quiet=quiet,
                    cmd_hint=build_hint_cmd(pattern, root, kind, ext, ignore_case),
                ),
                regex,
                scan_root,
                seen_chunk_keys,
            )
        except (SystemExit, Exception):  # noqa: BLE001
            pass

    return result


def _scan_files(
    result: GrepResult,
    files: list[FileEntry],
    root: Path,
    regex: re.Pattern[str],
    *,
    context_lines: int,
    count: bool,
) -> None:
    """Scan text/document files line by line, populating ``result``."""
    for f in files:
        try:
            fp = Path(f.path)
            full_path = fp if fp.is_absolute() else (root.resolve() / fp)
            if f.is_binary and f.kind != "document":
                continue

            if f.kind == "document":
                from mm.cat_utils.extract_meta import _local_document

                content = _local_document(full_path)
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
                        match = GrepMatch(path=f.path, line_number=i + 1, line=line)
                        if context_lines > 0:
                            start = max(0, i - context_lines)
                            end = min(len(lines), i + context_lines + 1)
                            match.context = lines[start:end]
                        result.matches.append(match)

            if file_match_count > 0:
                result.file_counts[f.path] = file_match_count
        except Exception:  # noqa: BLE001
            continue


def _merge_chunk_hits(
    result: GrepResult,
    hits: list[dict],
    regex: re.Pattern[str],
    scan_root: Path,
    seen_chunk_keys: set[tuple[str, int]],
) -> None:
    """Merge FTS / semantic chunk hits into ``result`` (deduped)."""
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
        result.matches.append(GrepMatch(path=rel_path, line_number=r["index"], line=line_text))
        result.file_counts[rel_path] = result.file_counts.get(rel_path, 0) + 1
