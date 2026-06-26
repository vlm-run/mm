"""Tests for the Context class."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa


def test_context_creation(small_tree: Path):
    from mm.context import Context

    ctx = Context(small_tree)
    assert ctx.num_files > 0
    assert len(ctx) == ctx.num_files


def test_to_polars(small_tree: Path):
    from mm.context import Context

    ctx = Context(small_tree)
    df = ctx.to_polars()
    assert len(df) == ctx.num_files
    assert "path" in df.columns
    assert "kind" in df.columns
    assert "size" in df.columns


def test_to_pandas(small_tree: Path):
    from mm.context import Context

    ctx = Context(small_tree)
    df = ctx.to_pandas()
    assert len(df) == ctx.num_files
    assert "path" in df.columns
    assert "kind" in df.columns


def test_to_arrow(small_tree: Path):
    from mm.context import Context

    ctx = Context(small_tree)
    table = ctx.to_arrow()
    assert isinstance(table, pa.Table)
    assert table.num_rows == ctx.num_files


def test_sql_query(small_tree: Path):
    from mm.context import Context

    ctx = Context(small_tree)
    result = ctx.sql("SELECT kind, COUNT(*) as n FROM files GROUP BY kind ORDER BY n DESC")
    assert result.num_rows > 0
    assert "kind" in result.column_names
    assert "n" in result.column_names


def test_filter_by_kind(small_tree: Path):
    from mm.context import Context

    ctx = Context(small_tree)
    code_files = ctx.filter(kind="code")
    assert code_files.num_files > 0
    assert code_files.num_files < ctx.num_files


def test_filter_by_ext(small_tree: Path):
    from mm.context import Context

    ctx = Context(small_tree)
    py_files = ctx.filter(ext=".py")
    assert py_files.num_files > 0
    for f in py_files.files:
        assert f.ext == ".py"


def test_filter_chaining(small_tree: Path):
    from mm.context import Context

    ctx = Context(small_tree)
    filtered = ctx.filter(kind="code").filter(ext=".py")
    assert filtered.num_files > 0


def test_files_iteration(small_tree: Path):
    from mm.context import Context

    ctx = Context(small_tree)
    files = ctx.files
    assert len(files) == ctx.num_files
    for f in files:
        assert hasattr(f, "path")
        assert hasattr(f, "kind")
        assert hasattr(f, "size")


def test_cat_text_file(small_tree: Path):
    from mm.context import Context

    ctx = Context(small_tree)
    content = ctx.cat("src/main.py")
    assert "def main" in content


def test_head_file(small_tree: Path):
    from mm.context import Context

    ctx = Context(small_tree)
    head = ctx.head("src/main.py", n=1)
    assert "def main" in head
    lines = head.splitlines()
    assert len(lines) <= 1


def test_grep_pattern(small_tree: Path):
    from mm.context import Context

    ctx = Context(small_tree)
    result = ctx.grep("hello", kind="code")
    assert result.total_matches > 0
    assert all("hello" in m.line for m in result.matches)


def test_save_db(small_tree: Path, isolated_db: Path, persist_ctx):
    from mm.context import Context

    ctx = Context(small_tree)
    # Persistence is the caller's job: export records, then write them.
    db = persist_ctx(ctx)
    # Verify data is in SQLite (filter to this test's root)
    root_str = str(small_tree.resolve()).replace("'", "''")
    f = db.get_files(where=f"uri LIKE '{root_str}%'")
    assert len(f) == ctx.num_files


def test_context_repr(small_tree: Path):
    from mm.context import Context

    ctx = Context(small_tree)
    r = repr(ctx)
    assert "Context" in r
    assert str(ctx.num_files) in r


def test_context_repr_includes_session(small_tree: Path):
    from mm.context import Context

    ctx = Context(small_tree, session_id="ctx-repr-sess")
    assert "ctx-repr-sess" in repr(ctx)


def test_save_db_with_session(small_tree: Path, tmp_path_factory, monkeypatch, persist_ctx):
    from mm.context import Context
    from mm.store.db import MmDatabase

    db_dir = tmp_path_factory.mktemp("mmdb")
    db_path = db_dir / "mm.db"
    monkeypatch.setattr(MmDatabase, "DB_PATH", db_path)
    monkeypatch.setattr(MmDatabase, "DB_DIR", db_dir)

    ctx = Context(small_tree, session_id="save-with-sess")
    persist_ctx(ctx)
    rows = MmDatabase().list_session_files("save-with-sess")
    assert len(rows) == ctx.num_files
    assert all(r["ref_id"] for r in rows)
