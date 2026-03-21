"""Tests for the vlmctx CLI commands.

Covers all 6 subcommands + config, verifying exit codes, JSON output
structure, and basic flag behaviour. Uses the shared `small_tree` fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from vlmctx.cli import app

runner = CliRunner()


# ── find ─────────────────────────────────────────────────────────────


class TestFind:
    def test_exit_zero(self, small_tree: Path):
        assert runner.invoke(app, ["find", str(small_tree)]).exit_code == 0

    def test_kind_filter(self, small_tree: Path):
        r = runner.invoke(app, ["find", str(small_tree), "--kind", "code"])
        assert r.exit_code == 0
        assert ".py" in r.output or ".rs" in r.output or ".js" in r.output

    def test_ext_filter(self, small_tree: Path):
        r = runner.invoke(app, ["find", str(small_tree), "--ext", ".py"])
        assert r.exit_code == 0
        assert "main.py" in r.output

    def test_json_returns_list(self, small_tree: Path):
        r = runner.invoke(app, ["find", str(small_tree), "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert isinstance(data, list)
        assert len(data) > 0
        assert "path" in data[0]

    def test_limit(self, small_tree: Path):
        r = runner.invoke(app, ["find", str(small_tree), "--limit", "2", "--format", "json"])
        data = json.loads(r.output)
        assert len(data) <= 2

    def test_sort_by_size(self, small_tree: Path):
        r = runner.invoke(app, ["find", str(small_tree), "--sort", "size", "--reverse", "--format", "json"])
        data = json.loads(r.output)
        sizes = [row["size"] for row in data]
        assert sizes == sorted(sizes, reverse=True)


# ── ls ───────────────────────────────────────────────────────────────


class TestLs:
    def test_exit_zero(self, small_tree: Path):
        assert runner.invoke(app, ["ls", str(small_tree)]).exit_code == 0

    def test_columns_select(self, small_tree: Path):
        r = runner.invoke(app, ["ls", str(small_tree), "--columns", "path,size,kind"])
        assert r.exit_code == 0

    def test_tree(self, small_tree: Path):
        r = runner.invoke(app, ["ls", str(small_tree), "--tree"])
        assert r.exit_code == 0

    def test_tree_json(self, small_tree: Path):
        r = runner.invoke(app, ["ls", str(small_tree), "--tree", "--format", "json"])
        assert r.exit_code == 0

    def test_schema(self, small_tree: Path):
        r = runner.invoke(app, ["ls", str(small_tree), "--schema"])
        assert r.exit_code == 0

    def test_schema_json_has_columns(self, small_tree: Path):
        r = runner.invoke(app, ["ls", str(small_tree), "--schema", "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        names = [c["column"] for c in data]
        assert "path" in names
        assert "kind" in names
        assert "size" in names

    def test_json_returns_list(self, small_tree: Path):
        r = runner.invoke(app, ["ls", str(small_tree), "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert isinstance(data, list)
        assert len(data) > 0


# ── cat ──────────────────────────────────────────────────────────────


class TestCat:
    def test_text_file_l1(self, small_tree: Path):
        r = runner.invoke(app, ["cat", str(small_tree / "src" / "main.py")])
        assert r.exit_code == 0
        assert "main" in r.output

    def test_text_file_l0(self, small_tree: Path):
        r = runner.invoke(app, ["cat", str(small_tree / "src" / "main.py"), "--level", "0"])
        assert r.exit_code == 0
        assert "def main" in r.output

    def test_head(self, small_tree: Path):
        r = runner.invoke(app, ["cat", str(small_tree / "src" / "main.py"), "-n", "1"])
        assert r.exit_code == 0
        lines = r.output.strip().splitlines()
        assert len(lines) == 1

    def test_tail(self, small_tree: Path):
        r = runner.invoke(app, ["cat", str(small_tree / "src" / "main.py"), "-n", "-1"])
        assert r.exit_code == 0
        lines = r.output.strip().splitlines()
        assert len(lines) == 1

    def test_json_output(self, small_tree: Path):
        r = runner.invoke(app, ["cat", str(small_tree / "src" / "main.py"), "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert len(data) == 1
        assert data[0]["level"] == 1
        assert "content" in data[0]
        assert "path" in data[0]

    def test_nonexistent_file(self, small_tree: Path):
        r = runner.invoke(app, ["cat", str(small_tree / "nope.txt")])
        assert r.exit_code != 0 or "not found" in r.output.lower()

    def test_multiple_files(self, small_tree: Path):
        r = runner.invoke(app, [
            "cat",
            str(small_tree / "src" / "main.py"),
            str(small_tree / "src" / "lib.rs"),
            "--format", "json",
        ])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert len(data) == 2


# ── grep ─────────────────────────────────────────────────────────────


class TestGrep:
    def test_pattern_match(self, small_tree: Path):
        r = runner.invoke(app, ["grep", "hello", str(small_tree)])
        assert r.exit_code == 0
        assert "hello" in r.output

    def test_json_output(self, small_tree: Path):
        r = runner.invoke(app, ["grep", "hello", str(small_tree), "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert isinstance(data, list)

    def test_count_mode(self, small_tree: Path):
        r = runner.invoke(app, ["grep", "hello", str(small_tree), "--count"])
        assert r.exit_code == 0

    def test_kind_filter(self, small_tree: Path):
        r = runner.invoke(app, ["grep", "hello", str(small_tree), "--kind", "code"])
        assert r.exit_code == 0

    def test_no_match(self, small_tree: Path):
        r = runner.invoke(app, ["grep", "zzz_nonexistent_zzz", str(small_tree)])
        assert r.exit_code == 1  # exit 1 on no match (grep/rg convention)


# ── sql ──────────────────────────────────────────────────────────────


class TestSql:
    def test_group_by(self, small_tree: Path):
        r = runner.invoke(app, [
            "sql", "SELECT kind, COUNT(*) as n FROM files GROUP BY kind",
            "--dir", str(small_tree),
        ])
        assert r.exit_code == 0

    def test_json_count(self, small_tree: Path):
        r = runner.invoke(app, [
            "sql", "SELECT COUNT(*) as total FROM files",
            "--dir", str(small_tree), "--format", "json",
        ])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data[0]["total"] > 0

    def test_where_clause(self, small_tree: Path):
        r = runner.invoke(app, [
            "sql", "SELECT name FROM files WHERE ext = '.py'",
            "--dir", str(small_tree), "--format", "json",
        ])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert all(row["name"].endswith(".py") for row in data)


# ── wc ───────────────────────────────────────────────────────────────


class TestWc:
    def test_exit_zero(self, small_tree: Path):
        assert runner.invoke(app, ["wc", str(small_tree)]).exit_code == 0

    def test_by_kind(self, small_tree: Path):
        r = runner.invoke(app, ["wc", str(small_tree), "--by-kind"])
        assert r.exit_code == 0

    def test_json_output(self, small_tree: Path):
        r = runner.invoke(app, ["wc", str(small_tree), "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert "files" in data
        assert "bytes" in data

    def test_by_kind_json(self, small_tree: Path):
        r = runner.invoke(app, ["wc", str(small_tree), "--by-kind", "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert "files" in data
        assert "by_kind" in data
        assert isinstance(data["by_kind"], dict)


# ── config ───────────────────────────────────────────────────────────


class TestConfig:
    def test_show_exit_zero(self):
        r = runner.invoke(app, ["config", "show"])
        assert r.exit_code == 0

    def test_show_json(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("vlmctx.config.CONFIG_PATH_XDG", tmp_path / "vlmctx.toml")
        monkeypatch.setattr("vlmctx.config.CONFIG_DIR_XDG", tmp_path)
        monkeypatch.setattr("vlmctx.config.CONFIG_PATH_LEGACY", tmp_path / "legacy" / "config.toml")
        monkeypatch.setattr("vlmctx.config.CONFIG_DIR_LEGACY", tmp_path / "legacy")
        r = runner.invoke(app, ["config", "show", "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert isinstance(data, dict)
        assert "provider" in data
        assert "base_url" in data["provider"]

    def test_init_creates_file(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "vlmctx.toml"
        monkeypatch.setattr("vlmctx.config.CONFIG_PATH_XDG", config_path)
        monkeypatch.setattr("vlmctx.config.CONFIG_DIR_XDG", tmp_path)
        monkeypatch.setattr("vlmctx.config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("vlmctx.config.CONFIG_PATH_LEGACY", tmp_path / "legacy" / "config.toml")
        monkeypatch.setattr("vlmctx.config.CONFIG_DIR_LEGACY", tmp_path / "legacy")
        r = runner.invoke(app, ["config", "init"])
        assert r.exit_code == 0
        assert config_path.exists()
