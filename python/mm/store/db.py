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
        from mm.store.schema import CHUNKS_DDL, FILES_DDL, L2_RESULTS_DDL

        self._connect.executescript(FILES_DDL + L2_RESULTS_DDL + CHUNKS_DDL)

    # -- Files (L0 + L1) --

    def upsert_files(self, scanner_table: pa.Table, root: Path) -> int:
        """Write L0 scan results. Preserves existing L1 columns on re-upsert."""
        from mm.store.schema import L0_COLUMNS

        n = scanner_table.num_rows
        if n == 0:
            return int(self._connect.execute("SELECT COUNT(*) FROM files").fetchone()[0])

        db = self._connect
        now = _now_us()
        # Build SQL once
        columns = "uri, name, stem, ext, size, modified, created, mime, kind, is_binary, depth, parent, width, height, phash, indexed_at"
        placeholders = ", ".join("?" * 16)
        l0_updates = ", ".join(f"{c} = excluded.{c}" for c in L0_COLUMNS if c != "uri")
        sql = (
            f"INSERT INTO files ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT(uri) DO UPDATE SET {l0_updates}"
        )

        # Columnar conversion — one Arrow call, no per-row dict allocation
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

        rows = [
            (
                f"{root_s}/{paths[i]}",
                names[i] or "",
                stems[i] or "",
                exts[i] or "",
                sizes[i] or 0,
                _to_us(modifieds[i]),
                _to_us(createds[i]),
                mimes[i] or "",
                kinds[i] or "other",
                int(bool(is_binarys[i])),
                depths[i] or 0,
                f"{root_s}/{parents[i]}" if parents[i] else root_s,
                widths[i],
                heights[i],
                f"{phashes[i]:016x}" if phashes[i] is not None else None,
                now,
            )
            for i in range(n)
        ]

        db.executemany(sql, rows)
        db.commit()
        return int(db.execute("SELECT COUNT(*) FROM files").fetchone()[0])

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

        data[FileCol.L1_INDEXED_AT] = _now_us()
        sets = ", ".join(f"{k} = ?" for k in data)
        self._connect.execute(f"UPDATE files SET {sets} WHERE uri = ?", (*data.values(), uri))
        self._connect.commit()

    def put_l1(self, uri: str, content_hash: str, content: str) -> None:
        from mm.store.schema import FileCol

        self.update_l1(uri, {FileCol.CONTENT_HASH: content_hash, FileCol.TEXT_PREVIEW: content})

    # -- L2 --

    def get_l2(
        self,
        content_hash: str,
        profile: str,
        model: str,
        mode: str | None = None,
        detail: bool = False,
        extra: str = "",
    ) -> str | None:
        """Look up a cached L2 result. Returns full content reassembled from chunks."""
        row = self._connect.execute(
            "SELECT id FROM l2_results "
            "WHERE content_hash = ? AND profile = ? AND model = ? "
            "AND mode IS ? AND detail = ? AND extra = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (content_hash, profile, model, mode, int(detail), extra),
        ).fetchone()
        if row is None:
            return None
        l2_id = row[0]
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
    ) -> int:
        """Insert L2 result, chunk L1+L2 content. Returns l2_results.id."""
        self.ensure_l0(uri)

        # Get L1 content
        l1_content = self.get_l1(content_hash)
        if not l1_content:
            raise RuntimeError("L1 content not found")

        now = _now_us()
        summary = content[:500] if len(content) > 500 else content
        cursor = self._connect.execute(
            "INSERT INTO l2_results (file_uri, content_hash, profile, model, mode, detail, extra, summary, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (uri, content_hash, profile, model, mode, int(detail), extra, summary, now),
        )
        assert cursor.lastrowid is not None
        l2_id: int = cursor.lastrowid
        self._connect.commit()

        # Chunk L1 (the raw extracted content the LLM saw) and L2 (the LLM-generated summary/description)
        self._put_chunks(l2_id, uri, content_hash, profile, model, l1_content, level=1)
        self._put_chunks(l2_id, uri, content_hash, profile, model, content, level=2)
        return l2_id

    # -- Chunks --

    def _put_chunks(
        self,
        l2_result_id: int,
        uri: str,
        content_hash: str,
        profile: str,
        model: str,
        content: str,
        level: int,
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
            "INSERT INTO chunks (l2_result_id, uri, content_hash, profile, model, level, chunk_idx, chunk_text, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (l2_result_id, uri, content_hash, profile, model, level, idx, text, now)
                for idx, text in enumerate(texts)
            ],
        )
        db.commit()

    def get_chunks(
        self, uri: str, content_hash: str, profile: str, model: str, *, level: int | None = None
    ) -> list[dict[str, Any]]:
        q = "SELECT * FROM chunks WHERE uri = ? AND content_hash = ? AND profile = ? AND model = ?"
        params: list = [uri, content_hash, profile, model]
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
            "SELECT chunk_text FROM chunks WHERE uri = ? AND content_hash = ? "
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

        import struct

        db = self._connect
        dim = len(vectors[0])
        self._ensure_vec_table(dim)

        chunks = self.get_chunks(uri, content_hash, profile, model)
        n = min(len(vectors), len(chunks))

        chunk_updates = []
        vec_inserts = []
        for i in range(n):
            chunk_id = chunks[i]["id"]
            chunk_updates.append((embed_model, chunk_id))
            vec_inserts.append((chunk_id, struct.pack(f"{dim}f", *vectors[i])))

        db.executemany("UPDATE chunks SET embed_model = ? WHERE id = ?", chunk_updates)
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
