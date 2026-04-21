"""SQLite + sqlite-vec storage backend for mm.

Single global database at ~/.local/share/mm/mm.db with tables:
  - files:      L0 + L1 metadata (one row per file, uri = absolute path)
  - l2_results: LLM-generated summaries (many per file)
  - chunks:     Chunked L2 content (many per L2 result)
  - chunks_vec: Embedding vectors (sqlite-vec virtual table, linked via chunk_id)
  - cache:      Key-value cache for L1/L2 results

Vector search (ANN/KNN):
  sqlite-vec provides exact KNN via brute-force scan over the vec0 virtual table.
  Queries use the MATCH operator with a query vector packed as raw float bytes:

    SELECT c.*, v.distance
    FROM chunks c
    JOIN chunks_vec v ON v.chunk_id = c.id
    WHERE v.embedding MATCH <query_vec_bytes> AND k = <limit>
    ORDER BY v.distance

  The `k = <limit>` clause is required by sqlite-vec to bound the search.
  Distance metric is L2 (Euclidean) by default. For small-to-medium datasets
  (<1M vectors) this is fast enough (sub-ms for 10K vectors). For larger
  datasets, sqlite-vec supports partitioned ANN indices.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mm.store.util import get_l2_id, now_us

if TYPE_CHECKING:
    import pyarrow as pa

CHUNK_SIZE = 2048
CHUNK_OVERLAP = 100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_us(val) -> int | None:
    """Convert Arrow timestamp (datetime or int) to microseconds since epoch."""
    if val is None:
        return None
    if isinstance(val, int):
        return val
    # datetime from Arrow — always UTC but may be naive
    import datetime as _dt

    if val.tzinfo is None:
        val = val.replace(tzinfo=_dt.timezone.utc)
    return int(val.timestamp() * 1_000_000)


# ---------------------------------------------------------------------------
# MmDatabase
# ---------------------------------------------------------------------------


class MmDatabase:
    """Global SQLite database for mm."""

    DB_DIR = Path.home() / ".local" / "share" / "mm"
    DB_PATH = DB_DIR / "mm.db"

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or self.DB_PATH
        self._conn: sqlite3.Connection | None = None
        self._vec_available: bool = False

    @property
    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
            self._vec_available = False
            try:
                import sqlite_vec

                self._conn.enable_load_extension(True)
                sqlite_vec.load(self._conn)
                self._conn.enable_load_extension(False)
                self._vec_available = True
            except (AttributeError, ImportError, OSError):
                pass
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._ensure_tables()
        return self._conn

    def _ensure_tables(self) -> None:
        """Create tables, apply additive migrations, then create indexes.

        Order matters: indexes can reference newly migrated columns
        (``session_id``, ``ref_id``) that aren't present in legacy DBs
        until the migration step runs.
        """
        from mm.store.schema import (
            CHUNKS_DDL,
            FILES_DDL,
            FILES_INDEX_DDL,
            L2_RESULTS_DDL,
        )

        assert self._conn is not None, "_ensure_tables called before _connect"
        self._conn.executescript(FILES_DDL + L2_RESULTS_DDL + CHUNKS_DDL)
        self._migrate_files()
        self._conn.executescript(FILES_INDEX_DDL)

    def _migrate_files(self) -> None:
        """Apply additive ``files`` migrations idempotently.

        SQLite's ``ALTER TABLE ADD COLUMN`` does not support ``IF NOT EXISTS``,
        so we inspect ``PRAGMA table_info`` and skip columns that already
        exist. Safe to call on every connect.
        """
        from mm.store.schema import FILES_MIGRATIONS

        assert self._conn is not None, "_migrate_files called before _connect"
        existing = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(files)").fetchall()
        }
        for column, ddl in FILES_MIGRATIONS:
            if column not in existing:
                self._conn.execute(ddl)
        self._conn.commit()

    # -- Files (L0 + L1) --

    def upsert_files(
        self,
        scanner_table: pa.Table,
        root: Path,
        *,
        session_id: str | None = None,
        refs: dict[str, str] | None = None,
    ) -> int:
        """Write L0 scan results. Preserves existing L1 columns on re-upsert.

        When ``session_id`` is provided, every row is tagged with that
        session. ``refs`` supplies the ``{relative_path: ref_id}``
        mapping generated by the :class:`mm.Context`; any rows without a
        supplied ref get a freshly random one via
        :func:`mm.refs.make_ref_id`.

        On conflict, ``session_id`` is overwritten but ``ref_id`` is
        preserved via ``COALESCE(files.ref_id, excluded.ref_id)`` — once
        a row is tagged with a ref in a given session, that ref is
        stable for the lifetime of the row.
        """
        from mm.refs import make_ref_id
        from mm.store.schema import L0_COLUMNS

        n = scanner_table.num_rows
        if n == 0:
            return int(self._connect.execute("SELECT COUNT(*) FROM files").fetchone()[0])

        db = self._connect
        now = now_us()
        columns = (
            "uri, name, stem, ext, size, modified, created, mime, kind, is_binary, "
            "depth, parent, width, height, phash, session_id, ref_id, indexed_at"
        )
        placeholders = ", ".join("?" * 18)
        l0_update_cols = [c for c in L0_COLUMNS if c != "uri"]
        update_clauses = [f"{c} = excluded.{c}" for c in l0_update_cols]
        if session_id is not None:
            update_clauses.append("session_id = excluded.session_id")
            # Keep the existing ref_id only when the row stays in the same
            # session; swap to the new one when retagging sessions.
            update_clauses.append(
                "ref_id = CASE "
                "WHEN files.session_id = excluded.session_id "
                "THEN COALESCE(files.ref_id, excluded.ref_id) "
                "ELSE excluded.ref_id END"
            )
        l0_updates = ", ".join(update_clauses)
        sql = (
            f"INSERT INTO files ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT(uri) DO UPDATE SET {l0_updates}"
        )

        d = scanner_table.to_pydict()
        root_s = str(root)
        paths = d["path"]
        names = d.get("name", [""] * n)
        stems = d.get("stem", [""] * n)
        exts = d.get("ext", [""] * n)
        sizes = d.get("size", [0] * n)
        modifieds = d.get("modified", [None] * n)
        createds = d.get("created", [None] * n)
        mimes = d.get("mime", [""] * n)
        kinds = d.get("kind", ["other"] * n)
        is_binarys = d.get("is_binary", [False] * n)
        depths = d.get("depth", [0] * n)
        parents = d.get("parent", [""] * n)
        widths = d.get("width", [None] * n)
        heights = d.get("height", [None] * n)
        phashes = d.get("phash", [None] * n)

        rows = []
        for i in range(n):
            rel_path = paths[i]
            uri = f"{root_s}/{rel_path}"
            kind = kinds[i] or "other"
            if session_id is None:
                ref_id = None
            elif refs is not None and rel_path in refs:
                ref_id = refs[rel_path]
            else:
                ref_id = make_ref_id(kind)
            rows.append(
                (
                    uri,
                    names[i] or "",
                    stems[i] or "",
                    exts[i] or "",
                    sizes[i] or 0,
                    _to_us(modifieds[i]),
                    _to_us(createds[i]),
                    mimes[i] or "",
                    kind,
                    int(bool(is_binarys[i])),
                    depths[i] or 0,
                    f"{root_s}/{parents[i]}" if parents[i] else root_s,
                    widths[i],
                    heights[i],
                    f"{phashes[i]:016x}" if phashes[i] is not None else None,
                    session_id,
                    ref_id,
                    now,
                )
            )

        db.executemany(sql, rows)
        db.commit()
        return int(db.execute("SELECT COUNT(*) FROM files").fetchone()[0])

    def get_file_by_ref(self, session_id: str, ref_id: str) -> dict[str, Any] | None:
        """Resolve a ``<session_id>/<ref_id>`` pair to its ``files`` row."""
        row = self._connect.execute(
            "SELECT * FROM files WHERE session_id = ? AND ref_id = ?",
            (session_id, ref_id),
        ).fetchone()
        return dict(row) if row else None

    def list_session_files(self, session_id: str) -> list[dict[str, Any]]:
        """Return all ``files`` rows tagged with ``session_id`` (ordered by uri)."""
        rows = self._connect.execute(
            "SELECT * FROM files WHERE session_id = ? ORDER BY uri",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_file(self, uri: str) -> dict[str, Any] | None:
        row = self._connect.execute("SELECT * FROM files WHERE uri = ?", (uri,)).fetchone()
        return dict(row) if row else None

    def get_files(self, where: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM files"
        if where:
            q += f" WHERE {where}"
        return [dict(r) for r in self._connect.execute(q).fetchall()]

    def ensure_l0(self, uri: str) -> None:
        """Ensure a ``files`` row exists for *uri* over L0, scanning via Rust if needed."""
        if self.get_file(uri) is not None:
            return

        if not Path(uri).exists():
            return

        from mm._mm import Scanner

        scanner = Scanner(str(Path(uri).parent))
        scanner.scan()
        self.upsert_files(scanner.to_arrow(), Path(uri).parent)

    def is_stale(self, uri: str, mtime_us: int, size: int) -> bool:
        row = self._connect.execute(
            "SELECT modified, size FROM files WHERE uri = ?", (uri,)
        ).fetchone()
        if row is None:
            return True
        return bool(row[0] != mtime_us or row[1] != size)

    def get_l1(self, content_hash: str) -> str | None:
        row = self._connect.execute(
            "SELECT text_preview FROM files "
            "WHERE content_hash = ? AND text_preview IS NOT NULL "
            "ORDER BY l1_indexed_at DESC LIMIT 1",
            (content_hash,),
        ).fetchone()
        if row is None:
            return None
        return str(row[0]) if row[0] is not None else None

    def update_l1(self, uri: str, data: dict[str, Any]) -> None:
        """Fill L1 columns for a specific file."""
        from mm.store.schema import FileCol

        self.ensure_l0(uri)
        if self.get_file(uri) is None:
            return

        data[FileCol.L1_INDEXED_AT] = now_us()
        sets = ", ".join(f"{k} = ?" for k in data)
        self._connect.execute(f"UPDATE files SET {sets} WHERE uri = ?", (*data.values(), uri))
        self._connect.commit()

    def put_l1(self, uri: str, content_hash: str, content: str) -> None:
        from mm.store.schema import FileCol

        self.update_l1(uri, {FileCol.CONTENT_HASH: content_hash, FileCol.TEXT_PREVIEW: content})

    # -- L2 --

    def get_l2(self, l2_id: str) -> str | None:
        """Look up a cached L2 result. Returns full content reassembled from chunks."""
        row = self._connect.execute("SELECT id FROM l2_results WHERE id = ?", (l2_id,)).fetchone()
        if row is None:
            return None
        chunks = self._connect.execute(
            "SELECT chunk_text FROM chunks WHERE l2_result_id = ? AND level = 2 ORDER BY chunk_idx",
            (l2_id,),
        ).fetchall()
        if not chunks:
            return None
        parts = [chunks[0][0]]
        for c in chunks[1:]:
            parts.append(c[0][CHUNK_OVERLAP:])
        return "".join(parts)

    def evict_l2(self, l2_id: str) -> int:
        """Delete an L2 result + its chunks/embeddings for the given key.

        chunks are cascade-deleted via FK ON DELETE CASCADE.
        chunks_vec (sqlite-vec virtual table) doesn't support FK cascades,
        so embeddings are cleaned up manually before the cascade fires.

        Returns 1 if a row was deleted, 0 otherwise.
        """
        db = self._connect
        # Clean up chunks_vec (virtual table, no FK cascade support).
        chunk_ids = [
            r[0]
            for r in db.execute("SELECT id FROM chunks WHERE l2_result_id = ?", (l2_id,)).fetchall()
        ]
        if chunk_ids:
            cp = ",".join("?" * len(chunk_ids))
            has_vec = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunks_vec'"
            ).fetchone()
            if has_vec:
                db.execute(f"DELETE FROM chunks_vec WHERE chunk_id IN ({cp})", chunk_ids)

        # Delete l2_results — chunks cascade-deleted via FK.
        cursor = db.execute("DELETE FROM l2_results WHERE id = ?", (l2_id,))
        db.commit()

        return cursor.rowcount

    def put_l2(
        self,
        uri: str,
        content_hash: str,
        profile: str,
        model: str,
        content: str,
        mode: str | None = None,
        detail=False,
        *,
        extra="",
    ) -> str:
        """Insert or replace L2 result, chunk L1+L2 content. Returns l2_results.id."""
        self.ensure_l0(uri)

        # Get L1 content
        l1_content = self.get_l1(content_hash)
        if not l1_content:
            raise RuntimeError("L1 content not found")

        l2_id = get_l2_id(content_hash, profile, model, mode, detail, extra=extra)
        now = now_us()
        summary = content[:500] if len(content) > 500 else content
        self._connect.execute(
            "INSERT OR REPLACE INTO l2_results (id, file_uri, content_hash, profile, model, mode, detail, extra, summary, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (l2_id, uri, content_hash, profile, model, mode, int(detail), extra, summary, now),
        )
        self._connect.commit()

        # Chunk L1 (the raw extracted content the LLM saw) and L2 (the LLM-generated summary/description)
        self._put_chunks(l2_id, uri, content_hash, profile, model, l1_content, level=1)
        self._put_chunks(l2_id, uri, content_hash, profile, model, content, level=2)
        return l2_id

    # -- Chunks --

    def _put_chunks(
        self,
        l2_result_id: str,
        uri: str,
        content_hash: str,
        profile: str,
        model: str,
        content: str,
        level: int,
    ) -> None:
        now = now_us()
        step = CHUNK_SIZE - CHUNK_OVERLAP
        texts: list[str] = []
        for i in range(0, len(content), step):
            texts.append(content[i : i + CHUNK_SIZE])
            if i + CHUNK_SIZE >= len(content):
                break
        if not texts:
            return
        db = self._connect
        db.executemany(
            "INSERT INTO chunks (l2_result_id, file_uri, content_hash, profile, model, level, chunk_idx, chunk_text, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (l2_result_id, uri, content_hash, profile, model, level, idx, text, now)
                for idx, text in enumerate(texts)
            ],
        )
        db.commit()

    def get_chunks(self, l2_result_id: str, *, level: int | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM chunks WHERE l2_result_id = ?"
        params: list[str | int] = [l2_result_id]
        if level is not None:
            q += " AND level = ?"
            params.append(level)
        q += " ORDER BY level, chunk_idx"
        return [dict(r) for r in self._connect.execute(q, params).fetchall()]

    def get_full_content(
        self, uri: str, content_hash: str, profile: str, model: str, *, level: int = 2
    ) -> str | None:
        """
        Reassemble full content for a given file/profile/model/level from chunks.

        Returns:
            str | None - The full reassembled content, or None if no chunks found.
        """
        rows = self._connect.execute(
            "SELECT chunk_text FROM chunks WHERE file_uri = ? AND content_hash = ? "
            "AND profile = ? AND model = ? AND level = ? ORDER BY chunk_idx",
            (uri, content_hash, profile, model, level),
        ).fetchall()
        if not rows:
            return None
        # Reassemble: first chunk in full, subsequent chunks skip the overlap prefix
        parts = [rows[0][0]]
        for r in rows[1:]:
            parts.append(r[0][CHUNK_OVERLAP:])
        return "".join(parts)

    # -- Embeddings --

    def _ensure_vec_table(self, dim: int) -> None:
        if not self._vec_available:
            return
        db = self._connect
        # Check if vec table exists
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunks_vec'"
        ).fetchone()
        if not exists:
            db.execute(
                f"CREATE VIRTUAL TABLE chunks_vec USING vec0(chunk_id INTEGER PRIMARY KEY, embedding float[{dim}])"
            )
            db.commit()

    def upsert_embeddings(
        self,
        *,
        l2_id: str,
        vectors: list[list[float]],
    ) -> None:
        if not vectors or not self._vec_available:
            return

        import struct

        db = self._connect
        dim = len(vectors[0])
        self._ensure_vec_table(dim)

        chunks = self.get_chunks(l2_id)
        n = min(len(vectors), len(chunks))

        vec_inserts = []
        for i in range(n):
            chunk_id = chunks[i]["id"]
            vec_inserts.append((chunk_id, struct.pack(f"{dim}f", *vectors[i])))

        db.executemany(
            "INSERT OR REPLACE INTO chunks_vec (chunk_id, embedding) VALUES (?, ?)", vec_inserts
        )
        db.commit()

    def search_similar(
        self,
        vector: list[float],
        limit: int = 10,
        where: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self._vec_available:
            return []
        db = self._connect
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunks_vec'"
        ).fetchone()
        if not exists:
            return []

        import struct

        dim = len(vector)
        vec_bytes = struct.pack(f"{dim}f", *vector)
        if where:
            rows = db.execute(
                "SELECT c.*, v.distance FROM chunks c "
                "JOIN chunks_vec v ON v.chunk_id = c.id "
                f"WHERE v.embedding MATCH ? AND k = ? AND {where} "
                "ORDER BY v.distance LIMIT ?",
                (vec_bytes, limit, limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT c.*, v.distance FROM chunks c "
                "JOIN chunks_vec v ON v.chunk_id = c.id "
                "WHERE v.embedding MATCH ? AND k = ? "
                "ORDER BY v.distance LIMIT ?",
                (vec_bytes, limit, limit),
            ).fetchall()

        return [dict(r) for r in rows]

    # -- SQL --

    def sql(self, query: str, table_name: str = "files") -> tuple[list[str], list[tuple]]:
        """Run a SQL query against the persistent store.

        Returns (column_names, rows).
        """
        cursor = self._connect.execute(query)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return columns, cursor.fetchall()

    # -- Indexes --

    def ensure_indexes(self) -> None:
        # Indexes are created in DDL via CREATE INDEX IF NOT EXISTS
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
