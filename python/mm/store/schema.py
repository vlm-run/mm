"""Schema definitions for the mm SQLite database.

Relationships::
    files  1 ──→ N  l2_results  1 ──→ N  chunks

Usage::
    from mm.store.schema import FileCol, L2Col, ChunkCol
"""

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        pass


# ---------------------------------------------------------------------------
# Column name enums
# ---------------------------------------------------------------------------


class FileCol(StrEnum):
    """Column names for the ``files`` table (L0 + L1 unified)."""

    # L0 — always populated on scan
    URI = "uri"
    NAME = "name"
    STEM = "stem"
    EXT = "ext"
    SIZE = "size"
    MODIFIED = "modified"
    CREATED = "created"
    MIME = "mime"
    KIND = "kind"
    IS_BINARY = "is_binary"
    DEPTH = "depth"
    PARENT = "parent"
    WIDTH = "width"
    HEIGHT = "height"

    # L1 — nullable, filled on demand
    CONTENT_HASH = "content_hash"
    TEXT_PREVIEW = "text_preview"
    LINE_COUNT = "line_count"
    WORD_COUNT = "word_count"
    LANGUAGE = "language"
    DIMENSIONS = "dimensions"
    PAGES = "pages"
    DURATION_S = "duration_s"
    FPS = "fps"
    MAGIC_MIME = "magic_mime"
    EXIF_CAMERA = "exif_camera"
    EXIF_DATE = "exif_date"
    EXIF_GPS = "exif_gps"
    EXIF_ORIENTATION = "exif_orientation"
    VIDEO_CODEC = "video_codec"
    AUDIO_CODEC = "audio_codec"
    HAS_AUDIO = "has_audio"
    PHASH = "phash"

    # Tracking
    INDEXED_AT = "indexed_at"
    L1_INDEXED_AT = "l1_indexed_at"


class L2Col(StrEnum):
    """Column names for the ``l2_results`` table."""

    ID = "id"
    FILE_URI = "file_uri"
    CONTENT_HASH = "content_hash"
    PROFILE = "profile"
    MODEL = "model"
    MODE = "mode"
    DETAIL = "detail"
    EXTRA = "extra"
    SUMMARY = "summary"
    CREATED_AT = "created_at"


class ChunkCol(StrEnum):
    """Column names for the ``chunks`` table."""

    ID = "id"
    L2_RESULT_ID = "l2_result_id"
    FILE_URI = "file_uri"
    CONTENT_HASH = "content_hash"
    PROFILE = "profile"
    MODEL = "model"
    LEVEL = "level"
    CHUNK_IDX = "chunk_idx"
    CHUNK_TEXT = "chunk_text"
    EMBED_MODEL = "embed_model"
    CREATED_AT = "created_at"


# ---------------------------------------------------------------------------
# L0 column list (for upsert — only update these on re-scan)
# ---------------------------------------------------------------------------

L0_COLUMNS: tuple[str, ...] = (
    FileCol.URI,
    FileCol.NAME,
    FileCol.STEM,
    FileCol.EXT,
    FileCol.SIZE,
    FileCol.MODIFIED,
    FileCol.CREATED,
    FileCol.MIME,
    FileCol.KIND,
    FileCol.IS_BINARY,
    FileCol.DEPTH,
    FileCol.PARENT,
    FileCol.WIDTH,
    FileCol.HEIGHT,
    FileCol.INDEXED_AT,
)

# ---------------------------------------------------------------------------
# L1 column set (for selective preservation on L0 re-upsert)
# ---------------------------------------------------------------------------

