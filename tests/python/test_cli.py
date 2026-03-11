"""Tests for the vlmctx CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from vlmctx.cli import app

runner = CliRunner()


def test_find_basic(small_tree: Path):
    result = runner.invoke(app, ["find", str(small_tree)])
    assert result.exit_code == 0


def test_find_with_kind(small_tree: Path):
    result = runner.invoke(app, ["find", str(small_tree), "--kind", "code"])
    assert result.exit_code == 0


def test_find_with_ext(small_tree: Path):
    result = runner.invoke(app, ["find", str(small_tree), "--ext", ".py"])
    assert result.exit_code == 0


def test_find_json(small_tree: Path):
    result = runner.invoke(app, ["find", str(small_tree), "--json"])
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) > 0


def test_ls_basic(small_tree: Path):
    result = runner.invoke(app, ["ls", str(small_tree)])
    assert result.exit_code == 0


def test_ls_with_columns(small_tree: Path):
    result = runner.invoke(app, ["ls", str(small_tree), "--columns", "path,size,kind"])
    assert result.exit_code == 0


def test_ls_tree(small_tree: Path):
    result = runner.invoke(app, ["ls", str(small_tree), "--tree"])
    assert result.exit_code == 0


def test_ls_schema(small_tree: Path):
    result = runner.invoke(app, ["ls", str(small_tree), "--schema"])
    assert result.exit_code == 0


def test_cat_file(small_tree: Path):
    result = runner.invoke(app, ["cat", str(small_tree / "src" / "main.py")])
    assert result.exit_code == 0
    assert "main" in result.output


def test_cat_head(small_tree: Path):
    result = runner.invoke(app, ["cat", str(small_tree / "src" / "main.py"), "-n", "1"])
    assert result.exit_code == 0


def test_cat_tail(small_tree: Path):
    result = runner.invoke(app, ["cat", str(small_tree / "src" / "main.py"), "-n", "-1"])
    assert result.exit_code == 0


def test_grep_basic(small_tree: Path):
    result = runner.invoke(app, ["grep", "hello", str(small_tree)])
    assert result.exit_code == 0


def test_grep_json(small_tree: Path):
    result = runner.invoke(app, ["grep", "hello", str(small_tree), "--json"])
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert isinstance(data, list)


def test_grep_count(small_tree: Path):
    result = runner.invoke(app, ["grep", "hello", str(small_tree), "--count"])
    assert result.exit_code == 0


def test_sql_basic(small_tree: Path):
    result = runner.invoke(app, [
        "sql",
        "SELECT kind, COUNT(*) as n FROM files GROUP BY kind",
        "--dir", str(small_tree),
    ])
    assert result.exit_code == 0


def test_sql_json(small_tree: Path):
    result = runner.invoke(app, [
        "sql",
        "SELECT COUNT(*) as total FROM files",
        "--dir", str(small_tree),
        "--json",
    ])
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert data[0]["total"] > 0


def test_wc_basic(small_tree: Path):
    result = runner.invoke(app, ["wc", str(small_tree)])
    assert result.exit_code == 0
