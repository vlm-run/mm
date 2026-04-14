"""Tests for the mm CLI commands.

Covers all 6 subcommands + config, verifying exit codes, JSON output
structure, and basic flag behaviour. Uses the shared `small_tree` fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mm.cli import app
from typer.testing import CliRunner

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
        r = runner.invoke(
            app, ["find", str(small_tree), "--sort", "size", "--reverse", "--format", "json"]
        )
        data = json.loads(r.output)
        sizes = [row["size"] for row in data]
        assert sizes == sorted(sizes, reverse=True)

    def test_dataset_jsonl(self, small_tree: Path):
        r = runner.invoke(app, ["find", str(small_tree), "--format", "dataset-jsonl"])
        assert r.exit_code == 0
        lines = [line for line in r.output.strip().splitlines() if line]
        assert len(lines) > 0

        row = json.loads(lines[0])
        assert "path" in row
        assert "kind" in row
        assert "size" in row
        # Each line must be valid JSON
        for line in lines:
            json.loads(line)

    def test_no_ignore_includes_gitignored(self, gitignored_tree: Path):
        """--no-ignore should include files that .gitignore would exclude."""
        # Without --no-ignore: gitignored files are excluded
        r = runner.invoke(app, ["find", str(gitignored_tree), "--format", "json"])
        assert r.exit_code == 0
        paths = {row["path"] for row in json.loads(r.output)}
        assert not any("skip.log" in p for p in paths)
        assert not any("data/" in p for p in paths)

        # With --no-ignore: gitignored files are included
        r = runner.invoke(app, ["find", str(gitignored_tree), "--no-ignore", "--format", "json"])
        assert r.exit_code == 0
        paths = {row["path"] for row in json.loads(r.output)}
        assert any("skip.log" in p for p in paths)
        assert any("file.csv" in p for p in paths)


# ── find (table, tree, schema) ────────────────────────────────────────


class TestFindTable:
    def test_columns_select(self, small_tree: Path):
        r = runner.invoke(app, ["find", str(small_tree), "--columns", "path,size,kind"])
        assert r.exit_code == 0

    def test_tree(self, small_tree: Path):
        r = runner.invoke(app, ["find", str(small_tree), "--tree"])
        assert r.exit_code == 0

    def test_tree_json(self, small_tree: Path):
        r = runner.invoke(app, ["find", str(small_tree), "--tree", "--format", "json"])
        assert r.exit_code == 0

    def test_schema(self, small_tree: Path):
        r = runner.invoke(app, ["find", str(small_tree), "--schema"])
        assert r.exit_code == 0

    def test_schema_json_has_columns(self, small_tree: Path):
        r = runner.invoke(app, ["find", str(small_tree), "--schema", "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        names = [c["column"] for c in data]
        assert "path" in names
        assert "kind" in names
        assert "size" in names

    def test_json_returns_list(self, small_tree: Path):
        r = runner.invoke(app, ["find", str(small_tree), "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_no_ignore_tree(self, gitignored_tree: Path):
        """--no-ignore should include gitignored files in tree mode."""
        r = runner.invoke(app, ["find", str(gitignored_tree), "--tree", "--no-ignore"])
        assert r.exit_code == 0
        assert "skip.log" in r.output
        assert "data" in r.output

    def test_no_ignore_schema(self, gitignored_tree: Path):
        """--no-ignore should work with schema mode."""
        r = runner.invoke(app, ["find", str(gitignored_tree), "--schema", "--no-ignore"])
        assert r.exit_code == 0


# ── cat ──────────────────────────────────────────────────────────────


class TestCat:
    def test_text_file_l1(self, small_tree: Path):
        r = runner.invoke(app, ["cat", str(small_tree / "src" / "main.py")])
        assert r.exit_code == 0
        assert "main" in r.output

    def test_text_file_fast(self, small_tree: Path):
        r = runner.invoke(app, ["cat", str(small_tree / "src" / "main.py"), "-m", "fast"])
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
        assert data[0]["mode"] == "fast"
        assert "content" in data[0]
        assert "path" in data[0]

    def test_nonexistent_file(self, small_tree: Path):
        r = runner.invoke(app, ["cat", str(small_tree / "nope.txt")])
        assert r.exit_code != 0 or "not found" in r.output.lower()

    def test_multiple_files(self, small_tree: Path):
        r = runner.invoke(
            app,
            [
                "cat",
                str(small_tree / "src" / "main.py"),
                str(small_tree / "src" / "lib.rs"),
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert len(data) == 2

    def test_dataset_jsonl(self, small_tree: Path):
        r = runner.invoke(
            app,
            [
                "cat",
                str(small_tree / "src" / "main.py"),
                str(small_tree / "src" / "lib.rs"),
                "--format",
                "dataset-jsonl",
            ],
        )
        assert r.exit_code == 0
        lines = [line for line in r.output.strip().splitlines() if line]
        assert len(lines) == 2

        for line in lines:
            row = json.loads(line)
            assert "name" in row
            assert "path" in row
            assert "type" in row
            assert "size" in row
            assert "content" in row
            assert "mode" in row

    def test_dataset_jsonl_single_file(self, small_tree: Path):
        r = runner.invoke(
            app,
            [
                "cat",
                str(small_tree / "src" / "main.py"),
                "--format",
                "dataset-jsonl",
            ],
        )
        assert r.exit_code == 0
        row = json.loads(r.output.strip())
        assert row["name"] == "main.py"
        assert row["type"] == "text"
        assert "def main" in row["content"]


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

    def test_ignore_case(self, small_tree: Path):
        """--ignore-case / -i should match regardless of casing."""
        # "HELLO" doesn't match "hello" case-sensitively
        r = runner.invoke(app, ["grep", "HELLO", str(small_tree)])
        assert r.exit_code == 1

        # With -i it should match
        r = runner.invoke(app, ["grep", "HELLO", str(small_tree), "-i"])
        assert r.exit_code == 0
        assert "hello" in r.output.lower()

    def test_ignore_case_json(self, small_tree: Path):
        """--ignore-case should work with JSON output."""
        r = runner.invoke(app, ["grep", "HELLO", str(small_tree), "-i", "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert len(data) > 0
        assert any("hello" in m["line"].lower() for m in data)

    def test_no_ignore(self, gitignored_tree: Path):
        """--no-ignore should search inside gitignored files."""
        # The gitignored_tree has skip.log with "log line" and data/file.csv with "a,b,c"
        # Without --no-ignore: gitignored files are not searched
        r = runner.invoke(app, ["grep", "log line", str(gitignored_tree)])
        assert r.exit_code == 1

        # With --no-ignore: gitignored files are included in the search
        r = runner.invoke(app, ["grep", "log line", str(gitignored_tree), "--no-ignore"])
        assert r.exit_code == 0
        assert "skip.log" in r.output

    def test_dataset_jsonl(self, small_tree: Path):
        r = runner.invoke(app, ["grep", "hello", str(small_tree), "--format", "dataset-jsonl"])
        assert r.exit_code == 0
        lines = [line for line in r.output.strip().splitlines() if line]
        assert len(lines) > 0
        row = json.loads(lines[0])
        assert "path" in row
        assert "line_number" in row
        assert "line" in row

    def test_dataset_jsonl_count(self, small_tree: Path):
        r = runner.invoke(
            app, ["grep", "hello", str(small_tree), "--count", "--format", "dataset-jsonl"]
        )
        assert r.exit_code == 0
        lines = [line for line in r.output.strip().splitlines() if line]
        assert len(lines) > 0
        row = json.loads(lines[0])
        assert "path" in row
        assert "count" in row


# ── sql ──────────────────────────────────────────────────────────────


class TestSql:
    def test_group_by(self, small_tree: Path):
        r = runner.invoke(
            app,
            [
                "sql",
                "SELECT kind, COUNT(*) as n FROM files GROUP BY kind",
                "--dir",
                str(small_tree),
                "--pre-index",
            ],
        )
        assert r.exit_code == 0

    def test_json_count(self, small_tree: Path):
        r = runner.invoke(
            app,
            [
                "sql",
                "SELECT COUNT(*) as total FROM files",
                "--dir",
                str(small_tree),
                "--format",
                "json",
                "--pre-index",
            ],
        )
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data[0]["total"] > 0

    def test_where_clause(self, small_tree: Path):
        r = runner.invoke(
            app,
            [
                "sql",
                "SELECT name FROM files WHERE ext = '.py'",
                "--dir",
                str(small_tree),
                "--format",
                "json",
                "--pre-index",
            ],
        )
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert all(row["name"].endswith(".py") for row in data)

    def test_dataset_jsonl(self, small_tree: Path):
        r = runner.invoke(
            app,
            [
                "sql",
                "SELECT name, kind, size FROM files ORDER BY name",
                "--dir",
                str(small_tree),
                "--format",
                "dataset-jsonl",
                "--pre-index",
            ],
        )
        assert r.exit_code == 0
        lines = [line for line in r.output.strip().splitlines() if line]
        assert len(lines) > 0
        row = json.loads(lines[0])
        assert "name" in row
        assert "kind" in row
        assert "size" in row


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
        assert "size" in data
        assert "tokens (est.)" in data
        assert "tok_per_mb" in data

    def test_by_kind_json(self, small_tree: Path):
        r = runner.invoke(app, ["wc", str(small_tree), "--by-kind", "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert "files" in data
        assert "by_kind" in data
        assert isinstance(data["by_kind"], dict)

    def test_dataset_jsonl(self, small_tree: Path):
        r = runner.invoke(app, ["wc", str(small_tree), "--format", "dataset-jsonl"])
        assert r.exit_code == 0
        lines = [line for line in r.output.strip().splitlines() if line]
        assert len(lines) >= 1
        for line in lines:
            row = json.loads(line)
            assert "files" in row or "kind" in row

    def test_dataset_jsonl_by_kind(self, small_tree: Path):
        r = runner.invoke(app, ["wc", str(small_tree), "--by-kind", "--format", "dataset-jsonl"])
        assert r.exit_code == 0
        lines = [line for line in r.output.strip().splitlines() if line]
        assert len(lines) > 1  # multiple kinds
        row = json.loads(lines[0])
        assert "kind" in row
        assert "files" in row
        assert "tokens (est.)" in row


# ── dataset-hf ──────────────────────────────────────────────────────


class TestDatasetHf:
    """Tests for --format dataset-hf (requires 'datasets' package)."""

    def test_emit_rows_roundtrip(self, tmp_path: Path):
        datasets = pytest.importorskip("datasets")
        from mm.display import emit_rows

        rows = [
            {"name": "a.png", "type": "image", "size": 1024, "content": "dims: 100x100"},
            {"name": "b.py", "type": "code", "size": 256, "content": "print('hi')"},
        ]
        out = str(tmp_path / "ds_out")
        emit_rows("dataset-hf", rows, output_dir=out)

        ds = datasets.load_from_disk(out)
        assert len(ds) == 2
        assert ds[0]["name"] == "a.png"
        assert ds[1]["type"] == "code"
        assert ds[1]["content"] == "print('hi')"

    def test_cat_dataset_hf(self, small_tree: Path, tmp_path: Path):
        datasets = pytest.importorskip("datasets")

        out = str(tmp_path / "cat_ds")
        r = runner.invoke(
            app,
            [
                "cat",
                str(small_tree / "src" / "main.py"),
                str(small_tree / "src" / "lib.rs"),
                "--format",
                "dataset-hf",
                "--output-dir",
                out,
            ],
        )
        assert r.exit_code == 0

        ds = datasets.load_from_disk(out)
        assert len(ds) == 2

        names = {str(ds[i]["name"]) for i in range(len(ds))}
        assert "main.py" in names
        assert "lib.rs" in names

        # Verify content was extracted
        for i in range(len(ds)):
            assert len(ds[i]["content"]) > 0

    def test_find_dataset_hf(self, small_tree: Path, tmp_path: Path, monkeypatch):
        datasets = pytest.importorskip("datasets")

        # find writes to mm_dataset/ by default — chdir to tmp so it lands there
        monkeypatch.chdir(tmp_path)
        r = runner.invoke(app, ["find", str(small_tree), "--format", "dataset-hf"])
        assert r.exit_code == 0

        ds = datasets.load_from_disk(str(tmp_path / "mm_dataset"))
        assert len(ds) > 0
        assert "path" in ds.column_names
        assert "kind" in ds.column_names

    def test_grep_dataset_hf(self, small_tree: Path, tmp_path: Path, monkeypatch):
        datasets = pytest.importorskip("datasets")

        monkeypatch.chdir(tmp_path)
        r = runner.invoke(app, ["grep", "hello", str(small_tree), "--format", "dataset-hf"])
        assert r.exit_code == 0

        ds = datasets.load_from_disk(str(tmp_path / "mm_dataset"))
        assert len(ds) > 0
        assert "path" in ds.column_names
        assert "line" in ds.column_names


# ── config ───────────────────────────────────────────────────────────


class TestConfig:
    def test_show_exit_zero(self):
        r = runner.invoke(app, ["config", "show"])
        assert r.exit_code == 0

    def test_show_json(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("mm.config.CONFIG_PATH_XDG", tmp_path / "mm.toml")
        monkeypatch.setattr("mm.config.CONFIG_DIR_XDG", tmp_path)
        monkeypatch.setattr("mm.config.CONFIG_PATH_LEGACY", tmp_path / "legacy" / "config.toml")
        monkeypatch.setattr("mm.config.CONFIG_DIR_LEGACY", tmp_path / "legacy")
        r = runner.invoke(app, ["config", "show", "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert isinstance(data, dict)
        assert "mode" in data
        assert "fast" in data["mode"]

    def test_init_creates_file(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "mm.toml"
        monkeypatch.setattr("mm.config.CONFIG_PATH_XDG", config_path)
        monkeypatch.setattr("mm.config.CONFIG_DIR_XDG", tmp_path)
        monkeypatch.setattr("mm.config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("mm.config.CONFIG_PATH_LEGACY", tmp_path / "legacy" / "config.toml")
        monkeypatch.setattr("mm.config.CONFIG_DIR_LEGACY", tmp_path / "legacy")
        r = runner.invoke(app, ["config", "init"])
        assert r.exit_code == 0
        assert config_path.exists()
