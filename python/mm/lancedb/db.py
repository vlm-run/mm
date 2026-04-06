"""LanceDB storage backend for mm.

Single global database at ~/.local/share/mm/mm.lance/ with three tables:
  - files:      L0 + L1 metadata (one row per file, uri = absolute path)
  - l2_results: LLM-generated summaries (many per file)
  - chunks:     Chunked L2 content + embeddings (many per L2 result)

Cache reads use a dbm sidecar (~0.2ms). Writes go to both dbm and LanceDB.
LanceDB import is deferred until first write/query — no cold-start penalty on reads.
"""

from __future__ import annotations

import datetime
import dbm
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import lancedb as ldb
    import pyarrow as pa


CHUNK_SIZE = 2048  # characters per chunk
CHUNK_OVERLAP = 100  # overlap on each side (200 total between adjacent chunks)

# ---------------------------------------------------------------------------
# Cache key builder
# ---------------------------------------------------------------------------


def make_key(
    content_hash: str,
    profile: str = "",
    model: str = "",
    mode: str | None = None,
    detail: bool = False,
    extra: str = "",
) -> str:
    """Deterministic cache key for L1 or L2 results."""
    return "cache:" + ":".join(
        filter(None, [content_hash, profile, model, mode, f"{detail}", extra])
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_us() -> int:
    return int(time.time() * 1_000_000)


def _esc(value: str) -> str:
    return value.replace("'", "''")


# ---------------------------------------------------------------------------
# MmDatabase
# ---------------------------------------------------------------------------


class MmDatabase:
    """Global LanceDB database for mm.

    The lancedb connection is lazy — not created until the first operation
    that actually needs it. Cache reads via dbm never touch lancedb.
    """

    DB_DIR = Path.home() / ".local" / "share" / "mm"
    DB_PATH = DB_DIR / "mm.lance"
    CACHE_PATH = DB_DIR / "cache.db"
    _cache_path = CACHE_PATH

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or self.DB_PATH
        self._cache_path = db_path.parent / "cache.db" if db_path else self.CACHE_PATH
        self._lance: ldb.DBConnection | None = None

    # -- dbm cache (fast path) --

    @classmethod
    def _cache_get(cls, key: str) -> str | None:
        try:
            with dbm.open(str(cls._cache_path), "r") as db:
                val = db.get(key)
                if val is not None:
                    return val.decode("utf-8")
        except Exception:
            pass
        return None

    def _cache_put(self, key: str, value: str) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        with dbm.open(str(self._cache_path), "c") as db:
            db[key] = value.encode("utf-8")

    # -- Lazy lancedb connection --

    def _connect(self) -> ldb.DBConnection:
        if self._lance is None:
            import lancedb

            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._lance = lancedb.connect(str(self._db_path))
        return self._lance

    def _files_table(self) -> ldb.table.Table:
        from mm.lancedb.schema import FILES_TABLE, files_schema

        db = self._connect()
        if FILES_TABLE not in db.table_names():
            return db.create_table(FILES_TABLE, schema=files_schema())
        return db.open_table(FILES_TABLE)

    def _l2_table(self) -> ldb.table.Table:
        from mm.lancedb.schema import L2_RESULTS_TABLE, l2_results_schema

        db = self._connect()
        if L2_RESULTS_TABLE not in db.table_names():
            return db.create_table(L2_RESULTS_TABLE, schema=l2_results_schema())
        return db.open_table(L2_RESULTS_TABLE)

    def _chunks_table(self) -> ldb.table.Table:
        from mm.lancedb.schema import CHUNKS_TABLE, chunks_schema

        db = self._connect()
        if CHUNKS_TABLE not in db.table_names():
            return db.create_table(CHUNKS_TABLE, schema=chunks_schema())
        return db.open_table(CHUNKS_TABLE)

    # -- Files (L0 + L1) --

    def upsert_files(self, scanner_table: pa.Table, root: Path) -> int:
        """Write L0 scan results. Converts relative paths to absolute URIs.
        Preserves existing L1 columns on re-upsert."""
        from mm.lancedb.schema import FileCol

        table = _to_absolute_table(scanner_table, root)
        table = _add_l1_nulls(table)

        ft = self._files_table()
        if ft.count_rows() == 0:
            ft.add(table)
        else:
            existing = ft.to_arrow()
            if existing.num_rows > 0:
                table = _preserve_l1(table, existing)
            ft.merge_insert(
                FileCol.URI
            ).when_matched_update_all().when_not_matched_insert_all().execute(table)
        return int(ft.count_rows())

    def update_l1(self, uri: str, data: dict[str, Any]) -> None:
        """Fill L1 columns for a specific file.
        Auto-creates a minimal L0 row from filesystem if the file isn't in the DB."""
        from mm.lancedb.schema import FileCol, files_schema

        existing = self.get_file(uri)
        if existing is None:
            existing = _l0_from_path(uri)
            if existing is None:
                return

        data[FileCol.L1_INDEXED_AT] = _now_us()

        row: dict[str, list] = {}
        schema = files_schema()
        for field in schema:
            if field.name in data:
                row[field.name] = [data[field.name]]
            else:
                row[field.name] = [existing.get(field.name)]

        import pyarrow as pa

        update_table = pa.table(row, schema=schema)
        ft = self._files_table()
        ft.merge_insert(
            FileCol.URI
        ).when_matched_update_all().when_not_matched_insert_all().execute(update_table)

    def get_file(self, uri: str) -> dict[str, Any] | None:
        from mm.lancedb.schema import FileCol

        ft = self._files_table()
        results = ft.search().where(f"{FileCol.URI} = '{_esc(uri)}'").limit(1).to_arrow()
        if results.num_rows == 0:
            return None
        return {col: results.column(col)[0].as_py() for col in results.column_names}

    def get_files(self, where: str | None = None) -> pa.Table:
        ft = self._files_table()
        q = ft.search()
        if where:
            q = q.where(where)
        return q.to_arrow()

    def is_stale(self, uri: str, mtime_us: int, size: int) -> bool:
        from mm.lancedb.schema import FileCol

        existing = self.get_file(uri)
        if existing is None:
            return True
        db_mtime = existing.get(FileCol.MODIFIED)
        db_size = existing.get(FileCol.SIZE)
        if db_mtime is None or db_size is None:
            return True
        if hasattr(db_mtime, "timestamp"):
            db_mtime_us = int(
                db_mtime.replace(tzinfo=datetime.timezone.utc).timestamp() * 1_000_000
            )
        else:
            db_mtime_us = int(db_mtime)
        return db_mtime_us != mtime_us or db_size != size

    # -- L1 (cache + lancedb) --

    def get_l1(self, content_hash: str) -> str | None:
        """Lookup cached L1 result from dbm."""
        return self._cache_get(make_key(content_hash))

    def put_l1(self, uri: str, content_hash: str, content: str) -> None:
        """Write to dbm cache + lancedb."""
        self._cache_put(make_key(content_hash), content)
        from mm.lancedb.schema import FileCol

        self.update_l1(uri, {FileCol.CONTENT_HASH: content_hash, FileCol.TEXT_PREVIEW: content})

    # -- L2 (cache + lancedb) --

    def get_l2(
        self,
        content_hash: str,
        profile: str,
        model: str,
        mode: str | None = None,
        detail: bool = False,
        extra: str = "",
    ) -> str | None:
        """Lookup cached L2 result from dbm."""
        return self._cache_get(make_key(content_hash, profile, model, mode, detail, extra))

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
        """Write to dbm cache + lancedb (summary + chunks)."""
        import pyarrow as pa

        from mm.lancedb.schema import L2Col, l2_results_schema

        self._cache_put(make_key(content_hash, profile, model, mode, detail, extra), content)

        now = _now_us()
        summary = content[:500] if len(content) > 500 else content
        l2_row = pa.table(
            {
                L2Col.URI: [uri],
                L2Col.CONTENT_HASH: [content_hash],
                L2Col.PROFILE: [profile],
                L2Col.MODEL: [model],
                L2Col.MODE: [mode],
                L2Col.DETAIL: [detail],
                L2Col.EXTRA: [extra],
                L2Col.SUMMARY: [summary],
                L2Col.CREATED_AT: pa.array([now], type=pa.timestamp("us")),
            },
            schema=l2_results_schema(),
        )
        self._l2_table().add(l2_row)
        self.put_chunks(uri, content_hash, profile, model, content)

    # -- Chunks --

    def put_chunks(
        self,
        uri: str,
        content_hash: str,
        profile: str,
        model: str,
        content: str,
    ) -> None:
        import pyarrow as pa

        from mm.lancedb.schema import ChunkCol, chunks_schema

        now = _now_us()
        step = CHUNK_SIZE - CHUNK_OVERLAP
        texts = []
        for i in range(0, len(content), step):
            texts.append(content[i : i + CHUNK_SIZE])
            if i + CHUNK_SIZE >= len(content):
                break
        if not texts:
            return
        chunk_table = pa.table(
            {
                ChunkCol.URI: [uri] * len(texts),
                ChunkCol.CONTENT_HASH: [content_hash] * len(texts),
                ChunkCol.PROFILE: [profile] * len(texts),
                ChunkCol.MODEL: [model] * len(texts),
                ChunkCol.CHUNK_IDX: list(range(len(texts))),
                ChunkCol.CHUNK_TEXT: texts,
                ChunkCol.EMBED_MODEL: [None] * len(texts),
                ChunkCol.CREATED_AT: pa.array([now] * len(texts), type=pa.timestamp("us")),
            },
            schema=chunks_schema(),
        )
        self._chunks_table().add(chunk_table)

    def get_full_content(self, uri: str, content_hash: str, profile: str, model: str) -> str | None:
        from mm.lancedb.schema import ChunkCol

        ct = self._chunks_table()
        where = (
            f"{ChunkCol.URI} = '{_esc(uri)}' "
            f"AND {ChunkCol.CONTENT_HASH} = '{_esc(content_hash)}' "
            f"AND {ChunkCol.PROFILE} = '{_esc(profile)}' "
            f"AND {ChunkCol.MODEL} = '{_esc(model)}'"
        )
        results = ct.search().where(where).to_arrow()
        if results.num_rows == 0:
            return None
        import pyarrow.compute as pc

        indices = pc.sort_indices(results.column(ChunkCol.CHUNK_IDX))
        sorted_results = results.take(indices)
        return "".join(
            sorted_results.column(ChunkCol.CHUNK_TEXT)[i].as_py()
            for i in range(sorted_results.num_rows)
        )

    # -- Embeddings --

    def upsert_embeddings(
        self,
        uri: str,
        content_hash: str,
        profile: str,
        model: str,
        embed_model: str,
        vectors: list[list[float]],
    ) -> None:
        import pyarrow as pa
        import pyarrow.compute as pc

        from mm.lancedb.schema import CHUNKS_TABLE, ChunkCol, chunks_schema

        ct = self._chunks_table()
        where = (
            f"{ChunkCol.URI} = '{_esc(uri)}' "
            f"AND {ChunkCol.CONTENT_HASH} = '{_esc(content_hash)}' "
            f"AND {ChunkCol.PROFILE} = '{_esc(profile)}' "
            f"AND {ChunkCol.MODEL} = '{_esc(model)}'"
        )
        results = ct.search().where(where).to_arrow()
        if results.num_rows == 0:
            return

        indices = pc.sort_indices(results.column(ChunkCol.CHUNK_IDX))
        sorted_results = results.take(indices)
        n = min(len(vectors), sorted_results.num_rows)

        rows: dict[str, list] = {}
        for col in sorted_results.column_names:
            rows[col] = [
                sorted_results.column(col)[i].as_py() for i in range(sorted_results.num_rows)
            ]
        for i in range(n):
            rows[ChunkCol.EMBED_MODEL][i] = embed_model

        dim = len(vectors[0]) if vectors else 0
        vec_col: list[list[float] | None] = [None] * sorted_results.num_rows
        for i in range(n):
            vec_col[i] = vectors[i]
        rows["vector"] = vec_col

        has_vector = "vector" in [f.name for f in ct.schema]
        ct.delete(where)

        if not has_vector:
            remaining = ct.to_arrow()
            self._connect().drop_table(CHUNKS_TABLE)
            fields = list(chunks_schema())
            fields.append(pa.field("vector", pa.list_(pa.float32(), dim), nullable=True))
            ct = self._connect().create_table(CHUNKS_TABLE, schema=pa.schema(fields))
            if remaining.num_rows > 0:
                null_vecs = pa.nulls(remaining.num_rows, type=pa.list_(pa.float32(), dim))
                remaining = remaining.append_column("vector", null_vecs)
                ct.add(remaining)

        update_table = pa.table(rows, schema=ct.schema)
        ct.add(update_table)

    def search_similar(
        self, vector: list[float], limit: int = 10, where: str | None = None
    ) -> pa.Table:
        import pyarrow as pa

        ct = self._chunks_table()
        if "vector" not in [f.name for f in ct.schema]:
            return pa.table({})
        q = ct.search(vector, vector_column_name="vector").limit(limit)
        if where:
            q = q.where(where)
        return q.to_arrow()

    # -- SQL --

    def sql(self, query: str, table_name: str = "files") -> pa.Table:
        import duckdb

        from mm.lancedb.schema import CHUNKS_TABLE, FILES_TABLE, L2_RESULTS_TABLE

        table_map = {
            FILES_TABLE: self._files_table,
            L2_RESULTS_TABLE: self._l2_table,
            CHUNKS_TABLE: self._chunks_table,
        }
        if table_name not in table_map:
            raise ValueError(f"Unknown table: {table_name}. Use one of: {list(table_map)}")
        arrow_table = table_map[table_name]().to_arrow()
        con = duckdb.connect()
        con.register(table_name, arrow_table)
        result = con.execute(query).fetch_arrow_table()
        con.close()
        return result

    # -- Index creation --

    def ensure_indexes(self) -> None:
        from mm.lancedb.schema import FileCol

        ft = self._files_table()
        for col in (FileCol.KIND, FileCol.EXT, FileCol.CONTENT_HASH):
            try:
                ft.create_scalar_index(col)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Arrow helpers (module-level, only imported when needed)
# ---------------------------------------------------------------------------


def _to_absolute_table(table: pa.Table, root: Path) -> pa.Table:
    import pyarrow as pa

    from mm.lancedb.schema import FileCol

    paths = table.column("path")
    uris = pa.array([str(root / p.as_py()) for p in paths], type=pa.string())
    parents = table.column("parent")
    abs_parents = pa.array(
        [str(root / p.as_py()) if p.as_py() else str(root) for p in parents],
        type=pa.string(),
    )

    columns: dict[str, pa.Array] = {FileCol.URI: uris}
    for field in table.schema:
        if field.name == "path":
            continue
        col = table.column(field.name)
        if field.name == "parent":
            columns[FileCol.PARENT] = abs_parents
        elif field.name == "phash":
            columns[FileCol.PHASH] = pa.array(
                [f"{v.as_py():016x}" if v.as_py() is not None else None for v in col],
                type=pa.string(),
            )
        elif field.type in (pa.uint16(), pa.uint32(), pa.uint64()):
            columns[field.name] = col.cast(pa.int64())
        else:
            columns[field.name] = col
    return pa.table(columns)


def _add_l1_nulls(table: pa.Table) -> pa.Table:
    import pyarrow as pa

    from mm.lancedb.schema import FileCol, files_schema

    schema = files_schema()
    for field in schema:
        if field.name not in table.column_names:
            if field.name == FileCol.INDEXED_AT:
                col = pa.array([_now_us()] * table.num_rows, type=pa.timestamp("us"))
            else:
                col = pa.nulls(table.num_rows, type=field.type)
            table = table.append_column(field.name, col)
    table = table.select([f.name for f in schema])
    return table.cast(schema)


def _preserve_l1(new_table: pa.Table, existing: pa.Table) -> pa.Table:
    import pyarrow as pa

    from mm.lancedb.schema import L1_COLUMNS, FileCol

    existing_uris = existing.column(FileCol.URI)
    uri_to_idx: dict[str, int] = {}
    for i in range(existing.num_rows):
        uri_to_idx[existing_uris[i].as_py()] = i

    new_uris = new_table.column(FileCol.URI)
    cols: dict[str, list] = {name: [] for name in new_table.column_names}

    for row_i in range(new_table.num_rows):
        uri = new_uris[row_i].as_py()
        existing_idx = uri_to_idx.get(uri)
        for col_name in new_table.column_names:
            new_val = new_table.column(col_name)[row_i].as_py()
            if col_name in L1_COLUMNS and new_val is None and existing_idx is not None:
                cols[col_name].append(existing.column(col_name)[existing_idx].as_py())
            else:
                cols[col_name].append(new_val)
    return pa.table(cols, schema=new_table.schema)


def _l0_from_path(uri: str) -> dict[str, Any] | None:
    from mm.lancedb.schema import FileCol

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
        FileCol.URI: uri,
        FileCol.NAME: p.name,
        FileCol.STEM: p.stem,
        FileCol.EXT: p.suffix,
        FileCol.SIZE: stat.st_size,
        FileCol.MODIFIED: int(stat.st_mtime * 1_000_000),
        FileCol.CREATED: int(getattr(stat, "st_birthtime", stat.st_ctime) * 1_000_000),
        FileCol.MIME: mime,
        FileCol.KIND: "other",
        FileCol.IS_BINARY: False,
        FileCol.DEPTH: 0,
        FileCol.PARENT: str(p.parent),
        FileCol.WIDTH: None,
        FileCol.HEIGHT: None,
        FileCol.INDEXED_AT: _now_us(),
    }
