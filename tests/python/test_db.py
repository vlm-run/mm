"""Tests for mm.store — MmDatabase, schema, and end-to-end operations."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pytest
from mm.store import MmDatabase
from mm.store.schema import (
    ChunkCol,
    FileCol,
    L2Col,
)
from mm.store.util import get_l2_id

from .test_utils import ROOT, ensure_l0, ensure_l1, get_hash, scanner_table

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path: Path) -> MmDatabase:
    """Create an isolated MmDatabase in a temp directory."""
    return MmDatabase(db_path=tmp_path / "test.db")


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestSchema:
    def test_column_enums_are_strings(self):
        assert FileCol.URI == "uri"
        assert L2Col.SUMMARY == "summary"
        assert ChunkCol.CHUNK_TEXT == "chunk_text"


# ---------------------------------------------------------------------------
# Files table (L0 + L1)
# ---------------------------------------------------------------------------


class TestUpsertFiles:
    def test_upsert_converts_to_absolute_uri(self, db: MmDatabase):
        uri = "/test/data/hello.py"
        ensure_l0(db, [uri])
        f = db.get_file(uri)
        assert f is not None
        assert f[FileCol.URI] == uri

    def test_upsert_column_mapping(self, db: MmDatabase):
        """Verify every column maps correctly through to_pydict bulk conversion."""
        table = pa.table(
            {
                "path": ["img.png", "doc.pdf"],
                "name": ["img.png", "doc.pdf"],
                "stem": ["img", "doc"],
                "ext": [".png", ".pdf"],
                "size": pa.array([1234, 5678], type=pa.uint64()),
                "modified": pa.array([1700000000000000, 1700000001000000], type=pa.timestamp("us")),
                "created": pa.array([1600000000000000, 1600000001000000], type=pa.timestamp("us")),
                "mime": ["image/png", "application/pdf"],
                "kind": ["image", "document"],
                "is_binary": [True, False],
                "depth": pa.array([0, 1], type=pa.uint16()),
                "parent": ["", "subdir"],
                "width": pa.array([800, None], type=pa.uint32()),
                "height": pa.array([600, None], type=pa.uint32()),
                "phash": pa.array([0x00FF00FF00FF00FF, None], type=pa.uint64()),
            }
        )
        db.upsert_files(table, ROOT)

        f1 = db.get_file("/test/data/img.png")
        assert f1["name"] == "img.png"
        assert f1["stem"] == "img"
        assert f1["ext"] == ".png"
        assert f1["size"] == 1234
        assert f1["modified"] == 1700000000000000
        assert f1["created"] == 1600000000000000
        assert f1["mime"] == "image/png"
        assert f1["kind"] == "image"
        assert f1["is_binary"] == 1
        assert f1["depth"] == 0
        assert f1["parent"] == str(ROOT)
        assert f1["width"] == 800
        assert f1["height"] == 600
        assert f1["phash"] == "00ff00ff00ff00ff"

        f2 = db.get_file("/test/data/doc.pdf")
        assert f2["kind"] == "document"
        assert f2["is_binary"] == 0
        assert f2["depth"] == 1
        assert f2["parent"] == f"{ROOT}/subdir"
        assert f2["modified"] == 1700000001000000
        assert f2["width"] is None
        assert f2["height"] is None
        assert f2["phash"] is None

    def test_upsert_returns_row_count(self, db: MmDatabase):
        count = ensure_l0(db, ["a.py", "b.py", "c.py"])
        assert count == 3

    def test_l1_columns_are_null_after_l0(self, db: MmDatabase):
        ensure_l0(db, ["doc.txt"])

        f = db.get_file("/test/data/doc.txt")
        assert f[FileCol.CONTENT_HASH] is None
        assert f[FileCol.TEXT_PREVIEW] is None
        assert f[FileCol.L1_INDEXED_AT] is None

    def test_upsert_preserves_l1_on_rescan(self, db: MmDatabase):
        ensure_l0(db, ["doc.txt"])
        # Fill L1
        db.update_l1(
            "/test/data/doc.txt",
            {
                FileCol.CONTENT_HASH: "abc123",
                FileCol.LINE_COUNT: 42,
            },
        )

        # Re-upsert L0 — L1 should survive
        table = scanner_table(["doc.txt"])
        db.upsert_files(table, ROOT)

        f = db.get_file("/test/data/doc.txt")
        assert f[FileCol.CONTENT_HASH] == "abc123"
        assert f[FileCol.LINE_COUNT] == 42

    def test_get_file_returns_none_for_missing(self, db: MmDatabase):
        assert db.get_file("/nonexistent") is None

    def test_get_files_with_filter(self, db: MmDatabase):
        ensure_l0(db, ["a.py", "b.png", "c.py"], kinds=["code", "image", "code"])

        result = db.get_files(where="kind = 'code'")
        assert len(result) == 2

        result = db.get_files(where="kind = 'image'")
        assert len(result) == 1


class TestUpdateL1:
    def test_update_sets_l1_fields(self, db: MmDatabase):
        uri = "/test/data/img.png"
        ensure_l0(db, [uri], kinds=["image"])
        db.update_l1(
            uri,
            {
                FileCol.CONTENT_HASH: "hash_xyz",
                FileCol.PHASH: "00ff00ff",
                FileCol.DIMENSIONS: "800x600",
            },
        )

        f = db.get_file(uri)
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
        uri = "/test/data/a.txt"
        ensure_l0(db, [uri])
        assert not db.is_stale("/test/data/a.txt", 1712000000000000, 100)

    def test_changed_mtime_is_stale(self, db: MmDatabase):
        uri = "/test/data/a.txt"
        ensure_l0(db, [uri])
        assert db.is_stale("/test/data/a.txt", 9999999999999999, 100)

    def test_changed_size_is_stale(self, db: MmDatabase):
        uri = "/test/data/a.txt"
        ensure_l0(db, [uri])
        assert db.is_stale("/test/data/a.txt", 1712000000000000, 999)


# ---------------------------------------------------------------------------
# L1
# ---------------------------------------------------------------------------


class TestL1Cache:
    def test_get_l1_miss(self, db: MmDatabase):
        assert db.get_l1("nonexistent_hash") is None

    def test_put_and_get_l1(self, db: MmDatabase):
        ensure_l0(db, ["/test/data/doc.txt"])
        db.put_l1("/test/data/doc.txt", "hash_abc", "extracted text content")
        result = db.get_l1("hash_abc")
        assert result == "extracted text content"


# ---------------------------------------------------------------------------
# L2 results
# ---------------------------------------------------------------------------


class TestL2Results:
    def test_put_l2_throws_with_missing_l1(self, db: MmDatabase):
        uri = "/test/data/img.png"
        ensure_l0(db, [uri], kinds=["image"])
        with pytest.raises(RuntimeError, match="L1 content not found"):
            db.put_l2(uri, get_hash(uri), "default", "qwen", "A cat on a mat.")
            result = db.get_l2("hash1", "default", "qwen")
            assert result == "A cat on a mat."

    def test_put_and_get_l2(self, db: MmDatabase):
        uri = "/test/data/img.png"
        ensure_l1(db, uri, "L1 content x", l0_kinds=["image"])

        content_hash = get_hash(uri)
        l2_id = db.put_l2(uri, content_hash, "default", "qwen", "A cat on a mat.")
        result = db.get_l2(l2_id)

        assert result == "A cat on a mat."
        assert db.get_l1("hash1") == "L1 content x"

    def test_l2_miss_wrong_profile(self, db: MmDatabase):
        uri = "/test/data/img.png"
        ensure_l1(db, uri, l0_kinds=["image"])

        content_hash = get_hash(uri)
        l2_id = db.put_l2(uri, content_hash, "default", "qwen", "A cat.")
        incorrect_l2_id = get_l2_id(content_hash, "other_profile", "qwen", None, False)

        assert db.get_l2(l2_id) == "A cat."
        assert db.get_l2(incorrect_l2_id) is None

    def test_l2_miss_wrong_model(self, db: MmDatabase):
        uri = "/test/data/img.png"
        ensure_l1(db, uri, l0_kinds=["image"])

        content_hash = get_hash(uri)
        l2_id = db.put_l2(uri, content_hash, "default", "qwen", "A cat.")
        incorrect_l2_id = get_l2_id(content_hash, "default", "gpt-4", None, False)
        assert db.get_l2(l2_id) == "A cat."
        assert db.get_l2(incorrect_l2_id) is None

    def test_l2_returns_full_content(self, db: MmDatabase):
        uri = "/test/data/doc.txt"
        ensure_l1(db, uri)

        long_content = "x" * 2000
        content_hash = get_hash(uri)
        l2_id = db.put_l2(uri, content_hash, "default", "qwen", long_content)

        assert len(db.get_l2(l2_id)) == 2000

    def test_l2_with_mode_and_detail(self, db: MmDatabase):
        uri = "/test/data/img.png"
        ensure_l1(db, uri)

        content_hash = get_hash(uri)

        id_fast = get_l2_id(content_hash, "default", "qwen", "fast", False)
        _id_fast = db.put_l2(uri, content_hash, "default", "qwen", "fast result", mode="fast")
        assert _id_fast == id_fast
        assert db.get_l2(id_fast) == "fast result"

        id_detail = get_l2_id(content_hash, "default", "qwen", None, True)
        _id_detail = db.put_l2(uri, content_hash, "default", "qwen", "detailed", detail=True)
        assert _id_detail == id_detail
        assert db.get_l2(_id_detail) == "detailed"

        id_accurate = get_l2_id(content_hash, "default", "qwen", "accurate", False)
        assert db.get_l2(id_accurate) is None


# ---------------------------------------------------------------------------
# Eviction (--no-cache)
# ---------------------------------------------------------------------------


class TestEvictL2:
    def test_evict_removes_l2_and_chunks(self, db: MmDatabase):
        uri = "/test/data/img.png"
        ensure_l1(db, uri, l0_kinds=["image"])
        content_hash = get_hash(uri)

        l2_id = db.put_l2(uri, content_hash, "default", "qwen", "A cat on a mat.")
        assert db.get_l2(l2_id) is not None

        # Verify chunks exist
        chunks = db.get_chunks(l2_id)
        assert len(chunks) > 0

        evicted = db.evict_l2(l2_id)
        assert evicted == 1
        assert db.get_l2(l2_id) is None

        # Chunks should be cascade-deleted
        chunks_after = db.get_chunks(l2_id)
        assert len(chunks_after) == 0

    def test_evict_returns_zero_when_nothing_to_evict(self, db: MmDatabase):
        assert db.evict_l2("nonexistent_id") == 0

    def test_evict_only_matching_key(self, db: MmDatabase):
        """Evicting one (profile, model, mode) should not affect others."""
        uri = "/test/data/img.png"
        ensure_l1(db, uri, l0_kinds=["image"])
        content_hash = get_hash(uri)

        id_fast = db.put_l2(uri, content_hash, "default", "qwen", "fast result", mode="fast")
        id_accurate = db.put_l2(
            uri, content_hash, "default", "qwen", "accurate result", mode="accurate"
        )

        db.evict_l2(id_fast)
        assert db.get_l2(id_fast) is None
        assert db.get_l2(id_accurate) == "accurate result"

    def test_put_overwrites_no_duplicates(self, db: MmDatabase):
        """Repeated put_l2 with same key overwrites via deterministic PK — no duplicates."""
        uri = "/test/data/img.png"
        ensure_l1(db, uri, l0_kinds=["image"])
        content_hash = get_hash(uri)

        id_v1 = db.put_l2(uri, content_hash, "default", "qwen", "version 1")
        db.put_l2(uri, content_hash, "default", "qwen", "version 2")
        db.put_l2(uri, content_hash, "default", "qwen", "version 3")

        # Only the latest content should be retrievable
        assert db.get_l2(id_v1) == "version 3"

        # Exactly one l2_results row for this key
        row = db._connect.execute(
            "SELECT COUNT(*) FROM l2_results WHERE content_hash = ? AND profile = ? AND model = ?",
            (content_hash, "default", "qwen"),
        ).fetchone()
        assert row[0] == 1

    def test_deterministic_id(self, db: MmDatabase):
        """put_l2 returns a deterministic sha256-based ID for the same parameters."""
        uri = "/test/data/img.png"
        ensure_l1(db, uri, l0_kinds=["image"])
        content_hash = get_hash(uri)

        id1 = db.put_l2(uri, content_hash, "default", "qwen", "content A")
        # Overwrite with different content but same key
        id2 = db.put_l2(uri, content_hash, "default", "qwen", "content B")
        assert id1 == id2
        assert isinstance(id1, str)
        assert len(id1) == 24

        # Different mode → different ID
        id3 = db.put_l2(uri, content_hash, "default", "qwen", "fast", mode="fast")
        assert id3 != id1

    def test_files_cascade_deletes_l2(self, db: MmDatabase):
        """Deleting a files row should cascade-delete its l2_results and chunks."""
        uri = "/test/data/img.png"
        ensure_l1(db, uri, l0_kinds=["image"])
        content_hash = get_hash(uri)

        l2_id = db.put_l2(uri, content_hash, "default", "qwen", "A cat on a mat.")
        assert db.get_l2(l2_id) is not None

        # Delete the files row
        db._connect.execute("DELETE FROM files WHERE uri = ?", (uri,))
        db._connect.commit()

        # l2_results and chunks should be cascade-deleted
        assert db.get_l2(l2_id) is None
        chunks = db.get_chunks(l2_id)
        assert len(chunks) == 0

    def test_evict_then_reinsert(self, db: MmDatabase):
        """Simulates --no-cache: evict then put fresh result."""
        uri = "/test/data/img.png"
        ensure_l1(db, uri, l0_kinds=["image"])
        content_hash = get_hash(uri)

        l2_id = db.put_l2(uri, content_hash, "default", "qwen", "stale result")
        db.evict_l2(l2_id)
        db.put_l2(uri, content_hash, "default", "qwen", "fresh result")

        assert db.get_l2(l2_id) == "fresh result"

        # Exactly one l2_results row should exist
        row = db._connect.execute(
            "SELECT COUNT(*) FROM l2_results WHERE content_hash = ? AND profile = ? AND model = ?",
            (content_hash, "default", "qwen"),
        ).fetchone()
        assert row[0] == 1


# ---------------------------------------------------------------------------
# Chunks
# ---------------------------------------------------------------------------


class TestChunks:
    def test_put_and_get_full_content(self, db: MmDatabase):
        uri = "/test/data/doc.txt"
        ensure_l1(db, uri)

        content_hash = get_hash(uri)
        content = "Hello world. " * 200  # ~2600 chars → 3 chunks
        db.put_l2(uri, content_hash, "default", "qwen", content)

        full = db.get_full_content(uri, content_hash, "default", "qwen")
        assert full == content

    def test_get_full_content_miss(self, db: MmDatabase):
        assert db.get_full_content("/nonexistent", "hash1", "default", "qwen") is None

    def test_short_content_is_single_chunk(self, db: MmDatabase):
        uri = "/test/data/a.txt"
        ensure_l1(db, uri)

        content_hash = get_hash(uri)
        db.put_l2(uri, content_hash, "default", "qwen", "short")
        full = db.get_full_content(uri, content_hash, "default", "qwen")
        assert full == "short"


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


class TestEmbeddings:
    def test_upsert_and_search(self, db: MmDatabase):
        uri = "/test/data/doc.txt"
        ensure_l1(db, uri)

        content_hash = get_hash(uri)
        content = "Machine learning is great. " * 50
        l2_id = db.put_l2(uri, content_hash, "default", "qwen", content)

        # Embed with fake 4-dim vectors
        vectors = [[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]]
        db.upsert_embeddings(l2_id=l2_id, vectors=vectors)

        results = db.search_similar([0.1, 0.2, 0.3, 0.4], limit=2)
        assert len(results) > 0
        assert "chunk_text" in results[0]

    def test_content_preserved_after_embedding(self, db: MmDatabase):
        uri = "/test/data/doc.txt"
        ensure_l1(db, uri)

        content_hash = get_hash(uri)
        content = "Test content for embedding. " * 50
        l2_id = db.put_l2(uri, content_hash, "default", "qwen", content)

        db.upsert_embeddings(l2_id=l2_id, vectors=[[1.0, 2.0], [3.0, 4.0]])

        full = db.get_full_content(uri, content_hash, "default", "qwen")
        assert full == content

    def test_search_returns_empty_without_embeddings(self, db: MmDatabase):
        results = db.search_similar([0.1, 0.2])
        assert len(results) == 0


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------


class TestSQL:
    def test_sql_group_by(self, db: MmDatabase):
        ensure_l0(db, ["a.py", "b.png", "c.py"], kinds=["code", "image", "code"])
        columns, rows = db.sql(
            "SELECT kind, COUNT(*) as n FROM files GROUP BY kind ORDER BY n DESC"
        )
        assert columns == ["kind", "n"]
        assert rows[0][0] == "code"
        assert rows[0][1] == 2

    def test_sql_where(self, db: MmDatabase):
        ensure_l0(db, ["a.py", "b.png"], kinds=["code", "image"])
        _, rows = db.sql("SELECT uri FROM files WHERE kind = 'image'")
        assert len(rows) == 1

    def test_sql_on_l2_table(self, db: MmDatabase):
        uri = f"{ROOT}/a.txt"
        ensure_l1(db, uri)
        db.put_l2(uri, get_hash(uri), "default", "qwen", "hello")
        _, rows = db.sql("SELECT COUNT(*) as n FROM l2_results", table_name="l2_results")
        assert rows[0][0] == 1
