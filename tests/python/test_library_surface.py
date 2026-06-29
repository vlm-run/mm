"""Library-surface guarantees for the public ``mm`` API.

This module is a structural guard, not a behavioral one: it asserts that the
public library surface stays *fully implemented* and *callable* so a future
change can't silently break a public method or re-introduce an unimplemented
stub. It complements (does not replace) the behavior-specific suites.

Three invariants are checked:

1. Nothing in ``python/mm`` raises :class:`NotImplementedError` — the library
   ships no stubbed-out public capability.
2. Every name exported from ``mm.__all__`` imports cleanly.
3. Every public :class:`~mm.context.Context` method is callable end-to-end in
   the mode it belongs to (directory-scan vs incremental role-aware), on a
   real fixture directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import mm
from mm.context import Context
from mm.results import CatResult, GrepMatch, GrepResult, WcStats

# Public Context methods, partitioned by the construction mode they require.
# A directory-scan Context(root) owns filesystem aggregates; an incremental
# Context() (no root) owns role-aware items/refs. Methods are listed here so a
# rename or accidental removal trips test_context_public_method_inventory.
_DIRECTORY_SCAN_METHODS = frozenset(
    {
        "info",
        "filter",
        "wc",
        "grep",
        "cat",
        "peek",
        "sql",
        "to_arrow",
        "to_polars",
        "to_pandas",
        "to_records",
        "ref_for",
        "global_ref",
    }
)
_ROLE_AWARE_METHODS = frozenset(
    {
        "add",
        "items",
        "ref_ids",
        "to_md",
        "print_tree",
        "to_messages",
    }
)
# Methods exercised elsewhere / not pinned to a single mode in this guard.
_OTHER_METHODS = frozenset({"encode", "head", "tail", "render_html", "show", "get", "remove"})

_TREE_LAYOUTS = ("insertion", "paths", "kind", "flat", "hybrid")


def test_no_unimplemented_in_library() -> None:
    """No module under ``python/mm`` raises ``NotImplementedError``."""
    pkg_root = Path(mm.__file__).parent
    offenders = [
        str(py.relative_to(pkg_root))
        for py in pkg_root.rglob("*.py")
        if "NotImplementedError" in py.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"NotImplementedError found in: {offenders}"


def test_public_exports_importable() -> None:
    """Every name in ``mm.__all__`` resolves via the lazy import machinery."""
    failures: dict[str, str] = {}
    for name in mm.__all__:
        try:
            assert getattr(mm, name) is not None
        except Exception as exc:  # noqa: BLE001 - we want the name + error
            failures[name] = repr(exc)
    assert not failures, f"exports failed to import: {failures}"


def test_context_public_method_inventory() -> None:
    """The set of public ``Context`` methods matches the documented surface.

    Guards against silently dropping a public method (the partitions above go
    stale) or adding an undocumented one (this guard should be updated with it).
    """
    import inspect

    public = {
        name
        for name, _ in inspect.getmembers(Context, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    catalogued = _DIRECTORY_SCAN_METHODS | _ROLE_AWARE_METHODS | _OTHER_METHODS
    assert public == catalogued, (
        f"Context surface drifted. Only in code: {public - catalogued}; "
        f"only in test inventory: {catalogued - public}"
    )


def test_directory_scan_surface(small_tree: Path) -> None:
    """Every directory-scan ``Context`` method is callable end-to-end."""
    ctx = Context(small_tree, session_id="surface-test")

    assert ctx.info() is None  # prints a panel, returns nothing

    code = ctx.filter(kind="code")
    assert code.files, "expected at least one code file in the fixture"
    a_code = code.files[0].path

    stats = ctx.wc()
    assert isinstance(stats, WcStats)
    assert stats.files > 0
    assert "by_kind" in stats.to_dict(by_kind=True)
    assert isinstance(ctx.wc(kind="code"), WcStats)

    grep_res = ctx.grep("fn")
    assert isinstance(grep_res, GrepResult)
    assert isinstance(ctx.grep("FN", ignore_case=True), GrepResult)

    assert isinstance(ctx.cat(a_code), str)

    meta = ctx.peek(a_code)
    assert isinstance(meta, mm.FileMetadata)
    assert meta.path

    table = ctx.sql("SELECT count(*) AS n FROM files")
    assert table.num_rows == 1

    assert ctx.to_arrow().num_rows == stats.files
    assert ctx.to_polars().height == stats.files
    assert len(ctx.to_pandas()) == stats.files

    records = ctx.to_records()
    assert isinstance(records, list) and records
    assert "path" in records[0]
    assert "ref_id" in ctx.to_records(refs=True)[0]

    assert isinstance(ctx.ref_for(a_code), str)
    assert ctx.global_ref(a_code).startswith("surface-test/")


def test_role_aware_surface(small_tree: Path) -> None:
    """Every incremental role-aware ``Context`` method is callable end-to-end."""
    ctx = Context()
    ctx.add("a short story about the sea", role="user")
    ctx.add(str(small_tree / "README.md"))

    items = ctx.items()
    assert len(items) == 2

    refs = ctx.ref_ids()
    assert len(refs) == 2

    assert isinstance(ctx.to_md(), str)
    assert isinstance(ctx.to_messages(), list)

    records = ctx.to_records()
    assert isinstance(records, list) and len(records) == 2

    for layout in _TREE_LAYOUTS:
        # print_tree renders to the console and returns None; the assertion is
        # that no layout raises (regression guard for the tree-builder fix).
        assert ctx.print_tree(layout=layout) is None

    with pytest.raises(ValueError):
        ctx.print_tree(layout="nope")  # type: ignore[arg-type]


def test_result_types_serialize() -> None:
    """Every public result type exposes a ``to_dict`` that round-trips."""
    assert WcStats(files=1, size=2, lines=3, tokens=4, tok_per_mb=5).to_dict()["files"] == 1
    assert GrepMatch(path="a", line_number=1, line="x").to_dict()["path"] == "a"

    result = GrepResult()
    result.matches.append(GrepMatch(path="a", line_number=1, line="x"))
    result.file_counts["a"] = 1
    assert result.has_matches
    assert len(result.to_dict()["matches"]) == 1
    assert result.to_dict()["file_counts"] == {"a": 1}

    assert CatResult(path="a", content="hi", mode="fast").to_dict()["mode"] == "fast"


def test_mode_guard_raises_clearly(small_tree: Path) -> None:
    """Calling a role-aware method on a directory-scan context fails loudly."""
    ctx = Context(small_tree)
    with pytest.raises(RuntimeError, match="incremental role-aware"):
        ctx.items()
