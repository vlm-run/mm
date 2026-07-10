"""FTS5 full-text index over ``chunks`` — trigram tokenizer + BM25 ranking.

Covers the upgrade from the ``LIKE %q%`` substring scan to a real FTS5
index: the trigram tokenizer preserves literal substring + punctuation
matching while enabling ``bm25()`` ranking, external-content triggers keep
the index in sync with every chunk write, and a one-time ``'rebuild'``
backfill upgrades pre-existing databases.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mm.store.db import MmDatabase
from mm.store.utils import now_us


def _seed_chunk(db: MmDatabase, uri: str, text: str, *, idx: int = 0, eid: str = "e1") -> int:
    """Insert one chunk row (trigger indexes it) and return its rowid."""
    now = now_us()
    db.ensure_metadata(uri)
    db._connect.execute(
        "INSERT INTO extractions (id, file_uri, content_hash, profile, model, mode, "
        "detail, extra, summary, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (eid, uri, "h", "p", "m", "accurate", 0, "", "summary", now),
    )
    db._connect.execute(
        "INSERT INTO chunks (extraction_id, file_uri, content_hash, profile, model, "
        "mode, chunk_idx, chunk_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (eid, uri, "h", "p", "m", "accurate", idx, text, now),
    )
    db._connect.commit()
    row = db._connect.execute(
        "SELECT id FROM chunks WHERE file_uri = ? AND chunk_idx = ?", (uri, idx)
    ).fetchone()
    return int(row["id"])


@pytest.fixture()
def db(tmp_path: Path) -> MmDatabase:
    return MmDatabase(db_path=tmp_path / "test.db")


class TestFTS5Index:
    def test_bm25_returns_substring_match_with_rank(self, db: MmDatabase, tmp_path: Path):
        uri = str(tmp_path / "doc.png")
        Path(uri).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        _seed_chunk(db, uri, "Breaking the Quantum Loop today")

        rows = db.search_chunks_bm25("ntum Loop")
        assert len(rows) == 1
        assert rows[0]["file_uri"] == uri
        assert "bm25" in rows[0]

    def test_search_chunks_fts_dispatches_to_bm25(self, db: MmDatabase, tmp_path: Path):
        uri = str(tmp_path / "doc.png")
        Path(uri).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        _seed_chunk(db, uri, "the quick brown fox")

        rows = db.search_chunks_fts("quick brown")
        assert len(rows) == 1
        assert "bm25" in rows[0]

    def test_bm25_ranks_shorter_chunk_higher(self, db: MmDatabase, tmp_path: Path):
        """All else equal, BM25 favours shorter fields (less dilution)."""
        long_uri = str(tmp_path / "long.png")
        short_uri = str(tmp_path / "short.png")
        for u in (long_uri, short_uri):
            Path(u).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        _seed_chunk(db, long_uri, "rareterm " + "padding " * 200, idx=0, eid="e-long")
        _seed_chunk(db, short_uri, "rareterm here", idx=0, eid="e-short")

        rows = db.search_chunks_bm25("rareterm")
        assert [r["file_uri"] for r in rows] == [short_uri, long_uri]
        assert rows[0]["bm25"] < rows[1]["bm25"]  # lower = more relevant

    def test_trigger_syncs_on_delete(self, db: MmDatabase, tmp_path: Path):
        uri = str(tmp_path / "doc.png")
        Path(uri).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        _seed_chunk(db, uri, "deletable token here")
        assert len(db.search_chunks_bm25("deletable")) == 1

        db._connect.execute("DELETE FROM chunks WHERE file_uri = ?", (uri,))
        db._connect.commit()
        assert db.search_chunks_bm25("deletable") == []

    def test_phrase_query_is_case_insensitive(self, db: MmDatabase, tmp_path: Path):
        uri = str(tmp_path / "doc.png")
        Path(uri).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        _seed_chunk(db, uri, "Breaking the Quantum Loop")

        assert len(db.search_chunks_bm25("QUANTUM loop")) == 1
        assert len(db.search_chunks_bm25("ntum LOOP")) == 1

    def test_empty_query_short_circuits(self, db: MmDatabase, tmp_path: Path):
        uri = str(tmp_path / "doc.png")
        Path(uri).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        _seed_chunk(db, uri, "anything at all")
        assert db.search_chunks_bm25("") == []
        assert db.search_chunks_bm25("   ") == []


class TestFTS5Backfill:
    def test_rebuild_indexes_pre_existing_chunks(self, tmp_path: Path):
        """A DB with chunks but no FTS table (pre-upgrade) backfills on open."""
        db_path = tmp_path / "legacy.db"
        db = MmDatabase(db_path=db_path)
        _ = db._connect
        uri = str(tmp_path / "doc.png")
        Path(uri).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        _seed_chunk(db, uri, "legacy Quantum Loop here")

        for t in ("chunks_fts_ai", "chunks_fts_ad", "chunks_fts_au"):
            db._connect.execute(f"DROP TRIGGER IF EXISTS {t}")
        db._connect.execute("DROP TABLE chunks_fts")
        db._connect.commit()
        db._connect.close()

        reopened = MmDatabase(db_path=db_path)
        _ = reopened._connect
        assert len(reopened.search_chunks_bm25("Quantum")) == 1

    def test_backfill_is_idempotent_across_reconnects(self, tmp_path: Path):
        db_path = tmp_path / "legacy.db"
        db = MmDatabase(db_path=db_path)
        _ = db._connect
        uri = str(tmp_path / "doc.png")
        Path(uri).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        _seed_chunk(db, uri, "once indexed, stays indexed")
        db._connect.close()

        for _ in range(2):
            fresh = MmDatabase(db_path=db_path)
            _ = fresh._connect
            assert len(fresh.search_chunks_bm25("indexed")) == 1
            fresh._connect.close()
