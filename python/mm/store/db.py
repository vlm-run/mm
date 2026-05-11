"""SQLite + sqlite-vec storage backend for mm.

Single global database at ~/.local/share/mm/mm.db with tables:
  - files:        file metadata + locally-extracted content columns
                  (one row per file, uri = absolute path)
  - extractions:  pipeline outputs beyond the plain ``files`` read
                  (mode = 'fast' or 'accurate'; many per file)
  - chunks:       chunked content tagged with one of three tiers
                  (metadata = files.text_preview;
                   fast/accurate = extraction output)
  - chunks_vec:   embedding vectors (sqlite-vec virtual table, linked via chunk_id)
  - cache:        key-value cache for extraction results

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

import json
import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mm.store.utils import get_extraction_id, now_us

if TYPE_CHECKING:
    from pyarrow import Table

CHUNK_SIZE = 2048
CHUNK_OVERLAP = 100


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


class MmDatabase:
    """Global SQLite database for mm."""

    DB_DIR = Path.home() / ".local" / "share" / "mm"
    DB_PATH = DB_DIR / "mm.db"

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or self.DB_PATH
        self._tls = threading.local()
        self._schema_ready: bool = False
        self._lock = threading.RLock()

    @property
    def _vec_available(self) -> bool:
        _ = self._connect
        return getattr(self._tls, "vec_loaded", False)

    @property
    def _conn(self) -> sqlite3.Connection | None:
        return getattr(self._tls, "conn", None)

    @property
    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._tls, "conn", None)
        if conn is not None:
            return conn

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            import sqlite_vec

            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            self._tls.vec_loaded = True
        except (AttributeError, ImportError, OSError):
            self._tls.vec_loaded = False
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        self._tls.conn = conn

        if not self._schema_ready:
            with self._lock:
                if not self._schema_ready:
                    self._ensure_tables()
                    self._schema_ready = True
        return conn

    def _ensure_tables(self) -> None:
        """Migrate legacy schemas, create tables, then create indexes.

        Order matters:
          1. Legacy rename/drop migrations run first so renames land on the
             original tables instead of coexisting with empty parallel ones
             created by ``CREATE TABLE IF NOT EXISTS``.
          2. ``CREATE TABLE IF NOT EXISTS`` is a no-op on migrated tables and
             a fresh-create on new databases.
          3. Additive column migrations (``session_id``, ``ref_id``) run before
             index creation since indexes reference those columns.
        """
        from mm.store.schema import (
            CHUNKS_DDL,
            EXTRACTIONS_DDL,
            FILES_DDL,
            FILES_INDEX_DDL,
        )

        assert self._conn is not None, "_ensure_tables called before _connect"
        self._migrate_legacy()
        self._conn.executescript(FILES_DDL + EXTRACTIONS_DDL + CHUNKS_DDL)
        self._migrate_files()
        self._conn.executescript(FILES_INDEX_DDL)

    def _migrate_legacy(self) -> None:
        """Bring pre-extractions-rename databases forward to the current schema.

        Two changes from the legacy schema (pre commit 8b758e6):
          * ``files.fast_indexed_at`` was renamed to ``files.content_indexed_at``.
            Renamed in place to preserve the indexed metadata cache.
          * ``accurate_results`` was renamed to ``extractions`` and
            ``chunks.accurate_result_id`` to ``chunks.extraction_id`` (with
            relaxed nullability and a new ``mode`` CHECK constraint). The
            extraction/chunk cache is rebuildable, so legacy ``accurate_results``
            and ``chunks`` (plus the ``chunks_vec`` virtual table) are dropped
            — the CREATE TABLE step in ``_ensure_tables`` recreates them with
            the current schema.

        Idempotent: each branch inspects the live schema and is a no-op once
        the migration has already run.
        """
        from mm.store.schema import (
            FILES_RENAMES,
            LEGACY_CACHE_TABLES,
            LEGACY_CHUNK_COLUMNS,
        )

        assert self._conn is not None, "_migrate_legacy called before _connect"
        conn = self._conn

        files_cols = {row["name"] for row in conn.execute("PRAGMA table_info(files)").fetchall()}
        if files_cols:
            for old, new in FILES_RENAMES:
                if old in files_cols and new not in files_cols:
                    conn.execute(f"ALTER TABLE files RENAME COLUMN {old} TO {new}")

        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        chunks_cols = {row["name"] for row in conn.execute("PRAGMA table_info(chunks)").fetchall()}
        legacy_chunks = bool(chunks_cols) and any(
            col in chunks_cols for col in LEGACY_CHUNK_COLUMNS
        )
        legacy_cache = any(t in tables for t in LEGACY_CACHE_TABLES)
        if legacy_chunks or legacy_cache:
            # Drop FK-linked cache tables together. Disable FK enforcement so
            # the order of drops doesn't matter.
            prev_fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            conn.execute("PRAGMA foreign_keys=OFF")
            try:
                conn.execute("DROP TABLE IF EXISTS chunks_vec")
                conn.execute("DROP TABLE IF EXISTS chunks")
                for table in LEGACY_CACHE_TABLES:
                    conn.execute(f"DROP TABLE IF EXISTS {table}")
            finally:
                conn.execute(f"PRAGMA foreign_keys={'ON' if prev_fk else 'OFF'}")

        conn.commit()

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

    # -- Files (metadata + locally extracted content) --

    def upsert_files(
        self,
        scanner_table: Table,
        root: Path,
        *,
        session_id: str | None = None,
        refs: dict[str, str] | None = None,
    ) -> int:
        """Write metadata scan results. Preserves existing content columns on re-upsert.

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
        from mm.store.schema import METADATA_COLUMNS

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
        metadata_update_cols = [c for c in METADATA_COLUMNS if c != "uri"]
        update_clauses = [f"{c} = excluded.{c}" for c in metadata_update_cols]
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
        metadata_updates = ", ".join(update_clauses)
        sql = (
            f"INSERT INTO files ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT(uri) DO UPDATE SET {metadata_updates}"
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

    def ensure_metadata(self, uri: str) -> None:
        """Ensure a ``files`` row exists for *uri*, scanning via Rust if needed."""
        if self.get_file(uri) is not None:
            return

        p = Path(uri)
        if not p.exists():
            return

        from mm._mm import Scanner

        scanner = Scanner(str(p.parent))
        scanner.scan()
        tbl = scanner.to_arrow()
        try:
            idx = tbl["path"].to_pylist().index(p.name)
        except ValueError:
            return
        self.upsert_files(tbl.slice(idx, 1), p.parent)

    def delete_files(self, uris: list[str]) -> int:
        """Delete ``files`` rows by URI, cascading through chunks_vec manually.

        Returns the number of rows deleted.
        """
        from mm.utils import batch_array

        if not uris:
            return 0

        db = self._connect
        has_vec = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunks_vec'"
        ).fetchone()

        deleted = 0
        for batch in batch_array(uris, 500):
            ph = ",".join("?" * len(batch))
            if has_vec:
                chunk_ids = [
                    r[0]
                    for r in db.execute(
                        f"SELECT id FROM chunks WHERE file_uri IN ({ph})", batch
                    ).fetchall()
                ]
                if chunk_ids:
                    for chunk_batch in batch_array(chunk_ids, 500):
                        cp = ",".join("?" * len(chunk_batch))
                        db.execute(f"DELETE FROM chunks_vec WHERE chunk_id IN ({cp})", chunk_batch)
            db.execute(
                f"DELETE FROM chunks WHERE file_uri IN ({ph}) AND extraction_id IS NULL",
                batch,
            )
            cur = db.execute(f"DELETE FROM files WHERE uri IN ({ph})", batch)
            deleted += cur.rowcount or 0
        db.commit()
        return deleted

    def is_stale(self, uri: str, mtime_us: int, size: int) -> bool:
        row = self._connect.execute(
            "SELECT modified, size FROM files WHERE uri = ?", (uri,)
        ).fetchone()
        if row is None:
            return True
        return bool(row[0] != mtime_us or row[1] != size)

    def get_file_content(self, content_hash: str) -> str | None:
        """Read the locally-extracted text preview for a file by content hash."""
        row = self._connect.execute(
            "SELECT text_preview FROM files "
            "WHERE content_hash = ? AND text_preview IS NOT NULL "
            "ORDER BY content_indexed_at DESC LIMIT 1",
            (content_hash,),
        ).fetchone()
        if row is None:
            return None
        return str(row[0]) if row[0] is not None else None

    def update_file_fields(self, uri: str, data: dict[str, Any]) -> None:
        """Fill content columns for a specific file."""
        from mm.store.schema import FileCol

        self.ensure_metadata(uri)
        if self.get_file(uri) is None:
            return

        data[FileCol.CONTENT_INDEXED_AT] = now_us()
        sets = ", ".join(f"{k} = ?" for k in data)
        self._connect.execute(f"UPDATE files SET {sets} WHERE uri = ?", (*data.values(), uri))
        self._connect.commit()

    def put_file_content(self, uri: str, content_hash: str, content: str) -> None:
        """Store locally-extracted content (``text_preview``) for *uri*."""
        from mm.store.schema import FileCol

        self.update_file_fields(
            uri, {FileCol.CONTENT_HASH: content_hash, FileCol.TEXT_PREVIEW: content}
        )

    # -- Extractions --

    def get_extraction(self, extraction_id: str) -> str | None:
        """Look up a cached extraction. Returns full content reassembled from chunks.

        Reads chunks tagged with the extraction's own ``mode`` (``'fast'`` or
        ``'accurate'``) — i.e. the pipeline output, not the underlying
        ``'metadata'`` layer. ``chunks.mode='metadata'`` is the locally-extracted
        tier (``files.text_preview``) that pipelines read from.
        """
        row = self._connect.execute(
            "SELECT mode FROM extractions WHERE id = ?", (extraction_id,)
        ).fetchone()
        if row is None:
            return None
        chunks = self._connect.execute(
            "SELECT chunk_text FROM chunks WHERE extraction_id = ? AND mode = ? ORDER BY chunk_idx",
            (extraction_id, row["mode"]),
        ).fetchall()
        if not chunks:
            return None
        parts = [chunks[0][0]]
        for c in chunks[1:]:
            parts.append(c[0][CHUNK_OVERLAP:])
        return "".join(parts)

    def get_extraction_metadata(self, extraction_id: str) -> dict[str, Any] | None:
        """Return the JSON-decoded ``metadata`` column for an extraction."""
        row = self._connect.execute(
            "SELECT metadata FROM extractions WHERE id = ?", (extraction_id,)
        ).fetchone()
        if row is None or row[0] is None:
            return None
        try:
            value = json.loads(row[0])
        except (TypeError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def evict_extraction(self, extraction_id: str) -> int:
        """Delete an extraction + its chunks/embeddings for the given key.

        chunks are cascade-deleted via FK ON DELETE CASCADE.
        chunks_vec (sqlite-vec virtual table) doesn't support FK cascades,
        so embeddings are cleaned up manually before the cascade fires.

        Returns 1 if a row was deleted, 0 otherwise.
        """
        db = self._connect
        chunk_ids = [
            r[0]
            for r in db.execute(
                "SELECT id FROM chunks WHERE extraction_id = ?", (extraction_id,)
            ).fetchall()
        ]
        if chunk_ids:
            cp = ",".join("?" * len(chunk_ids))
            has_vec = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunks_vec'"
            ).fetchone()
            if has_vec:
                db.execute(f"DELETE FROM chunks_vec WHERE chunk_id IN ({cp})", chunk_ids)

        cursor = db.execute("DELETE FROM extractions WHERE id = ?", (extraction_id,))
        db.commit()

        return cursor.rowcount

    def put_extraction(
        self,
        uri: str,
        content_hash: str,
        profile: str,
        model: str,
        content: str,
        mode: str = "accurate",
        detail: bool = False,
        *,
        extra: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Insert or replace an extraction; chunk file-content + extraction output.

        ``mode`` is ``'fast'`` or ``'accurate'`` (default ``'accurate'``).
        Returns ``extractions.id``.
        """
        if mode not in ("fast", "accurate"):
            raise ValueError(f"mode must be 'fast' or 'accurate', got {mode!r}")
        self.ensure_metadata(uri)

        file_content = self.get_file_content(content_hash)
        if not file_content:
            raise RuntimeError("File content not found")

        extraction_id = get_extraction_id(content_hash, profile, model, mode, detail, extra=extra)
        now = now_us()
        summary = content[:500] if len(content) > 500 else content
        metadata_json = json.dumps(metadata, separators=(",", ":")) if metadata else None
        self._connect.execute(
            "INSERT OR REPLACE INTO extractions "
            "(id, file_uri, content_hash, profile, model, mode, detail, extra, summary, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                extraction_id,
                uri,
                content_hash,
                profile,
                model,
                mode,
                int(detail),
                extra,
                summary,
                metadata_json,
                now,
            ),
        )
        self._connect.commit()

        # ``chunks.mode`` tags the *content tier* the chunk belongs to:
        #   'metadata' → the file's locally-extracted text (files.text_preview)
        #                — the input pipelines read from
        #   <mode>     → the extraction's own pipeline output, tagged with the
        #                pipeline that produced it (matches extractions.mode)
        # ``get_extraction`` reads the pipeline-output tier; the metadata tier
        # is reusable across fast/accurate extractions of the same file.
        self._put_chunks(
            extraction_id, uri, content_hash, profile, model, file_content, mode="metadata"
        )
        self._put_chunks(extraction_id, uri, content_hash, profile, model, content, mode=mode)
        return extraction_id

    def _put_chunks(
        self,
        extraction_id: str | None,
        uri: str,
        content_hash: str,
        profile: str,
        model: str,
        content: str,
        mode: str,
    ) -> None:
        """Slide a 2 KiB window over *content*; persist each chunk row."""
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
            "INSERT INTO chunks "
            "(extraction_id, file_uri, content_hash, profile, model, mode, chunk_idx, chunk_text, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (extraction_id, uri, content_hash, profile, model, mode, idx, text, now)
                for idx, text in enumerate(texts)
            ],
        )
        db.commit()

    def get_chunks(self, extraction_id: str, *, mode: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM chunks WHERE extraction_id = ?"
        params: list[str] = [extraction_id]
        if mode is not None:
            q += " AND mode = ?"
            params.append(mode)
        q += " ORDER BY mode, chunk_idx"
        return [dict(r) for r in self._connect.execute(q, params).fetchall()]

    def has_text_chunks(self, content_hash: str) -> bool:
        """Return True if FK-orphan text chunks exist for *content_hash*."""
        row = self._connect.execute(
            "SELECT 1 FROM chunks WHERE content_hash = ? AND extraction_id IS NULL "
            "AND mode = 'metadata' LIMIT 1",
            (content_hash,),
        ).fetchone()
        return row is not None

    def get_text_chunks(self, content_hash: str) -> list[dict[str, Any]]:
        """Fetch FK-orphan chunks for *content_hash* in chunk order."""
        rows = self._connect.execute(
            "SELECT * FROM chunks WHERE content_hash = ? AND extraction_id IS NULL "
            "AND mode = 'metadata' ORDER BY chunk_idx",
            (content_hash,),
        ).fetchall()
        return [dict(r) for r in rows]

    def put_text_chunks(
        self,
        *,
        uri: str,
        content_hash: str,
        content: str,
    ) -> int:
        """Write FK-orphan text chunks.

        Idempotent: prior orphan chunks for the same content hash are
        cleared (along with their embeddings) before re-insertion.
        Returns the number of chunks written.
        """
        self.ensure_metadata(uri)
        db = self._connect

        old_ids = [
            r[0]
            for r in db.execute(
                "SELECT id FROM chunks WHERE content_hash = ? AND extraction_id IS NULL "
                "AND mode = 'metadata'",
                (content_hash,),
            ).fetchall()
        ]

        if old_ids:
            has_vec = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunks_vec'"
            ).fetchone()
            if has_vec:
                cp = ",".join("?" * len(old_ids))
                db.execute(f"DELETE FROM chunks_vec WHERE chunk_id IN ({cp})", old_ids)
            cp = ",".join("?" * len(old_ids))
            db.execute(f"DELETE FROM chunks WHERE id IN ({cp})", old_ids)

        self._put_chunks(None, uri, content_hash, "", "", content, mode="metadata")
        return int(
            db.execute(
                "SELECT COUNT(*) FROM chunks WHERE content_hash = ? AND extraction_id IS NULL "
                "AND mode = 'metadata'",
                (content_hash,),
            ).fetchone()[0]
        )

    def get_full_content(
        self,
        uri: str,
        content_hash: str,
        profile: str,
        model: str,
        *,
        mode: str = "accurate",
    ) -> str | None:
        """Reassemble full content for a given file/profile/model/mode from chunks."""
        rows = self._connect.execute(
            "SELECT chunk_text FROM chunks WHERE file_uri = ? AND content_hash = ? "
            "AND profile = ? AND model = ? AND mode = ? ORDER BY chunk_idx",
            (uri, content_hash, profile, model, mode),
        ).fetchall()
        if not rows:
            return None
        parts = [rows[0][0]]
        for r in rows[1:]:
            parts.append(r[0][CHUNK_OVERLAP:])
        return "".join(parts)

    # -- Embeddings --

    def _ensure_vec_table(self, dim: int) -> None:
        if not self._vec_available:
            return
        db = self._connect
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
        extraction_id: str | None = None,
        chunk_ids: list[int] | None = None,
        vectors: list[list[float]],
    ) -> None:
        """Pair *vectors* with chunk IDs and upsert into ``chunks_vec``."""
        if not vectors or not self._vec_available:
            return
        if extraction_id is None and chunk_ids is None:
            raise ValueError("pass exactly one of extraction_id or chunk_ids")

        import struct

        db = self._connect
        dim = len(vectors[0])
        self._ensure_vec_table(dim)

        if chunk_ids is None and extraction_id:
            chunks = self.get_chunks(extraction_id)
            chunk_ids = [c["id"] for c in chunks]

        if not chunk_ids:
            raise ValueError("chunk_ids couldn't be generated")

        n = min(len(vectors), len(chunk_ids))
        vec_inserts = [(chunk_ids[i], struct.pack(f"{dim}f", *vectors[i])) for i in range(n)]
        db.executemany(
            "INSERT OR REPLACE INTO chunks_vec (chunk_id, embedding) VALUES (?, ?)",
            vec_inserts,
        )
        db.commit()

    def search_chunks_fts(
        self,
        query: str,
        *,
        uri: str | None = None,
        uri_prefix: str | None = None,
        kind: str | None = None,
        ext: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Case-insensitive substring search over ``chunks.chunk_text``"""
        db = self._connect
        # Escape LIKE metacharacters in user input so 'user_id' and '100%' don't over-match
        q_esc = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        joins: list[str] = []
        where: list[str] = ["c.chunk_text LIKE ? ESCAPE '\\' COLLATE NOCASE"]
        params: list[Any] = [f"%{q_esc}%"]

        if uri:
            where.append("c.file_uri = ?")
            params.append(uri)
        elif uri_prefix:
            prefix_esc = uri_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where.append("c.file_uri LIKE ? ESCAPE '\\'")
            params.append(prefix_esc + "%")

        if kind:
            joins.append("JOIN files f ON f.uri = c.file_uri")
            kinds = [k.strip() for k in kind.split(",") if k.strip()]
            where.append(f"f.kind IN ({','.join('?' * len(kinds))})")
            params.extend(kinds)

        if ext:
            exts = [e.strip().lower() for e in ext.split(",") if e.strip()]
            if exts:
                where.append("(" + " OR ".join("LOWER(c.file_uri) LIKE ?" for _ in exts) + ")")
                params.extend(f"%{e}" for e in exts)

        sql = (
            "SELECT c.* FROM chunks c "
            + " ".join(joins)
            + " WHERE "
            + " AND ".join(where)
            + " LIMIT ?"
        )
        params.append(limit)
        return [dict(r) for r in db.execute(sql, params).fetchall()]

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
