"""Structured result types shared by the library and CLI surfaces.

The library is the single source of truth for all computation. Every
core capability returns one of these typed results; the CLI consumes
them purely for presentation (Rich rendering, ``--format`` serialization,
exit codes). Keeping the shapes here — rather than as ad-hoc ``dict``s
inside command bodies — is what guarantees the two surfaces cannot drift.

All result types are plain dataclasses with a :meth:`to_dict` method so
they serialize predictably through ``json`` / ``tsv`` / ``csv`` without
any surface-specific glue.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Canonical wc field names — used as dict / JSON keys and column headers so
# the output is identical regardless of ``--format`` or caller.
F_FILES = "files"
F_SIZE = "size"
F_LINES = "lines (est.)"
F_TOKENS = "tokens (est.)"
F_TOK_MB = "tok_per_mb"
F_TOK_IMG = "tok_per_img"


@dataclass
class WcStats:
    """Aggregate token/line/size statistics for a set of files.

    Returned by :func:`mm.stats.compute_wc` and ``Context.wc``. The
    ``by_kind`` mapping carries the same per-kind dicts keyed by the
    canonical ``F_*`` field names so every output format renders
    identically.

    Attributes:
        files: Total number of files counted.
        size: Total size in bytes.
        lines: Estimated total line count.
        tokens: Estimated total token count.
        tok_per_mb: Token density (tokens per megabyte), 0 when empty.
        by_kind: Per-kind breakdown keyed by kind name; each value is a
            dict using the canonical ``F_*`` field names.
    """

    files: int
    size: int
    lines: int
    tokens: int
    tok_per_mb: int
    by_kind: dict[str, dict[str, int | float]] = field(default_factory=dict)

    def to_dict(self, *, by_kind: bool = False) -> dict[str, Any]:
        """Return the canonical result dict (matching the CLI output keys)."""
        result: dict[str, Any] = {
            F_FILES: self.files,
            F_SIZE: self.size,
            F_LINES: self.lines,
            F_TOKENS: self.tokens,
            F_TOK_MB: self.tok_per_mb,
        }
        if by_kind:
            result["by_kind"] = self.by_kind
        return result


@dataclass
class GrepMatch:
    """A single line match produced by ``Context.grep``.

    Attributes:
        path: File path (relative to the context root) containing the match.
        line_number: 1-based line number of the match.
        line: The full matching line (newline stripped).
        kind: File kind of the matched file, when known.
    """

    path: str
    line_number: int
    line: str
    kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {"path": self.path, "line_number": self.line_number, "line": self.line}
        if self.kind is not None:
            d["kind"] = self.kind
        return d


@dataclass
class GrepFileCount:
    """Per-file match count produced by ``Context.grep(count=True)``."""

    path: str
    count: int
    kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"path": self.path, "count": self.count}
        if self.kind is not None:
            d["kind"] = self.kind
        return d


@dataclass
class CatResult:
    """Result of a ``Context.cat`` extraction.

    Attributes:
        path: Source file path.
        content: Extracted / generated textual content.
        mode: Extraction tier that produced ``content``
            (``"metadata"``, ``"fast"``, or ``"accurate"``).
        kind: File kind (``"image"``, ``"document"``, ...).
        cached: Whether the content was served from cache.
    """

    path: str
    content: str
    mode: str
    kind: str | None = None
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __str__(self) -> str:
        return self.content
