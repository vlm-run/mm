"""SQLite + sqlite-vec storage backend for mm.

Single global database at ~/.local/share/mm/mm.db with tables:
  - files:      L0 + L1 metadata (one row per file, uri = absolute path)
  - l2_results: LLM-generated summaries (many per file)
  - chunks:     Chunked L2 content + embeddings (many per L2 result)
  - cache:      Key-value cache for L1/L2 results
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pyarrow as pa

CHUNK_SIZE = 2048
CHUNK_OVERLAP = 100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_us() -> int:
    return int(time.time() * 1_000_000)


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


def make_key(
    content_hash: str,
    profile: str = "",
    model: str = "",
    mode: str | None = None,
    detail: bool = False,
    extra: str = "",
) -> str:
    return "cache:" + ":".join(
        filter(None, [content_hash, profile, model, mode, f"{detail}", extra])
    )


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

    @property
    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            import sqlite_vec

            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.enable_load_extension(True)
            sqlite_vec.load(self._conn)
            self._conn.enable_load_extension(False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._ensure_tables()
        return self._conn

    def _ensure_tables(self) -> None:
        from mm.store.schema import CACHE_DDL, CHUNKS_DDL, FILES_DDL, L2_RESULTS_DDL

        self._connect.executescript(FILES_DDL + L2_RESULTS_DDL + CHUNKS_DDL + CACHE_DDL)

    # -- Cache (replaces dbm) --

    def cache_get(self, key: str) -> str | None:
        row = self._connect.execute("SELECT value FROM cache WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def cache_put(self, key: str, value: str) -> None:
        self._connect.execute(
            "INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)", (key, value)
        )
        self._connect.commit()

    # -- Files (L0 + L1) --

    def upsert_files(self, scanner_table: pa.Table, root: Path) -> int:
        """Write L0 scan results. Preserves existing L1 columns on re-upsert."""
        from mm.store.schema import L0_COLUMNS

        db = self._connect
        now = _now_us()
        col_names = scanner_table.column_names

        for i in range(scanner_table.num_rows):
            row = {c: scanner_table.column(c)[i].as_py() for c in col_names}
            uri = str(root / row.pop("path"))
            parent = str(root / row["parent"]) if row.get("parent") else str(root)
            phash = f"{row['phash']:016x}" if row.get("phash") is not None else None

            # Convert timestamps: Arrow gives datetime objects, we store μs integers
            modified = _to_us(row.get("modified"))
            created = _to_us(row.get("created"))

            vals = {
                "uri": uri,
                "name": row.get("name", ""),
                "stem": row.get("stem", ""),
                "ext": row.get("ext", ""),
                "size": row.get("size", 0),
                "modified": modified,
                "created": created,
                "mime": row.get("mime", ""),
                "kind": row.get("kind", "other"),
                "is_binary": int(bool(row.get("is_binary", False))),
                "depth": row.get("depth", 0),
                "parent": parent,
                "width": row.get("width"),
                "height": row.get("height"),
                "indexed_at": now,
            }

            if phash is not None:
                vals["phash"] = phash

            # ON CONFLICT: update L0 columns, preserve L1 columns
            l0_updates = ", ".join(f"{c} = excluded.{c}" for c in L0_COLUMNS if c != "uri")
            columns = ", ".join(vals.keys())
            placeholders = ", ".join("?" * len(vals))
            db.execute(
                f"INSERT INTO files ({columns}) VALUES ({placeholders}) "
                f"ON CONFLICT(uri) DO UPDATE SET {l0_updates}",
                tuple(vals.values()),
            )
        db.commit()
        return db.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    def update_l1(self, uri: str, data: dict[str, Any]) -> None:
        """Fill L1 columns for a specific file."""
        from mm.store.schema import FileCol

        db = self._connect
        existing = self.get_file(uri)
        if existing is None:
            row = _l0_from_path(uri)
            if row is None:
                return
            cols = ", ".join(row.keys())
            placeholders = ", ".join("?" * len(row))
            db.execute(
                f"INSERT OR IGNORE INTO files ({cols}) VALUES ({placeholders})", tuple(row.values())
            )

        data[FileCol.L1_INDEXED_AT] = _now_us()
        sets = ", ".join(f"{k} = ?" for k in data)
        db.execute(f"UPDATE files SET {sets} WHERE uri = ?", (*data.values(), uri))
        db.commit()

    def get_file(self, uri: str) -> dict[str, Any] | None:
        row = self._connect.execute("SELECT * FROM files WHERE uri = ?", (uri,)).fetchone()
        return dict(row) if row else None

    def get_files(self, where: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM files"
        if where:
            q += f" WHERE {where}"
        return [dict(r) for r in self._connect.execute(q).fetchall()]

    def is_stale(self, uri: str, mtime_us: int, size: int) -> bool:
        row = self._connect.execute(
            "SELECT modified, size FROM files WHERE uri = ?", (uri,)
        ).fetchone()
        if row is None:
            return True
        return row[0] != mtime_us or row[1] != size

    # -- L1 (cache) --

    def get_l1(self, content_hash: str) -> str | None:
        return self.cache_get(make_key(content_hash))

    def put_l1(self, uri: str, content_hash: str, content: str) -> None:
        from mm.store.schema import FileCol

        self.cache_put(make_key(content_hash), content)
        self.update_l1(uri, {FileCol.CONTENT_HASH: content_hash, FileCol.TEXT_PREVIEW: content})

    # -- L2 (cache + l2_results + chunks) --

    def get_l2(
        self,
        content_hash: str,
        profile: str,
        model: str,
        mode: str | None = None,
        detail: bool = False,
        extra: str = "",
    ) -> str | None:
        return self.cache_get(make_key(content_hash, profile, model, mode, detail, extra))

    def put_l2(
        self,
        uri: str,
        content_hash: str,
        profile: str,
        model: str,
        content: str,
        mode: str | None = None,
        detail: bool = False,
        *,
        extra: str = "",
    ) -> None:
        self.cache_put(make_key(content_hash, profile, model, mode, detail, extra), content)
        now = _now_us()
        summary = content[:500] if len(content) > 500 else content
        self._connect.execute(
            "INSERT INTO l2_results (uri, content_hash, profile, model, mode, detail, extra, summary, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (uri, content_hash, profile, model, mode, int(detail), extra, summary, now),
        )
        self._connect.commit()
        self.put_chunks(uri, content_hash, profile, model, content)

    # -- Chunks --

    def put_chunks(
        self, uri: str, content_hash: str, profile: str, model: str, content: str
    ) -> None:
        now = _now_us()
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
            "INSERT INTO chunks (uri, content_hash, profile, model, chunk_idx, chunk_text, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(uri, content_hash, profile, model, idx, text, now) for idx, text in enumerate(texts)],
        )
        db.commit()

    def get_chunks(
        self, uri: str, content_hash: str, profile: str, model: str
    ) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self._connect.execute(
                "SELECT * FROM chunks WHERE uri = ? AND content_hash = ? "
                "AND profile = ? AND model = ? ORDER BY chunk_idx",
                (uri, content_hash, profile, model),
            ).fetchall()
        ]

    def get_full_content(self, uri: str, content_hash: str, profile: str, model: str) -> str | None:
        rows = self._connect.execute(
            "SELECT chunk_text FROM chunks WHERE uri = ? AND content_hash = ? "
            "AND profile = ? AND model = ? ORDER BY chunk_idx",
            (uri, content_hash, profile, model),
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
        uri: str,
        content_hash: str,
        profile: str,
        model: str,
        embed_model: str,
        vectors: list[list[float]],
    ) -> None:
        if not vectors:
            return

        db = self._connect
        dim = len(vectors[0])
        self._ensure_vec_table(dim)

        chunks = self.get_chunks(uri, content_hash, profile, model)
        n = min(len(vectors), len(chunks))

        for i in range(n):
            chunk_id = chunks[i]["id"]
            db.execute(
                "UPDATE chunks SET embed_model = ? WHERE id = ?",
                (embed_model, chunk_id),
            )
            # Upsert into vec table
            import struct

            vec_bytes = struct.pack(f"{dim}f", *vectors[i])
            db.execute(
                "INSERT OR REPLACE INTO chunks_vec (chunk_id, embedding) VALUES (?, ?)",
                (chunk_id, vec_bytes),
            )
        db.commit()

    def search_similar(
        self, vector: list[float], limit: int = 10, where: str | None = None
    ) -> list[dict[str, Any]]:
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


def _l0_from_path(uri: str) -> dict[str, Any] | None:
    p = Path(uri)
    if not p.exists():
        return None
    try:
        stat = p.stat()
    except OSError:
        return None

    mime = "application/octet-stream"
    try:
        import mimetypes

        mime = mimetypes.guess_type(p.name)[0] or mime
    except Exception:
        pass

    return {
        "uri": uri,
        "name": p.name,
        "stem": p.stem,
        "ext": p.suffix,
        "size": stat.st_size,
        "modified": int(stat.st_mtime * 1_000_000),
        "created": int(getattr(stat, "st_birthtime", stat.st_ctime) * 1_000_000),
        "mime": mime,
        "kind": "other",
        "is_binary": 0,
        "depth": 0,
        "parent": str(p.parent),
        "width": None,
        "height": None,
        "indexed_at": _now_us(),
    }
