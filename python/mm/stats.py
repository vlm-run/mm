"""File-aggregate statistics — the source of truth behind ``mm wc``.

The computation lives here so that both ``Context.wc`` and the ``mm wc``
command share one implementation. Following the dependency-injection
pattern used across the library, :func:`compute_wc` accepts an
already-built Rust ``Scanner`` so callers that have one on a hot path
(the CLI) avoid re-scanning, while library callers can omit it and let
the function build one.
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any

from mm.results import (
    F_FILES,
    F_LINES,
    F_SIZE,
    F_TOK_IMG,
    F_TOK_MB,
    F_TOKENS,
    WcStats,
)

TOKEN_CHARS_RATIO = 4


def compute_wc(
    root: str | Path,
    *,
    kind: str | None = None,
    stdin_paths: list[str] | None = None,
    scanner: Any | None = None,
) -> WcStats:
    """Compute file/line/token/size aggregates for a directory or path set.

    Args:
        root: Directory the stats are computed against.
        kind: Optional kind filter (single or comma-separated, e.g.
            ``"image,document"``).
        stdin_paths: If given, restrict the computation to this explicit
            list of piped paths instead of scanning ``root``.
        scanner: Optional pre-built Rust ``Scanner`` for ``root`` (already
            scanned or not). When ``None``, one is constructed and scanned.
            Passing a scanner preserves the CLI fast path.

    Returns:
        A :class:`~mm.results.WcStats` with totals and a ``by_kind`` breakdown.
    """
    root = Path(root).resolve()

    if stdin_paths:
        return _wc_from_paths(root, stdin_paths, kind)

    if scanner is None:
        from mm._mm import Scanner

        scanner = Scanner(str(root))
        scanner.scan()

    base = _json.loads(scanner.wc(kind=kind))
    kind_stats: dict[str, dict[str, int | float]] = {}
    for k, s in base.get("by_kind", {}).items():
        kind_stats[k] = {
            F_FILES: s["files"],
            F_SIZE: s["bytes"],
            F_LINES: s["lines"],
            F_TOKENS: s["tokens"],
        }
    total_files = base["files"]
    total_size = base["bytes"]
    total_tokens = base["estimated_tokens"]
    total_lines = base["lines"]

    # Rust handles every kind except documents (which need pypdfium2);
    # overlay document line/token counts extracted in Python.
    if "document" in kind_stats and kind_stats["document"].get(F_FILES, 0) > 0:
        doc_entries = _json.loads(scanner.to_json_fast(kind="document"))
        if doc_entries:
            from mm.cat_utils.extract_meta import _local_document

            for entry in doc_entries:
                content = _local_document(root / entry["path"])
                char_len = len(content)
                lines = content.count("\n")
                if content and not content.endswith("\n"):
                    lines += 1
                lines = max(1, lines)
                tokens = char_len // TOKEN_CHARS_RATIO

                total_tokens += tokens
                total_lines += lines
                doc = kind_stats["document"]
                doc[F_TOKENS] = int(doc.get(F_TOKENS, 0)) + tokens
                doc[F_LINES] = int(doc.get(F_LINES, 0)) + lines

    tok_per_mb = _density(total_tokens, total_size)
    for k, s in kind_stats.items():
        mb = s[F_SIZE] / (1024 * 1024) if s[F_SIZE] else 0
        if mb > 0:
            s[F_TOK_MB] = round(s[F_TOKENS] / mb)
        if k == "image" and s[F_FILES] > 0:
            s[F_TOK_IMG] = round(s[F_TOKENS] / s[F_FILES])

    return WcStats(
        files=total_files,
        size=total_size,
        lines=total_lines,
        tokens=total_tokens,
        tok_per_mb=tok_per_mb,
        by_kind=kind_stats,
    )


def _density(tokens: int, size: int) -> int:
    """Tokens per megabyte (0 when size is 0)."""
    mb = size / (1024 * 1024) if size else 0
    return round(tokens / mb) if mb > 0 else 0


def _wc_from_paths(root: Path, paths: list[str], kind_filter: str | None) -> WcStats:
    """Compute wc stats for an explicit set of piped file paths."""
    from mm.pipe import resolve_piped_paths
    from mm.utils import file_kind_with_code

    kind_stats: dict[str, dict[str, int | float]] = {}
    total_files = 0
    total_size = 0
    total_tokens = 0
    total_lines = 0

    for p_str in resolve_piped_paths(paths):
        p = Path(p_str)
        if not p.is_file():
            continue

        fkind = file_kind_with_code(p)
        if kind_filter:
            if "," in kind_filter:
                if fkind not in {k.strip() for k in kind_filter.split(",")}:
                    continue
            elif kind_filter != fkind:
                continue

        fsize = p.stat().st_size
        if fkind in ("text", "code"):
            content = p.read_text(errors="replace")
            flines = content.count("\n") or 1
            ftokens = len(content) // TOKEN_CHARS_RATIO
        elif fkind == "document":
            from mm.cat_utils.extract_meta import _local_document

            content = _local_document(p)
            flines = max(1, content.count("\n"))
            ftokens = len(content) // TOKEN_CHARS_RATIO
        else:
            flines = 0
            ftokens = 0

        total_files += 1
        total_size += fsize
        total_lines += flines
        total_tokens += ftokens

        if fkind not in kind_stats:
            kind_stats[fkind] = {F_FILES: 0, F_SIZE: 0, F_LINES: 0, F_TOKENS: 0}
        kind_stats[fkind][F_FILES] += 1
        kind_stats[fkind][F_SIZE] += fsize
        kind_stats[fkind][F_LINES] += flines
        kind_stats[fkind][F_TOKENS] += ftokens

    for k, s in kind_stats.items():
        mb = s[F_SIZE] / (1024 * 1024) if s[F_SIZE] else 0
        if mb > 0:
            s[F_TOK_MB] = round(s[F_TOKENS] / mb)
        if k == "image" and s[F_FILES] > 0:
            s[F_TOK_IMG] = round(s[F_TOKENS] / s[F_FILES])

    return WcStats(
        files=total_files,
        size=total_size,
        lines=total_lines,
        tokens=total_tokens,
        tok_per_mb=_density(total_tokens, total_size),
        by_kind=kind_stats,
    )
