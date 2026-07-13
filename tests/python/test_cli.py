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

    def test_kind_filter_comma_separated(self, small_tree: Path):
        """--kind image,code should return files of both kinds."""
        r = runner.invoke(
            app, ["find", str(small_tree), "--kind", "image,code", "--format", "json"]
        )
        assert r.exit_code == 0
        data = json.loads(r.output)
        kinds = {row["kind"] for row in data}
        assert "image" in kinds
        assert "code" in kinds
        assert kinds <= {"image", "code"}

    def test_kind_filter_comma_separated_with_spaces(self, small_tree: Path):
        """--kind 'image, code' (with spaces) should still work."""
        r = runner.invoke(
            app, ["find", str(small_tree), "--kind", "image, code", "--format", "json"]
        )
        assert r.exit_code == 0
        data = json.loads(r.output)
        kinds = {row["kind"] for row in data}
        assert "image" in kinds
        assert "code" in kinds

    def test_kind_filter_single_still_works(self, small_tree: Path):
        """Single --kind value should still work after comma-separated support."""
        r = runner.invoke(app, ["find", str(small_tree), "--kind", "image", "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert all(row["kind"] == "image" for row in data)
        assert len(data) > 0

    def test_ignore_case(self, small_tree: Path):
        """--ignore-case / -i should make --name matching case-insensitive."""
        # small_tree contains README.md (uppercase) and readme.md (lowercase).
        # Case-sensitive: "README" only matches README.md.
        r = runner.invoke(app, ["find", str(small_tree), "-n", "README", "--format", "json"])
        assert r.exit_code == 0
        names = {row["name"] for row in json.loads(r.output)}
        assert "README.md" in names
        assert "readme.md" not in names

        # With -i: both README.md and readme.md should match.
        r = runner.invoke(app, ["find", str(small_tree), "-n", "README", "-i", "--format", "json"])
        assert r.exit_code == 0
        names = {row["name"] for row in json.loads(r.output)}
        assert {"README.md", "readme.md"} <= names

    def test_ignore_case_regex(self, small_tree: Path):
        """-i should combine with regex patterns (fast path via Rust)."""
        r = runner.invoke(
            app,
            ["find", str(small_tree), "-n", r"^MAIN\.PY$", "-i", "--format", "json"],
        )
        assert r.exit_code == 0
        names = {row["name"] for row in json.loads(r.output)}
        assert "main.py" in names

    def test_ignore_case_requires_name(self, small_tree: Path):
        """--ignore-case without --name should error."""
        r = runner.invoke(app, ["find", str(small_tree), "-i"])
        assert r.exit_code != 0

    def test_ignore_case_tree(self, small_tree: Path):
        """-i should work with --tree mode."""
        r = runner.invoke(app, ["find", str(small_tree), "--tree", "-n", "README", "-i"])
        assert r.exit_code == 0
        assert "README.md" in r.output
        assert "readme.md" in r.output


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
    def test_text_file_default(self, small_tree: Path):
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

    def test_json_output(self, small_tree: Path, isolated_db: Path):
        r = runner.invoke(app, ["cat", str(small_tree / "src" / "main.py"), "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.stdout)
        assert len(data) == 1
        # Default mode is ``fast``.
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
        data = json.loads(r.stdout)
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


class TestCatLargeBatch:
    """Large multi-file ``cat`` prompts or requires ``--yes`` (threshold configurable)."""

    @staticmethod
    def _write_n_files(base: Path, n: int) -> list[str]:
        base.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []
        for i in range(n):
            p = base / f"batch_{i}.txt"
            p.write_text(f"x{i}\n")
            paths.append(str(p))
        return paths

    def test_below_threshold_no_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MM_CAT_BATCH_CONFIRM_THRESHOLD", "9")
        paths = self._write_n_files(tmp_path, 8)
        r = runner.invoke(app, ["cat", *paths, "--format", "json"])
        assert r.exit_code == 0

    def test_at_threshold_blocks_without_yes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MM_CAT_BATCH_CONFIRM_THRESHOLD", "9")
        paths = self._write_n_files(tmp_path, 9)
        r = runner.invoke(app, ["cat", *paths, "--format", "json"])
        assert r.exit_code == 1
        out = r.output + (r.stderr or "")
        assert "--yes" in out or "-y" in out

    def test_at_threshold_succeeds_with_short_yes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("MM_CAT_BATCH_CONFIRM_THRESHOLD", "9")
        paths = self._write_n_files(tmp_path, 9)
        r = runner.invoke(app, ["cat", *paths, "--format", "json", "-y"])
        assert r.exit_code == 0

    def test_at_threshold_succeeds_with_long_yes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("MM_CAT_BATCH_CONFIRM_THRESHOLD", "9")
        paths = self._write_n_files(tmp_path, 9)
        r = runner.invoke(app, ["cat", *paths, "--format", "json", "--yes"])
        assert r.exit_code == 0

    def test_default_threshold_uses_nine_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Without env override, 8 paths OK and 9 paths require -y (non-interactive)."""
        monkeypatch.delenv("MM_CAT_BATCH_CONFIRM_THRESHOLD", raising=False)
        paths8 = self._write_n_files(tmp_path / "a", 8)
        r8 = runner.invoke(app, ["cat", *paths8, "--format", "json"])
        assert r8.exit_code == 0
        paths9 = self._write_n_files(tmp_path / "b", 9)
        r9 = runner.invoke(app, ["cat", *paths9, "--format", "json"])
        assert r9.exit_code == 1


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
        r = runner.invoke(app, ["grep", "HELLO", str(small_tree)])
        assert r.exit_code == 1

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
        r = runner.invoke(app, ["grep", "log line", str(gitignored_tree)])
        assert r.exit_code == 1
        assert "skip.log" not in r.output

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

    def test_dataset_hf(self, small_tree: Path, tmp_path: Path, monkeypatch):
        """``grep --format dataset-hf`` writes a HuggingFace dataset to ``mm_dataset/``."""
        datasets = pytest.importorskip("datasets")

        monkeypatch.chdir(tmp_path)
        r = runner.invoke(app, ["grep", "hello", str(small_tree), "--format", "dataset-hf"])
        assert r.exit_code == 0

        ds = datasets.load_from_disk(str(tmp_path / "mm_dataset"))
        assert len(ds) > 0
        assert "path" in ds.column_names
        assert "line" in ds.column_names

    def test_kind_filter_comma_separated(self, small_tree: Path):
        """--kind document,code should search across both kinds."""
        r = runner.invoke(app, ["grep", "hello", str(small_tree), "--kind", "document,code"])
        assert r.exit_code == 0
        assert "hello" in r.output

    def test_kind_filter_comma_separated_excludes_others(self, small_tree: Path):
        """--kind config,text should not match content only in code files."""
        r = runner.invoke(app, ["grep", "def main", str(small_tree), "--kind", "document,text"])
        assert r.exit_code == 1
        assert "def main" not in r.output

    def test_smart_case_lowercase_pattern_matches_mixed_content(self, tmp_path: Path):
        """All-lowercase pattern matches mixed-case content (smart-case on)."""
        (tmp_path / "doc.txt").write_text("Go Paperless, Go Green!\n")
        r = runner.invoke(app, ["grep", "go paperless", str(tmp_path)])
        assert r.exit_code == 0
        assert "Go Paperless" in r.output

    def test_smart_case_uppercase_in_pattern_stays_case_sensitive(self, tmp_path: Path):
        """Any uppercase letter in pattern preserves case-sensitivity."""
        (tmp_path / "doc.txt").write_text("Go Paperless\n")
        r = runner.invoke(app, ["grep", "Paperless", str(tmp_path)])
        assert r.exit_code == 0
        r = runner.invoke(app, ["grep", "PAPERLESS", str(tmp_path)])
        assert r.exit_code == 1

    def test_smart_case_overridden_by_ignore_case_flag(self, tmp_path: Path):
        """-i forces case-insensitive even when the pattern contains uppercase."""
        (tmp_path / "doc.txt").write_text("Go Paperless\n")
        r = runner.invoke(app, ["grep", "PAPERLESS", str(tmp_path), "-i"])
        assert r.exit_code == 0
        assert "Paperless" in r.output

    def test_smart_case_ignores_uppercase_in_regex_escapes(self, tmp_path: Path):
        """Uppercase inside regex escapes (\\S, \\W, \\D, \\B) shouldn't flip
        smart-case off — they're metacharacters, not user-intended literals."""
        (tmp_path / "doc.txt").write_text("LARGE WORLD\n")
        r = runner.invoke(app, ["grep", r"\S+ world", str(tmp_path)])
        assert r.exit_code == 0
        assert "LARGE WORLD" in r.output

    def test_smart_case_explicit_character_class_stays_case_sensitive(self, tmp_path: Path):
        """An explicit [A-Z] in the pattern is user-intended uppercase — smart-case
        stays off (matching ripgrep's behavior)."""
        (tmp_path / "doc.txt").write_text("Hello world\n")
        r = runner.invoke(app, ["grep", "[A-Z]ello", str(tmp_path)])
        assert r.exit_code == 0
        (tmp_path / "doc.txt").write_text("hello world\n")
        r = runner.invoke(app, ["grep", "[A-Z]ello", str(tmp_path)])
        assert r.exit_code == 1

    def test_fts_snippet_includes_match_when_buried_in_chunk(
        self, tmp_path: Path, isolated_db: Path
    ):
        """The displayed line for an FTS hit must contain the matching phrase even
        when it sits in the middle of a long chunk — the chunk's head/tail must
        not be the only thing shown, or the match would be cropped out."""
        from mm.store.db import MmDatabase
        from mm.store.utils import now_us

        img = tmp_path / "shot.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

        prefix = ("noisetoken-" + "x" * 8 + " ") * 60
        suffix = ("filler-" + "y" * 8 + " ") * 60
        chunk = prefix + "the quantum cloud is here " + suffix

        db = MmDatabase()
        db.ensure_metadata(str(img))
        now = now_us()
        db._connect.execute(
            "INSERT INTO extractions (id, file_uri, content_hash, profile, model, mode, "
            "detail, extra, summary, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("l2-snip", str(img), "h", "p", "m", "accurate", 0, "", "summary", now),
        )
        db._connect.execute(
            "INSERT INTO chunks (extraction_id, file_uri, content_hash, profile, model, "
            "mode, chunk_idx, chunk_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("l2-snip", str(img), "h", "p", "m", "accurate", 0, chunk, now),
        )
        db._connect.commit()

        r = runner.invoke(app, ["grep", "quantum cloud", str(tmp_path)])
        assert r.exit_code == 0
        # The displayed line must include the matched phrase — the bug was that
        # only the chunk's prefix[:90] and suffix[-50:] were shown, hiding it.
        assert "quantum cloud" in r.output

    def test_fts_finds_indexed_chunk_in_binary(self, tmp_path: Path, isolated_db: Path):
        """FTS additively surfaces hits inside indexed chunks; regex never sees the
        binary bytes of an image, but FTS can match the -m=accurate chunk text seeded for it.
        """
        from mm.store.db import MmDatabase
        from mm.store.utils import now_us

        img = tmp_path / "photo.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

        db = MmDatabase()
        db.ensure_metadata(str(img))
        now = now_us()
        db._connect.execute(
            "INSERT INTO extractions (id, file_uri, content_hash, profile, model, mode, "
            "detail, extra, summary, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("l2-1", str(img), "h", "p", "m", "accurate", 0, "", "summary", now),
        )
        db._connect.execute(
            "INSERT INTO chunks (extraction_id, file_uri, content_hash, profile, model, "
            "mode, chunk_idx, chunk_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "l2-1",
                str(img),
                "h",
                "p",
                "m",
                "accurate",
                0,
                "the quick brown fox jumps over the lazy dog",
                now,
            ),
        )
        db._connect.commit()

        r = runner.invoke(app, ["grep", "quick brown", str(tmp_path)])
        assert r.exit_code == 0
        assert "photo.png" in r.output

    def test_fts_matches_substring_inside_token(self, tmp_path: Path, isolated_db: Path):
        """``fts_search`` must surface hits when the query is a substring of
        indexed words, not just a token prefix.
        """
        from mm.store.db import MmDatabase
        from mm.store.utils import now_us

        img = tmp_path / "doc.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

        db = MmDatabase()
        db.ensure_metadata(str(img))
        now = now_us()
        db._connect.execute(
            "INSERT INTO extractions (id, file_uri, content_hash, profile, model, mode, "
            "detail, extra, summary, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("l2-sub", str(img), "h", "p", "m", "accurate", 0, "", "summary", now),
        )
        db._connect.execute(
            "INSERT INTO chunks (extraction_id, file_uri, content_hash, profile, model, "
            "mode, chunk_idx, chunk_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("l2-sub", str(img), "h", "p", "m", "accurate", 0, "Breaking the Quantum Loop", now),
        )
        db._connect.commit()

        from mm.fts import fts_search

        # Mid-token substring, mixed case.
        hits = fts_search("ntum Loop", uri_prefix=str(tmp_path))
        assert len(hits) == 1
        # Mid-token substring, uppercase.
        hits_upper = fts_search("ntum LOOP", uri_prefix=str(tmp_path))
        assert len(hits_upper) == 1

        r = runner.invoke(app, ["grep", "ntum Loop", str(tmp_path), "--kind", "image"])
        assert r.exit_code == 0
        assert "doc.png" in r.output

    def test_fts_kind_filter_pushed_into_sql(self, tmp_path: Path, isolated_db: Path):
        """``--kind`` filters FTS hits via JOIN on ``files``: only matching kinds
        come back, even when the wrong-kind chunk has the same text."""
        from mm.store.db import MmDatabase
        from mm.store.utils import now_us

        img = tmp_path / "photo.png"
        txt = tmp_path / "notes.txt"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        txt.write_text("placeholder so the file exists\n")

        db = MmDatabase()
        db.ensure_metadata(str(img))
        db.ensure_metadata(str(txt))
        now = now_us()
        # Seed identical chunk text under both files so kind alone determines the hit.
        for idx, (uri, extraction_id) in enumerate([(str(img), "l2-img"), (str(txt), "l2-txt")]):
            db._connect.execute(
                "INSERT INTO extractions (id, file_uri, content_hash, profile, model, mode, "
                "detail, extra, summary, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (extraction_id, uri, "h", "p", "m", "accurate", 0, "", "summary", now),
            )
            db._connect.execute(
                "INSERT INTO chunks (extraction_id, file_uri, content_hash, profile, model, "
                "mode, chunk_idx, chunk_text, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (extraction_id, uri, "h", "p", "m", "accurate", idx, "rare phrase only here", now),
            )
        db._connect.commit()

        r = runner.invoke(app, ["grep", "rare phrase", str(tmp_path), "--kind", "image"])
        assert r.exit_code == 0
        assert "photo.png" in r.output
        assert "notes.txt" not in r.output

    def test_fts_preserves_punctuation_in_query(self, tmp_path: Path, isolated_db: Path):
        """Queries containing apostrophes/hyphens/dots must match content that
        contains them verbatim. The trigram tokenizer indexes punctuation as
        regular characters; stripping it on the way in (e.g. ``\\w+`` extraction)
        would turn ``won't`` into ``won t`` and miss the content.
        """
        from mm.fts import fts_search
        from mm.store.db import MmDatabase
        from mm.store.utils import now_us

        img = tmp_path / "punct.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

        db = MmDatabase()
        db.ensure_metadata(str(img))
        now = now_us()
        db._connect.execute(
            "INSERT INTO extractions (id, file_uri, content_hash, profile, model, mode, "
            "detail, extra, summary, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("l2-p", str(img), "h", "p", "m", "accurate", 0, "", "summary", now),
        )
        db._connect.execute(
            "INSERT INTO chunks (extraction_id, file_uri, content_hash, profile, model, "
            "mode, chunk_idx, chunk_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "l2-p",
                str(img),
                "h",
                "p",
                "m",
                "accurate",
                0,
                "I won't ship hello-world v1.0 today, it's still WIP.",
                now,
            ),
        )
        db._connect.commit()

        for q in ["won't", "hello-world", "v1.0", "it's still"]:
            assert len(fts_search(q, uri_prefix=str(tmp_path))) == 1, (
                f"punctuation query {q!r} must match"
            )

        # Empty/whitespace queries short-circuit to [].
        assert fts_search("", uri_prefix=str(tmp_path)) == []
        assert fts_search("   ", uri_prefix=str(tmp_path)) == []

    def test_fts_escapes_like_wildcards_in_query(self, tmp_path: Path, isolated_db: Path):
        """Underscore and percent in the user query must be treated literally."""
        from mm.fts import fts_search
        from mm.store.db import MmDatabase
        from mm.store.utils import now_us

        img = tmp_path / "wild.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

        db = MmDatabase()
        db.ensure_metadata(str(img))
        now = now_us()
        db._connect.execute(
            "INSERT INTO extractions (id, file_uri, content_hash, profile, model, mode, "
            "detail, extra, summary, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("l2-w", str(img), "h", "p", "m", "accurate", 0, "", "summary", now),
        )
        # Three chunks: only chunk 0 contains the literal query strings; the
        # others would slip past an unescaped LIKE.
        seeded = [
            (0, "literal user_id and 100% appear here"),
            (1, "userxid and 100 percent are decoys"),
            (2, "user-id and 1000 are also decoys"),
        ]
        for idx, text in seeded:
            db._connect.execute(
                "INSERT INTO chunks (extraction_id, file_uri, content_hash, profile, model, "
                "mode, chunk_idx, chunk_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("l2-w", str(img), "h", "p", "m", "accurate", idx, text, now),
            )
        db._connect.commit()

        for q in ["user_id", "100%"]:
            hits = fts_search(q, uri_prefix=str(tmp_path), limit=10)
            assert len(hits) == 1, f"{q!r} must match exactly chunk 0, got {len(hits)}"
            assert hits[0]["index"] == 0


# ── peek ─────────────────────────────────────────────────────────────


class TestPeek:
    def test_rich_default_shows_kind(self, small_tree: Path):
        r = runner.invoke(app, ["peek", str(small_tree / "icon.png")])
        assert r.exit_code == 0
        assert "icon.png" in r.output
        assert "image" in r.output

    def test_json_emits_list(self, small_tree: Path):
        r = runner.invoke(app, ["peek", str(small_tree / "src" / "main.py"), "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert isinstance(data, list) and len(data) == 1
        assert data[0]["kind"] == "text"

    def test_multi_file_emits_one_row_each(self, small_tree: Path):
        r = runner.invoke(
            app,
            [
                "peek",
                str(small_tree / "icon.png"),
                str(small_tree / "src" / "main.py"),
                "--format",
                "json",
            ],
        )
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert {row["kind"] for row in data} == {"image", "text"}


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

    def test_kind_filter_comma_separated(self, small_tree: Path):
        """--kind code,image should count files of both kinds."""
        r = runner.invoke(app, ["wc", str(small_tree), "--kind", "code,image", "--format", "json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["files"] > 0

    def test_kind_filter_comma_separated_subset(self, small_tree: Path):
        """Comma-separated kind should return fewer files than unfiltered."""
        r_all = runner.invoke(app, ["wc", str(small_tree), "--format", "json"])
        r_subset = runner.invoke(
            app, ["wc", str(small_tree), "--kind", "code,image", "--format", "json"]
        )
        all_data = json.loads(r_all.output)
        subset_data = json.loads(r_subset.output)
        assert subset_data["files"] < all_data["files"]


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


# ── prune integration: deleted files are pruned from DB across sql/cat/grep ──


class TestPruneIntegration:
    """End-to-end: a file indexed in DB and later deleted from disk must not
    leak through ``sql``, ``cat``, or ``grep`` output. Verifies the wiring of
    :func:`mm.store.utils.prune_missing` in each command path.
    """

    def test_sql_prunes_stale_rows(self, tmp_path: Path, isolated_db: Path):
        from mm.store.db import MmDatabase

        a, b = tmp_path / "a.txt", tmp_path / "b.txt"
        a.write_text("hello")
        b.write_text("world")
        db = MmDatabase()
        db.ensure_metadata(str(a))
        db.ensure_metadata(str(b))
        assert len(db.get_files()) == 2

        a.unlink()

        r = runner.invoke(
            app, ["sql", "SELECT uri FROM files", "--dir", str(tmp_path), "--format", "json"]
        )
        assert r.exit_code == 0
        uris = {row["uri"] for row in json.loads(r.output)}
        assert str(a) not in uris
        assert str(b) in uris

        # Row is physically gone from the DB, not just filtered from output.
        assert db.get_file(str(a)) is None
        assert db.get_file(str(b)) is not None

    def test_cat_prunes_row_when_path_missing(self, tmp_path: Path, isolated_db: Path):
        from mm.store.db import MmDatabase

        p = tmp_path / "gone.txt"
        p.write_text("bye")
        db = MmDatabase()
        db.ensure_metadata(str(p))
        assert db.get_file(str(p)) is not None

        p.unlink()

        r = runner.invoke(app, ["cat", str(p)])
        # cat exits 0 but emits "Error: ... not found." on stderr (mixed).
        assert "not found" in r.output
        assert db.get_file(str(p)) is None


# ── cat --report ─────────────────────────────────────────────────────


class TestCatReport:
    """``--report`` generates self-contained HTML of pipeline internals."""

    @staticmethod
    def _make_png(path: Path, size: int = 10, color: str = "red") -> None:
        """Write a minimal valid PNG."""
        from PIL import Image

        Image.new("RGB", (size, size), color=color).save(path, "PNG")

    def test_report_text_file_no_html(self, small_tree: Path, tmp_path: Path, monkeypatch):
        """Passthrough (text) files produce no report HTML."""
        monkeypatch.chdir(tmp_path)
        r = runner.invoke(app, ["cat", str(small_tree / "src" / "main.py"), "--report"])
        assert r.exit_code == 0
        reports_dir = tmp_path / "mm_reports"
        assert not reports_dir.exists() or not list(reports_dir.glob("*.html"))

    def test_report_image_writes_html(self, isolated_db: Path, tmp_path: Path, monkeypatch):
        """``--report --no-generate`` on an image writes an HTML file."""
        monkeypatch.chdir(tmp_path)
        img = tmp_path / "test.png"
        self._make_png(img)
        r = runner.invoke(
            app,
            ["cat", str(img), "--report", "--no-generate", "--no-cache"],
        )
        assert r.exit_code == 0
        reports = list((tmp_path / "mm_reports").glob("*.html"))
        assert len(reports) == 1
        html_content = reports[0].read_text()
        assert "<!DOCTYPE html>" in html_content
        assert "test.png" in html_content

    def test_report_multi_file_combined(self, isolated_db: Path, tmp_path: Path, monkeypatch):
        """Multiple files produce a single ``multi_`` report."""
        monkeypatch.chdir(tmp_path)
        img1 = tmp_path / "a.png"
        img2 = tmp_path / "b.png"
        self._make_png(img1, color="red")
        self._make_png(img2, color="blue")
        r = runner.invoke(
            app,
            [
                "cat",
                str(img1),
                str(img2),
                "--report",
                "--no-generate",
                "--no-cache",
            ],
        )
        assert r.exit_code == 0
        reports = list((tmp_path / "mm_reports").glob("*.html"))
        assert len(reports) == 1
        assert reports[0].name.startswith("multi_")

    def test_report_cached_skipped(self, isolated_db: Path, tmp_path: Path, monkeypatch):
        """Cache hit skips report — no HTML file written."""
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)
        img = tmp_path / "cached.png"
        self._make_png(img)
        # First run with mocked LLM to populate cache (no report)
        with patch("mm.llm.LlmBackend._chat", return_value="A red square."):
            r1 = runner.invoke(
                app,
                ["cat", str(img), "--no-cache"],
            )
        assert r1.exit_code == 0
        # Second run with --report (cache hit) — no HTML should be written
        r2 = runner.invoke(
            app,
            ["cat", str(img), "--report"],
        )
        assert r2.exit_code == 0
        reports_dir = tmp_path / "mm_reports"
        assert not reports_dir.exists() or not list(reports_dir.glob("*.html"))
