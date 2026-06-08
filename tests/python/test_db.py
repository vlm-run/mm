"""Tests for mm.store — MmDatabase, schema, and end-to-end operations."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pytest
from mm.store import MmDatabase
from mm.store.schema import (
    ChunkCol,
    ExtractionCol,
    FileCol,
)
from mm.store.utils import get_extraction_id

from .conftest import requires_sqlite_vec
from .test_utils import ROOT, ensure_fast, ensure_metadata, get_hash, scanner_table

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
        assert ExtractionCol.SUMMARY == "summary"
        assert ChunkCol.CHUNK_TEXT == "chunk_text"


# ---------------------------------------------------------------------------
# Files table (metadata + fast)
# ---------------------------------------------------------------------------


class TestUpsertFiles:
    def test_upsert_converts_to_absolute_uri(self, db: MmDatabase):
        uri = "/test/data/hello.py"
        ensure_metadata(db, [uri])
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
        count = ensure_metadata(db, ["a.py", "b.py", "c.py"])
        assert count == 3

    def test_fast_columns_are_null_after_metadata(self, db: MmDatabase):
        ensure_metadata(db, ["doc.txt"])

        f = db.get_file("/test/data/doc.txt")
        assert f[FileCol.CONTENT_HASH] is None
        assert f[FileCol.TEXT_PREVIEW] is None
        assert f[FileCol.CONTENT_INDEXED_AT] is None

    def test_upsert_preserves_fast_on_rescan(self, db: MmDatabase):
        ensure_metadata(db, ["doc.txt"])
        # Fill fast columns
        db.put_file_content(
            "/test/data/doc.txt",
            {
                FileCol.CONTENT_HASH: "abc123",
                FileCol.LINE_COUNT: 42,
            },
        )

        # Re-upsert metadata — fast columns should survive
        table = scanner_table(["doc.txt"])
        db.upsert_files(table, ROOT)

        f = db.get_file("/test/data/doc.txt")
        assert f[FileCol.CONTENT_HASH] == "abc123"
        assert f[FileCol.LINE_COUNT] == 42

    def test_get_file_returns_none_for_missing(self, db: MmDatabase):
        assert db.get_file("/nonexistent") is None

    def test_get_files_with_filter(self, db: MmDatabase):
        ensure_metadata(db, ["a.py", "b.png", "c.py"], kinds=["code", "image", "code"])

        result = db.get_files(where="kind = 'code'")
        assert len(result) == 2

        result = db.get_files(where="kind = 'image'")
        assert len(result) == 1


class TestUpdateFast:
    def test_update_sets_fast_fields(self, db: MmDatabase):
        uri = "/test/data/img.png"
        ensure_metadata(db, [uri], kinds=["image"])
        db.put_file_content(
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
        assert f[FileCol.CONTENT_INDEXED_AT] is None

    def test_update_fast_noop_for_missing_file(self, db: MmDatabase):
        # Should not raise
        db.put_file_content("/nonexistent", {FileCol.CONTENT_HASH: "abc"})


# ---------------------------------------------------------------------------
# Staleness detection
# ---------------------------------------------------------------------------


class TestStaleness:
    def test_new_file_is_stale(self, db: MmDatabase):
        assert db.is_stale("/test/data/new.txt", 1712000000000000, 100)

    def test_same_mtime_and_size_is_not_stale(self, db: MmDatabase):
        uri = "/test/data/a.txt"
        ensure_metadata(db, [uri])
        assert not db.is_stale("/test/data/a.txt", 1712000000000000, 100)

    def test_changed_mtime_is_stale(self, db: MmDatabase):
        uri = "/test/data/a.txt"
        ensure_metadata(db, [uri])
        assert db.is_stale("/test/data/a.txt", 9999999999999999, 100)

    def test_changed_size_is_stale(self, db: MmDatabase):
        uri = "/test/data/a.txt"
        ensure_metadata(db, [uri])
        assert db.is_stale("/test/data/a.txt", 1712000000000000, 999)


# ---------------------------------------------------------------------------
# Fast (local extraction cache)
# ---------------------------------------------------------------------------


class TestFileContentCache:
    def test_get_file_content_miss(self, db: MmDatabase):
        assert db.get_file_content("nonexistent_hash") is None

    def test_put_and_get_file_content(self, db: MmDatabase):
        ensure_metadata(db, ["/test/data/doc.txt"])
        db.put_file_content(
            "/test/data/doc.txt",
            {
                FileCol.CONTENT_HASH: "hash_abc",
                FileCol.TEXT_PREVIEW: "extracted text content",
            },
        )
        result = db.get_file_content("hash_abc")
        assert result == "extracted text content"


# ---------------------------------------------------------------------------
# Accurate results
# ---------------------------------------------------------------------------


class TestAccurateResults:
    def test_put_accurate_throws_with_missing_fast(self, db: MmDatabase):
        uri = "/test/data/img.png"
        ensure_metadata(db, [uri], kinds=["image"])
        with pytest.raises(RuntimeError, match="File content not found"):
            db.put_extraction(uri, get_hash(uri), "default", "qwen", "A cat on a mat.")
            result = db.get_extraction("hash1", "default", "qwen")
            assert result == "A cat on a mat."

    def test_put_and_get_accurate(self, db: MmDatabase):
        uri = "/test/data/img.png"
        ensure_fast(db, uri, "fast content x", metadata_kinds=["image"])

        content_hash = get_hash(uri)
        extraction_id = db.put_extraction(uri, content_hash, "default", "qwen", "A cat on a mat.")
        result = db.get_extraction(extraction_id)

        assert result == "A cat on a mat."
        assert db.get_file_content("hash1") == "fast content x"

    def test_accurate_miss_wrong_profile(self, db: MmDatabase):
        uri = "/test/data/img.png"
        ensure_fast(db, uri, metadata_kinds=["image"])

        content_hash = get_hash(uri)
        extraction_id = db.put_extraction(uri, content_hash, "default", "qwen", "A cat.")
        incorrect_extraction_id = get_extraction_id(
            content_hash, "other_profile", "qwen", None, False
        )

        assert db.get_extraction(extraction_id) == "A cat."
        assert db.get_extraction(incorrect_extraction_id) is None

    def test_accurate_miss_wrong_model(self, db: MmDatabase):
        uri = "/test/data/img.png"
        ensure_fast(db, uri, metadata_kinds=["image"])

        content_hash = get_hash(uri)
        extraction_id = db.put_extraction(uri, content_hash, "default", "qwen", "A cat.")
        incorrect_extraction_id = get_extraction_id(content_hash, "default", "gpt-4", None, False)
        assert db.get_extraction(extraction_id) == "A cat."
        assert db.get_extraction(incorrect_extraction_id) is None

    def test_accurate_returns_full_content(self, db: MmDatabase):
        uri = "/test/data/doc.txt"
        ensure_fast(db, uri)

        long_content = "x" * 2000
        content_hash = get_hash(uri)
        extraction_id = db.put_extraction(uri, content_hash, "default", "qwen", long_content)

        assert len(db.get_extraction(extraction_id)) == 2000

    def test_accurate_with_mode_and_detail(self, db: MmDatabase):
        uri = "/test/data/img.png"
        ensure_fast(db, uri)

        content_hash = get_hash(uri)

        id_fast = get_extraction_id(content_hash, "default", "qwen", "fast", False)
        _id_fast = db.put_extraction(
            uri, content_hash, "default", "qwen", "fast result", mode="fast"
        )
        assert _id_fast == id_fast
        assert db.get_extraction(id_fast) == "fast result"

        id_detail = get_extraction_id(content_hash, "default", "qwen", "accurate", True)
        _id_detail = db.put_extraction(
            uri, content_hash, "default", "qwen", "detailed", detail=True
        )
        assert _id_detail == id_detail
        assert db.get_extraction(_id_detail) == "detailed"

        id_accurate = get_extraction_id(content_hash, "default", "qwen", "accurate", False)
        assert db.get_extraction(id_accurate) is None


class TestExtractionMetadata:
    """``put_extraction(metadata=...)`` round-trips through ``get_extraction_metadata``.

    The verbose-cache fix in ``cat`` relies on this round-trip to replay the
    rendered verbose suffix on a cached + verbose run without re-invoking the LLM.
    """

    def test_round_trip(self, db: MmDatabase):
        uri = "/test/data/img.png"
        ensure_fast(db, uri, metadata_kinds=["image"])
        meta = {"verbose_suffix": "[dim]generate: ollama • 1.2s • 100→50 tokens[/dim]"}

        eid = db.put_extraction(uri, get_hash(uri), "default", "qwen", "summary", metadata=meta)
        assert db.get_extraction_metadata(eid) == meta

    def test_returns_none_when_metadata_omitted(self, db: MmDatabase):
        uri = "/test/data/img.png"
        ensure_fast(db, uri, metadata_kinds=["image"])

        eid = db.put_extraction(uri, get_hash(uri), "default", "qwen", "summary")
        assert db.get_extraction_metadata(eid) is None

    def test_returns_none_for_unknown_id(self, db: MmDatabase):
        assert db.get_extraction_metadata("does-not-exist") is None

    def test_returns_none_when_json_malformed(self, db: MmDatabase):
        """Defensively handle hand-edited or corrupt metadata."""
        uri = "/test/data/img.png"
        ensure_fast(db, uri, metadata_kinds=["image"])
        eid = db.put_extraction(
            uri, get_hash(uri), "default", "qwen", "summary", metadata={"k": "v"}
        )
        # Stomp the metadata column with non-JSON text.
        db._connect.execute("UPDATE extractions SET metadata = ? WHERE id = ?", ("{not json", eid))
        db._connect.commit()
        assert db.get_extraction_metadata(eid) is None


# ---------------------------------------------------------------------------
# Eviction (--no-cache)
# ---------------------------------------------------------------------------


class TestEvictAccurate:
    def test_evict_removes_accurate_and_chunks(self, db: MmDatabase):
        uri = "/test/data/img.png"
        ensure_fast(db, uri, metadata_kinds=["image"])
        content_hash = get_hash(uri)

        extraction_id = db.put_extraction(uri, content_hash, "default", "qwen", "A cat on a mat.")
        assert db.get_extraction(extraction_id) is not None

        # Verify chunks exist
        chunks = db.get_chunks(extraction_id)
        assert len(chunks) > 0

        evicted = db.evict_extraction(extraction_id)
        assert evicted == 1
        assert db.get_extraction(extraction_id) is None

        # Chunks should be cascade-deleted
        chunks_after = db.get_chunks(extraction_id)
        assert len(chunks_after) == 0

    def test_evict_returns_zero_when_nothing_to_evict(self, db: MmDatabase):
        assert db.evict_extraction("nonexistent_id") == 0

    def test_evict_only_matching_key(self, db: MmDatabase):
        """Evicting one (profile, model, mode) should not affect others."""
        uri = "/test/data/img.png"
        ensure_fast(db, uri, metadata_kinds=["image"])
        content_hash = get_hash(uri)

        id_fast = db.put_extraction(
            uri, content_hash, "default", "qwen", "fast result", mode="fast"
        )
        id_accurate = db.put_extraction(
            uri, content_hash, "default", "qwen", "accurate result", mode="accurate"
        )

        db.evict_extraction(id_fast)
        assert db.get_extraction(id_fast) is None
        assert db.get_extraction(id_accurate) == "accurate result"

    def test_put_overwrites_no_duplicates(self, db: MmDatabase):
        """Repeated put_accurate with same key overwrites via deterministic PK — no duplicates."""
        uri = "/test/data/img.png"
        ensure_fast(db, uri, metadata_kinds=["image"])
        content_hash = get_hash(uri)

        id_v1 = db.put_extraction(uri, content_hash, "default", "qwen", "version 1")
        db.put_extraction(uri, content_hash, "default", "qwen", "version 2")
        db.put_extraction(uri, content_hash, "default", "qwen", "version 3")

        # Only the latest content should be retrievable
        assert db.get_extraction(id_v1) == "version 3"

        # Exactly one extractions row for this key
        row = db._connect.execute(
            "SELECT COUNT(*) FROM extractions WHERE content_hash = ? AND profile = ? AND model = ?",
            (content_hash, "default", "qwen"),
        ).fetchone()
        assert row[0] == 1

    def test_deterministic_id(self, db: MmDatabase):
        """put_accurate returns a deterministic sha256-based ID for the same parameters."""
        uri = "/test/data/img.png"
        ensure_fast(db, uri, metadata_kinds=["image"])
        content_hash = get_hash(uri)

        id1 = db.put_extraction(uri, content_hash, "default", "qwen", "content A")
        # Overwrite with different content but same key
        id2 = db.put_extraction(uri, content_hash, "default", "qwen", "content B")
        assert id1 == id2
        assert isinstance(id1, str)
        assert len(id1) == 24

        # Different mode → different ID
        id3 = db.put_extraction(uri, content_hash, "default", "qwen", "fast", mode="fast")
        assert id3 != id1

    def test_files_cascade_deletes_accurate(self, db: MmDatabase):
        """Deleting a files row should cascade-delete its extractions and chunks."""
        uri = "/test/data/img.png"
        ensure_fast(db, uri, metadata_kinds=["image"])
        content_hash = get_hash(uri)

        extraction_id = db.put_extraction(uri, content_hash, "default", "qwen", "A cat on a mat.")
        assert db.get_extraction(extraction_id) is not None

        # Delete the files row
        db._connect.execute("DELETE FROM files WHERE uri = ?", (uri,))
        db._connect.commit()

        # extractions and chunks should be cascade-deleted
        assert db.get_extraction(extraction_id) is None
        chunks = db.get_chunks(extraction_id)
        assert len(chunks) == 0

    def test_evict_then_reinsert(self, db: MmDatabase):
        """Simulates --no-cache: evict then put fresh result."""
        uri = "/test/data/img.png"
        ensure_fast(db, uri, metadata_kinds=["image"])
        content_hash = get_hash(uri)

        extraction_id = db.put_extraction(uri, content_hash, "default", "qwen", "stale result")
        db.evict_extraction(extraction_id)
        db.put_extraction(uri, content_hash, "default", "qwen", "fresh result")

        assert db.get_extraction(extraction_id) == "fresh result"

        # Exactly one extractions row should exist
        row = db._connect.execute(
            "SELECT COUNT(*) FROM extractions WHERE content_hash = ? AND profile = ? AND model = ?",
            (content_hash, "default", "qwen"),
        ).fetchone()
        assert row[0] == 1


# ---------------------------------------------------------------------------
# Chunks
# ---------------------------------------------------------------------------


class TestChunks:
    def test_put_and_get_full_content(self, db: MmDatabase):
        uri = "/test/data/doc.txt"
        ensure_fast(db, uri)

        content_hash = get_hash(uri)
        content = "Hello world. " * 200  # ~2600 chars → 3 chunks
        db.put_extraction(uri, content_hash, "default", "qwen", content)

        full = db.get_full_content(uri, content_hash, "default", "qwen")
        assert full == content

    def test_get_full_content_miss(self, db: MmDatabase):
        assert db.get_full_content("/nonexistent", "hash1", "default", "qwen") is None

    def test_short_content_is_single_chunk(self, db: MmDatabase):
        uri = "/test/data/a.txt"
        ensure_fast(db, uri)

        content_hash = get_hash(uri)
        db.put_extraction(uri, content_hash, "default", "qwen", "short")
        full = db.get_full_content(uri, content_hash, "default", "qwen")
        assert full == "short"


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


class TestEmbeddings:
    @requires_sqlite_vec
    def test_upsert_and_search(self, db: MmDatabase):
        uri = "/test/data/doc.txt"
        ensure_fast(db, uri)

        content_hash = get_hash(uri)
        content = "Machine learning is great. " * 50
        extraction_id = db.put_extraction(uri, content_hash, "default", "qwen", content)

        # Embed with fake 4-dim vectors
        vectors = [[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]]
        db.upsert_embeddings(extraction_id=extraction_id, vectors=vectors)

        results = db.search_similar([0.1, 0.2, 0.3, 0.4], limit=2)
        assert len(results) > 0
        assert "chunk_text" in results[0]

    @requires_sqlite_vec
    def test_content_preserved_after_embedding(self, db: MmDatabase):
        uri = "/test/data/doc.txt"
        ensure_fast(db, uri)

        content_hash = get_hash(uri)
        content = "Test content for embedding. " * 50
        extraction_id = db.put_extraction(uri, content_hash, "default", "qwen", content)

        db.upsert_embeddings(extraction_id=extraction_id, vectors=[[1.0, 2.0], [3.0, 4.0]])

        full = db.get_full_content(uri, content_hash, "default", "qwen")
        assert full == content

    @requires_sqlite_vec
    def test_search_returns_empty_without_embeddings(self, db: MmDatabase):
        results = db.search_similar([0.1, 0.2])
        assert len(results) == 0


# ---------------------------------------------------------------------------
# sqlite-vec extension auto-loading (centralized in _VecConnection / _load_vec)
# ---------------------------------------------------------------------------


def _seed_embeddings(path: Path) -> None:
    seed = MmDatabase(db_path=path)
    uri = "/test/data/doc.txt"
    ensure_fast(seed, uri)
    extraction_id = seed.put_extraction(uri, get_hash(uri), "default", "qwen", "content " * 50)
    seed.upsert_embeddings(extraction_id=extraction_id, vectors=[[0.1, 0.2], [0.3, 0.4]])


class TestVecAutoLoad:
    @requires_sqlite_vec
    def test_raw_chunks_vec_query_autoloads_on_fresh_connection(self, tmp_path: Path):
        path = tmp_path / "test.db"
        _seed_embeddings(path)

        conn = MmDatabase(db_path=path)._connect
        assert getattr(conn, "_vec_loaded", None) is None

        count = conn.execute("SELECT COUNT(*) FROM chunks_vec").fetchone()[0]
        assert count >= 1
        assert getattr(conn, "_vec_loaded", None) is True

    @requires_sqlite_vec
    def test_sql_method_on_chunks_vec_autoloads(self, tmp_path: Path):
        path = tmp_path / "test.db"
        _seed_embeddings(path)

        _, rows = MmDatabase(db_path=path).sql("SELECT COUNT(*) AS n FROM chunks_vec")
        assert rows[0][0] >= 1

    def test_vector_free_query_never_loads_extension(self, db: MmDatabase):
        ensure_metadata(db, ["a.py"])
        db.sql("SELECT COUNT(*) FROM chunks")
        assert getattr(db._connect, "_vec_loaded", None) is None


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------


class TestSQL:
    def test_sql_group_by(self, db: MmDatabase):
        ensure_metadata(db, ["a.py", "b.png", "c.py"], kinds=["code", "image", "code"])
        columns, rows = db.sql(
            "SELECT kind, COUNT(*) as n FROM files GROUP BY kind ORDER BY n DESC"
        )
        assert columns == ["kind", "n"]
        assert rows[0][0] == "code"
        assert rows[0][1] == 2

    def test_sql_where(self, db: MmDatabase):
        ensure_metadata(db, ["a.py", "b.png"], kinds=["code", "image"])
        _, rows = db.sql("SELECT uri FROM files WHERE kind = 'image'")
        assert len(rows) == 1

    def test_sql_on_accurate_table(self, db: MmDatabase):
        uri = f"{ROOT}/a.txt"
        ensure_fast(db, uri)
        db.put_extraction(uri, get_hash(uri), "default", "qwen", "hello")
        _, rows = db.sql("SELECT COUNT(*) as n FROM extractions", table_name="extractions")
        assert rows[0][0] == 1


# ---------------------------------------------------------------------------
# ensure_metadata — single-URI guarantee (must not pull in sibling files)
# ---------------------------------------------------------------------------


class TestEnsureMetadata:
    """``MmDatabase.ensure_metadata(uri)`` must insert exactly one row for *uri*.

    Regression: an earlier version scanned the parent directory and
    upserted every sibling, so indexing a single file polluted the DB
    with N rows. See the ``ensure_metadata`` filter on ``tbl["path"]``.
    """

    def test_inserts_only_requested_file(self, tmp_path: Path):
        for name in ("a.txt", "b.txt", "c.txt"):
            (tmp_path / name).write_text("x")
        db = MmDatabase(db_path=tmp_path / "test.db")

        db.ensure_metadata(str(tmp_path / "a.txt"))

        rows = db.get_files()
        assert len(rows) == 1
        assert rows[0]["uri"] == str(tmp_path / "a.txt")

    def test_siblings_not_inserted_across_calls(self, tmp_path: Path):
        """Each ensure_metadata inserts only its own URI, never a sibling."""
        for name in ("a.txt", "b.txt", "c.txt", "d.txt"):
            (tmp_path / name).write_text("x")
        db = MmDatabase(db_path=tmp_path / "test.db")

        db.ensure_metadata(str(tmp_path / "b.txt"))
        assert {r["name"] for r in db.get_files()} == {"b.txt"}

        db.ensure_metadata(str(tmp_path / "d.txt"))
        assert {r["name"] for r in db.get_files()} == {"b.txt", "d.txt"}

    def test_noop_when_row_exists(self, tmp_path: Path):
        (tmp_path / "a.txt").write_text("x")
        db = MmDatabase(db_path=tmp_path / "test.db")
        db.ensure_metadata(str(tmp_path / "a.txt"))
        db.ensure_metadata(str(tmp_path / "a.txt"))
        assert len(db.get_files()) == 1

    def test_noop_when_file_missing(self, tmp_path: Path):
        db = MmDatabase(db_path=tmp_path / "test.db")
        db.ensure_metadata(str(tmp_path / "missing.txt"))
        assert db.get_files() == []


# ---------------------------------------------------------------------------
# prune_missing — reconcile DB rows against disk (one-way only)
# ---------------------------------------------------------------------------


class TestPruneMissing:
    """``prune_missing`` deletes DB rows whose files no longer exist on disk.

    Strictly one-way: files on disk that aren't in the DB stay untouched
    (the normal "unindexed" state). The *disk_uris* hint short-circuits
    stat calls for files the caller already knows exist.
    """

    def test_requires_prefix_or_uris(self, db: MmDatabase):
        from mm.store.utils import prune_missing

        with pytest.raises(ValueError, match="requires either prefix or uris"):
            prune_missing(db=db)

    def test_prune_by_uri_list_deletes_only_missing(self, tmp_path: Path):
        from mm.store.utils import prune_missing

        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.txt").write_text("x")
        db = MmDatabase(db_path=tmp_path / "test.db")
        db.ensure_metadata(str(tmp_path / "a.txt"))
        db.ensure_metadata(str(tmp_path / "b.txt"))

        (tmp_path / "a.txt").unlink()
        deleted = prune_missing(
            uris=[str(tmp_path / "a.txt"), str(tmp_path / "b.txt")],
            db=db,
        )

        assert deleted == 1
        assert {r["name"] for r in db.get_files()} == {"b.txt"}

    def test_prune_by_prefix(self, tmp_path: Path):
        from mm.store.utils import prune_missing

        for name in ("a.txt", "b.txt", "c.txt"):
            (tmp_path / name).write_text("x")
        db = MmDatabase(db_path=tmp_path / "test.db")
        for name in ("a.txt", "b.txt", "c.txt"):
            db.ensure_metadata(str(tmp_path / name))

        (tmp_path / "b.txt").unlink()
        deleted = prune_missing(prefix=str(tmp_path), db=db)

        assert deleted == 1
        assert {r["name"] for r in db.get_files()} == {"a.txt", "c.txt"}

    def test_prune_is_scoped_to_prefix(self, tmp_path: Path):
        """Rows outside the prefix are never touched, even if their files are gone."""
        from mm.store.utils import prune_missing

        d1, d2 = tmp_path / "d1", tmp_path / "d2"
        d1.mkdir()
        d2.mkdir()
        (d1 / "a.txt").write_text("x")
        (d2 / "b.txt").write_text("x")
        db = MmDatabase(db_path=tmp_path / "test.db")
        db.ensure_metadata(str(d1 / "a.txt"))
        db.ensure_metadata(str(d2 / "b.txt"))

        (d1 / "a.txt").unlink()
        (d2 / "b.txt").unlink()
        deleted = prune_missing(prefix=str(d1), db=db)

        assert deleted == 1
        assert [r["uri"] for r in db.get_files()] == [str(d2 / "b.txt")]

    def test_noop_when_nothing_missing(self, tmp_path: Path):
        from mm.store.utils import prune_missing

        (tmp_path / "a.txt").write_text("x")
        db = MmDatabase(db_path=tmp_path / "test.db")
        db.ensure_metadata(str(tmp_path / "a.txt"))

        deleted = prune_missing(prefix=str(tmp_path), db=db)
        assert deleted == 0
        assert len(db.get_files()) == 1

    def test_on_disk_files_never_pruned(self, tmp_path: Path):
        """One-way guarantee: files absent from *disk_uris* but present on disk must survive.

        Simulates a caller whose scan excluded a file (gitignored, filtered
        by ``--kind``, etc.). The stat fallback must save it.
        """
        from mm.store.utils import prune_missing

        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.txt").write_text("x")
        db = MmDatabase(db_path=tmp_path / "test.db")
        db.ensure_metadata(str(tmp_path / "a.txt"))
        db.ensure_metadata(str(tmp_path / "b.txt"))

        # Caller's scan only saw a.txt (e.g. b.txt was gitignored).
        disk_uris = {str(tmp_path / "a.txt")}
        deleted = prune_missing(prefix=str(tmp_path), disk_uris=disk_uris, db=db)

        assert deleted == 0
        assert {r["name"] for r in db.get_files()} == {"a.txt", "b.txt"}

    def test_disk_uris_hint_short_circuits_stat(self, tmp_path: Path):
        """A URI in *disk_uris* is trusted and never stat'd.

        If the hint is stale (claims a deleted file still exists), the row
        survives this call — it'll be pruned on the next call with a fresh
        hint. This is the intentional tradeoff for avoiding the stat.
        """
        from mm.store.utils import prune_missing

        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.txt").write_text("x")
        db = MmDatabase(db_path=tmp_path / "test.db")
        db.ensure_metadata(str(tmp_path / "a.txt"))
        db.ensure_metadata(str(tmp_path / "b.txt"))

        (tmp_path / "b.txt").unlink()
        stale_hint = {str(tmp_path / "a.txt"), str(tmp_path / "b.txt")}
        assert prune_missing(prefix=str(tmp_path), disk_uris=stale_hint, db=db) == 0

        assert prune_missing(prefix=str(tmp_path), db=db) == 1
        assert {r["name"] for r in db.get_files()} == {"a.txt"}

    def test_prune_cascades_to_accurate_and_chunks(self, tmp_path: Path):
        """Deleting a files row cascades to extractions and chunks."""
        from mm.store.utils import prune_missing

        p = tmp_path / "a.txt"
        p.write_text("hello world")
        db = MmDatabase(db_path=tmp_path / "test.db")
        uri = str(p)
        db.ensure_metadata(uri)
        content_hash = get_hash(p)

        db.put_file_content(
            uri, {FileCol.CONTENT_HASH: content_hash, FileCol.TEXT_PREVIEW: "fast content"}
        )
        extraction_id = db.put_extraction(uri, content_hash, "default", "qwen", "accurate summary")

        assert db.get_extraction(extraction_id) is not None
        assert len(db.get_chunks(extraction_id)) > 0

        p.unlink()
        deleted = prune_missing(uris=[uri], db=db)

        assert deleted == 1
        assert db.get_file(uri) is None
        assert db.get_extraction(extraction_id) is None
        assert db.get_chunks(extraction_id) == []

    def test_delete_files_is_idempotent(self, tmp_path: Path):
        """``delete_files`` returns 0 on no-op inputs and is safe to call twice."""
        (tmp_path / "a.txt").write_text("x")
        db = MmDatabase(db_path=tmp_path / "test.db")
        db.ensure_metadata(str(tmp_path / "a.txt"))

        assert db.delete_files([]) == 0
        assert db.delete_files(["/nonexistent/path"]) == 0

        uri = str(tmp_path / "a.txt")
        assert db.delete_files([uri]) == 1
        assert db.delete_files([uri]) == 0
