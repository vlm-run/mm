"""Tests for mm.lancedb — MmDatabase, schema, and end-to-end operations."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pytest
from mm.lancedb import MmDatabase
from mm.lancedb.schema import (
    ChunkCol,
    FileCol,
    L2Col,
    chunks_schema,
    files_schema,
    l2_results_schema,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path: Path) -> MmDatabase:
    """Create an isolated MmDatabase in a temp directory."""
    return MmDatabase(db_path=tmp_path / "test.lance")


def _scanner_table(
    paths: list[str],
    kinds: list[str] | None = None,
) -> pa.Table:
    """Build a minimal scanner-like Arrow table with relative paths."""
    n = len(paths)
    if kinds is None:
        kinds = ["text"] * n
    return pa.table(
        {
            "path": paths,
            "name": [p.split("/")[-1] for p in paths],
            "stem": [p.split("/")[-1].rsplit(".", 1)[0] for p in paths],
            "ext": ["." + p.split(".")[-1] if "." in p else "" for p in paths],
            "size": pa.array([100] * n, type=pa.uint64()),
            "modified": pa.array([1712000000000000] * n, type=pa.timestamp("us")),
            "created": pa.array([1712000000000000] * n, type=pa.timestamp("us")),
            "mime": ["text/plain"] * n,
            "kind": kinds,
            "is_binary": [False] * n,
            "depth": pa.array([0] * n, type=pa.uint16()),
            "parent": [""] * n,
            "width": pa.array([None] * n, type=pa.uint32()),
            "height": pa.array([None] * n, type=pa.uint32()),
        }
    )


ROOT = Path("/test/data")


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestSchema:
    def test_files_schema_field_count(self):
        schema = files_schema()
        # 14 L0 + 18 L1 + 2 tracking = 34
        assert len(schema) == 34

    def test_l2_results_schema_field_count(self):
        assert len(l2_results_schema()) == 9

    def test_chunks_schema_field_count(self):
        # No vector column in base schema
        assert len(chunks_schema()) == 8

    def test_column_enums_are_strings(self):
        assert FileCol.URI == "uri"
        assert L2Col.SUMMARY == "summary"
        assert ChunkCol.CHUNK_TEXT == "chunk_text"

    def test_uri_is_primary_key(self):
        schema = files_schema()
        uri_field = schema.field(FileCol.URI)
        assert not uri_field.nullable


# ---------------------------------------------------------------------------
# Files table (L0 + L1)
# ---------------------------------------------------------------------------


class TestUpsertFiles:
    def test_upsert_converts_to_absolute_uri(self, db: MmDatabase):
        table = _scanner_table(["hello.py"])
        db.upsert_files(table, ROOT)

        f = db.get_file("/test/data/hello.py")
        assert f is not None
        assert f[FileCol.URI] == "/test/data/hello.py"

    def test_upsert_returns_row_count(self, db: MmDatabase):
        table = _scanner_table(["a.py", "b.py", "c.py"])
        n = db.upsert_files(table, ROOT)
        assert n == 3

    def test_l1_columns_are_null_after_l0(self, db: MmDatabase):
        table = _scanner_table(["doc.txt"])
        db.upsert_files(table, ROOT)

        f = db.get_file("/test/data/doc.txt")
        assert f[FileCol.CONTENT_HASH] is None
        assert f[FileCol.TEXT_PREVIEW] is None
        assert f[FileCol.L1_INDEXED_AT] is None

    def test_upsert_preserves_l1_on_rescan(self, db: MmDatabase):
        table = _scanner_table(["doc.txt"])
        db.upsert_files(table, ROOT)

        # Fill L1
        db.update_l1(
            "/test/data/doc.txt",
            {
                FileCol.CONTENT_HASH: "abc123",
                FileCol.LINE_COUNT: 42,
            },
        )

        # Re-upsert L0 — L1 should survive
        db.upsert_files(table, ROOT)

        f = db.get_file("/test/data/doc.txt")
        assert f[FileCol.CONTENT_HASH] == "abc123"
        assert f[FileCol.LINE_COUNT] == 42

    def test_get_file_returns_none_for_missing(self, db: MmDatabase):
        assert db.get_file("/nonexistent") is None

    def test_get_files_with_filter(self, db: MmDatabase):
        table = _scanner_table(["a.py", "b.png", "c.py"], kinds=["code", "image", "code"])
        db.upsert_files(table, ROOT)

        result = db.get_files(where="kind = 'code'")
        assert result.num_rows == 2

        result = db.get_files(where="kind = 'image'")
        assert result.num_rows == 1


class TestUpdateL1:
    def test_update_sets_l1_fields(self, db: MmDatabase):
        db.upsert_files(_scanner_table(["img.png"], kinds=["image"]), ROOT)
        db.update_l1(
            "/test/data/img.png",
            {
                FileCol.CONTENT_HASH: "hash_xyz",
                FileCol.PHASH: "00ff00ff",
                FileCol.DIMENSIONS: "800x600",
            },
        )

        f = db.get_file("/test/data/img.png")
        assert f[FileCol.CONTENT_HASH] == "hash_xyz"
        assert f[FileCol.PHASH] == "00ff00ff"
        assert f[FileCol.DIMENSIONS] == "800x600"
        assert f[FileCol.L1_INDEXED_AT] is not None

    def test_update_l1_noop_for_missing_file(self, db: MmDatabase):
        # Should not raise
        db.update_l1("/nonexistent", {FileCol.CONTENT_HASH: "abc"})


# ---------------------------------------------------------------------------
# Staleness detection
# ---------------------------------------------------------------------------


class TestStaleness:
    def test_new_file_is_stale(self, db: MmDatabase):
        assert db.is_stale("/test/data/new.txt", 1712000000000000, 100)

    def test_same_mtime_and_size_is_not_stale(self, db: MmDatabase):
        db.upsert_files(_scanner_table(["a.txt"]), ROOT)
        assert not db.is_stale("/test/data/a.txt", 1712000000000000, 100)

    def test_changed_mtime_is_stale(self, db: MmDatabase):
        db.upsert_files(_scanner_table(["a.txt"]), ROOT)
        assert db.is_stale("/test/data/a.txt", 9999999999999999, 100)

    def test_changed_size_is_stale(self, db: MmDatabase):
        db.upsert_files(_scanner_table(["a.txt"]), ROOT)
        assert db.is_stale("/test/data/a.txt", 1712000000000000, 999)


# ---------------------------------------------------------------------------
# L1 cache
# ---------------------------------------------------------------------------


class TestL1Cache:
    def test_get_l1_miss(self, db: MmDatabase):
        assert db.get_l1("nonexistent_hash") is None

    def test_put_and_get_l1(self, db: MmDatabase):
        db.upsert_files(_scanner_table(["doc.txt"]), ROOT)
        db.put_l1("/test/data/doc.txt", "hash_abc", "extracted text content")

        result = db.get_l1("hash_abc")
        assert result == "extracted text content"


# ---------------------------------------------------------------------------
# L2 results
# ---------------------------------------------------------------------------


class TestL2Results:
    def test_put_and_get_l2(self, db: MmDatabase):
        db.upsert_files(_scanner_table(["img.png"], kinds=["image"]), ROOT)
        db.put_l2("/test/data/img.png", "hash1", "default", "qwen", "A cat on a mat.")

        result = db.get_l2("hash1", "default", "qwen")
        assert result == "A cat on a mat."

    def test_l2_miss_wrong_profile(self, db: MmDatabase):
        db.upsert_files(_scanner_table(["img.png"], kinds=["image"]), ROOT)
        db.put_l2("/test/data/img.png", "hash1", "default", "qwen", "A cat.")

        assert db.get_l2("hash1", "other_profile", "qwen") is None

    def test_l2_miss_wrong_model(self, db: MmDatabase):
        db.upsert_files(_scanner_table(["img.png"], kinds=["image"]), ROOT)
        db.put_l2("/test/data/img.png", "hash1", "default", "qwen", "A cat.")

        assert db.get_l2("hash1", "default", "gpt-4") is None

    def test_l2_returns_full_content(self, db: MmDatabase):
        db.upsert_files(_scanner_table(["doc.txt"]), ROOT)
        long_content = "x" * 2000
        db.put_l2("/test/data/doc.txt", "hash1", "default", "qwen", long_content)

        # dbm cache returns full content; lancedb stores truncated summary
        result = db.get_l2("hash1", "default", "qwen")
        assert len(result) == 2000

    def test_l2_with_mode_and_detail(self, db: MmDatabase):
        db.upsert_files(_scanner_table(["img.png"], kinds=["image"]), ROOT)
        db.put_l2("/test/data/img.png", "h1", "default", "qwen", "fast result", mode="fast")
        db.put_l2("/test/data/img.png", "h1", "default", "qwen", "detailed", detail=True)

        assert db.get_l2("h1", "default", "qwen", mode="fast") == "fast result"
        assert db.get_l2("h1", "default", "qwen", detail=True) == "detailed"
        assert db.get_l2("h1", "default", "qwen", mode="accurate") is None


# ---------------------------------------------------------------------------
# Chunks
# ---------------------------------------------------------------------------


class TestChunks:
    def test_put_and_get_full_content(self, db: MmDatabase):
        db.upsert_files(_scanner_table(["doc.txt"]), ROOT)
        content = "Hello world. " * 200  # ~2600 chars → 3 chunks
        db.put_l2("/test/data/doc.txt", "hash1", "default", "qwen", content)

        full = db.get_full_content("/test/data/doc.txt", "hash1", "default", "qwen")
        assert full == content

    def test_get_full_content_miss(self, db: MmDatabase):
        assert db.get_full_content("/nonexistent", "hash1", "default", "qwen") is None

    def test_short_content_is_single_chunk(self, db: MmDatabase):
        db.upsert_files(_scanner_table(["a.txt"]), ROOT)
        db.put_l2("/test/data/a.txt", "h1", "default", "qwen", "short")

        full = db.get_full_content("/test/data/a.txt", "h1", "default", "qwen")
        assert full == "short"


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


class TestEmbeddings:
    def test_upsert_and_search(self, db: MmDatabase):
        db.upsert_files(_scanner_table(["doc.txt"]), ROOT)
        content = "Machine learning is great. " * 50
        db.put_l2("/test/data/doc.txt", "h1", "default", "qwen", content)

        # Embed with fake 4-dim vectors
        vectors = [[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]]
        db.upsert_embeddings("/test/data/doc.txt", "h1", "default", "qwen", "embed-v1", vectors)

        results = db.search_similar([0.1, 0.2, 0.3, 0.4], limit=2)
        assert results.num_rows > 0
        assert "chunk_text" in results.column_names

    def test_content_preserved_after_embedding(self, db: MmDatabase):
        db.upsert_files(_scanner_table(["doc.txt"]), ROOT)
        content = "Test content for embedding. " * 50
        db.put_l2("/test/data/doc.txt", "h1", "default", "qwen", content)

        db.upsert_embeddings(
            "/test/data/doc.txt",
            "h1",
            "default",
            "qwen",
            "embed-v1",
            [[1.0, 2.0], [3.0, 4.0]],
        )

        full = db.get_full_content("/test/data/doc.txt", "h1", "default", "qwen")
        assert full == content

    def test_search_returns_empty_without_embeddings(self, db: MmDatabase):
        results = db.search_similar([0.1, 0.2])
        assert results.num_rows == 0


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------


class TestSQL:
    def test_sql_group_by(self, db: MmDatabase):
        table = _scanner_table(["a.py", "b.png", "c.py"], kinds=["code", "image", "code"])
        db.upsert_files(table, ROOT)

        result = db.sql("SELECT kind, COUNT(*) as n FROM files GROUP BY kind ORDER BY n DESC")
        rows = result.to_pydict()
        assert rows["kind"][0] == "code"
        assert rows["n"][0] == 2

    def test_sql_where(self, db: MmDatabase):
        table = _scanner_table(["a.py", "b.png"], kinds=["code", "image"])
        db.upsert_files(table, ROOT)

        result = db.sql("SELECT uri FROM files WHERE kind = 'image'")
        assert result.num_rows == 1

    def test_sql_on_l2_table(self, db: MmDatabase):
        db.upsert_files(_scanner_table(["a.txt"]), ROOT)
        db.put_l2("/test/data/a.txt", "h1", "default", "qwen", "hello")

        result = db.sql("SELECT COUNT(*) as n FROM l2_results", table_name="l2_results")
        assert result.to_pydict()["n"][0] == 1