L1_COLUMNS: frozenset[str] = frozenset(
    {
        FileCol.CONTENT_HASH,
        FileCol.TEXT_PREVIEW,
        FileCol.LINE_COUNT,
        FileCol.WORD_COUNT,
        FileCol.LANGUAGE,
        FileCol.DIMENSIONS,
        FileCol.PAGES,
        FileCol.DURATION_S,
        FileCol.FPS,
        FileCol.MAGIC_MIME,
        FileCol.EXIF_CAMERA,
        FileCol.EXIF_DATE,
        FileCol.EXIF_GPS,
        FileCol.EXIF_ORIENTATION,
        FileCol.VIDEO_CODEC,
        FileCol.AUDIO_CODEC,
        FileCol.HAS_AUDIO,
        FileCol.PHASH,
        FileCol.L1_INDEXED_AT,
    }
)

# ---------------------------------------------------------------------------
# SQLite DDL
# ---------------------------------------------------------------------------

FILES_DDL = """\
CREATE TABLE IF NOT EXISTS files (
    uri             TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    stem            TEXT NOT NULL,
    ext             TEXT NOT NULL,
    size            INTEGER NOT NULL,
    modified        INTEGER NOT NULL,
    created         INTEGER NOT NULL,
    mime            TEXT NOT NULL,
    kind            TEXT NOT NULL,
    is_binary       INTEGER NOT NULL,
    depth           INTEGER NOT NULL,
    parent          TEXT NOT NULL,
    width           INTEGER,
    height          INTEGER,
    content_hash    TEXT,
    text_preview    TEXT,
    line_count      INTEGER,
    word_count      INTEGER,
    language        TEXT,
    dimensions      TEXT,
    pages           INTEGER,
    duration_s      REAL,
    fps             REAL,
    magic_mime      TEXT,
    exif_camera     TEXT,
    exif_date       TEXT,
    exif_gps        TEXT,
    exif_orientation TEXT,
    video_codec     TEXT,
    audio_codec     TEXT,
    has_audio       INTEGER,
    phash           TEXT,
    indexed_at      INTEGER NOT NULL,
    l1_indexed_at   INTEGER
);
CREATE INDEX IF NOT EXISTS idx_files_kind ON files (kind);
CREATE INDEX IF NOT EXISTS idx_files_ext ON files (ext);
CREATE INDEX IF NOT EXISTS idx_files_content_hash ON files (content_hash);
CREATE INDEX IF NOT EXISTS idx_files_l1_lookup ON files (content_hash, l1_indexed_at DESC);
"""

L2_RESULTS_DDL = """\
CREATE TABLE IF NOT EXISTS l2_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_uri        TEXT NOT NULL REFERENCES files(uri),
    content_hash    TEXT NOT NULL,
    profile         TEXT NOT NULL,
    model           TEXT NOT NULL,
    mode            TEXT,
    detail          INTEGER NOT NULL,
    extra           TEXT NOT NULL DEFAULT '',
    summary         TEXT NOT NULL,
    created_at      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_l2_file_uri ON l2_results (file_uri);
CREATE INDEX IF NOT EXISTS idx_l2_lookup
ON l2_results (content_hash, profile, model, mode, detail, extra, created_at DESC);
"""

CHUNKS_DDL = """\
CREATE TABLE IF NOT EXISTS chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    l2_result_id    INTEGER NOT NULL REFERENCES l2_results(id),
    file_uri        TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    profile         TEXT NOT NULL,
    model           TEXT NOT NULL,
    level           INTEGER NOT NULL DEFAULT 2,
    chunk_idx       INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    embed_model     TEXT,
    created_at      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_l2_result_id ON chunks (l2_result_id);
CREATE INDEX IF NOT EXISTS idx_chunks_l2_reassembly
ON chunks (l2_result_id, level, chunk_idx);
CREATE INDEX IF NOT EXISTS idx_chunks_file_lookup
ON chunks (file_uri, content_hash, profile, model, level, chunk_idx);
"""

# ---------------------------------------------------------------------------
# Table names
# ---------------------------------------------------------------------------

FILES_TABLE = "files"
L2_RESULTS_TABLE = "l2_results"
CHUNKS_TABLE = "chunks"
