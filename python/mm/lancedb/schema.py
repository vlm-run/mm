"""Schema definitions for the mm LanceDB tables.

Relationships::

    files  1 ──→ N  l2_results  1 ──→ N  chunks

SQL DDL (reference — LanceDB uses Arrow schemas, not SQL)::

    ──────────────────────────────────────────────────────────────
    -- Table: files
    -- One row per file. L0 columns are always populated on scan.
    -- L1 columns are nullable, filled lazily on demand.
    ──────────────────────────────────────────────────────────────
    CREATE TABLE files (
        -- L0: filesystem metadata (populated on scan)
        uri             TEXT        NOT NULL PRIMARY KEY,   -- absolute path
        name            TEXT        NOT NULL,               -- filename with ext
        stem            TEXT        NOT NULL,               -- filename without ext
        ext             TEXT        NOT NULL,               -- extension incl. dot
        size            BIGINT      NOT NULL,               -- bytes
        modified        TIMESTAMP   NOT NULL,               -- last modified (μs)
        created         TIMESTAMP   NOT NULL,               -- created (μs)
        mime            TEXT        NOT NULL,               -- MIME type
        kind            TEXT        NOT NULL,               -- image|video|document|code|audio|data|config|text|other
        is_binary       BOOLEAN     NOT NULL,
        depth           BIGINT      NOT NULL,               -- nesting from scan root
        parent          TEXT        NOT NULL,               -- parent dir (absolute)
        width           BIGINT,                             -- image/video width px
        height          BIGINT,                             -- image/video height px

        -- L1: content extraction (filled on demand)
        content_hash    TEXT,                               -- xxh3 hex (lineage key)
        text_preview    TEXT,                               -- first 500 chars
        line_count      BIGINT,
        word_count      BIGINT,
        language        TEXT,                               -- detected language
        dimensions      TEXT,                               -- "WxH" formatted
        pages           BIGINT,                             -- document page count
        duration_s      DOUBLE,                             -- audio/video seconds
        fps             DOUBLE,
        magic_mime      TEXT,                               -- MIME from magic bytes
        exif_camera     TEXT,
        exif_date       TEXT,
        exif_gps        TEXT,                               -- "lat,lon"
        exif_orientation TEXT,
        video_codec     TEXT,
        audio_codec     TEXT,
        has_audio       BOOLEAN,
        phash           TEXT,                               -- perceptual hash hex

        -- Tracking
        indexed_at      TIMESTAMP   NOT NULL,               -- last L0 scan time
        l1_indexed_at   TIMESTAMP                           -- last L1 extraction time
    );
    CREATE INDEX idx_files_kind         ON files (kind);
    CREATE INDEX idx_files_ext          ON files (ext);
    CREATE INDEX idx_files_content_hash ON files (content_hash);

    ──────────────────────────────────────────────────────────────
    -- Table: l2_results
    -- LLM-generated summaries. Many per file (one per
    -- profile × model × mode × detail × extra combination).
    ──────────────────────────────────────────────────────────────
    CREATE TABLE l2_results (
        uri             TEXT        NOT NULL REFERENCES files(uri),
        content_hash    TEXT        NOT NULL,               -- file hash at extraction time
        profile         TEXT        NOT NULL,               -- LLM profile name
        model           TEXT        NOT NULL,               -- model identifier
        mode            TEXT,                               -- fast|accurate|NULL
        detail          BOOLEAN     NOT NULL,
        extra           TEXT        NOT NULL DEFAULT '',     -- video mosaic params etc.
        summary         TEXT        NOT NULL,               -- first 500 chars preview
        created_at      TIMESTAMP   NOT NULL
    );

    ──────────────────────────────────────────────────────────────
    -- Table: chunks
    -- Full L2 content split into ~1024-char chunks.
    -- Each chunk can carry an embedding vector.
    -- Full content = SELECT chunk_text FROM chunks
    --                WHERE uri = ? AND content_hash = ?
    --                  AND profile = ? AND model = ?
    --                ORDER BY chunk_idx;
    ──────────────────────────────────────────────────────────────
    CREATE TABLE chunks (
        uri             TEXT        NOT NULL REFERENCES files(uri),
        content_hash    TEXT        NOT NULL,               -- FK → l2_results
        profile         TEXT        NOT NULL,               -- FK → l2_results
        model           TEXT        NOT NULL,               -- FK → l2_results
        chunk_idx       BIGINT      NOT NULL,               -- 0-based position
        chunk_text      TEXT        NOT NULL,               -- ~1024-char slice
        embed_model     TEXT,                               -- embedding model name
        created_at      TIMESTAMP   NOT NULL
        -- vector       FLOAT[]     (added dynamically on first embedding)
    );

Usage::

    from mm.lancedb.schema import FileCol, L2Col, ChunkCol
    table.column(FileCol.URI)
"""

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        pass


import pyarrow as pa


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

    URI = "uri"
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

    URI = "uri"
    CONTENT_HASH = "content_hash"
    PROFILE = "profile"
    MODEL = "model"
    CHUNK_IDX = "chunk_idx"
    CHUNK_TEXT = "chunk_text"
    EMBED_MODEL = "embed_model"
    CREATED_AT = "created_at"
    # ``vector`` column is added dynamically on first embedding


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
# Arrow schemas
# ---------------------------------------------------------------------------


def files_schema() -> pa.Schema:
    """Arrow schema for the ``files`` table (L0 + L1 unified)."""
    return pa.schema(
        [
            # L0
            pa.field(FileCol.URI, pa.string(), nullable=False),
            pa.field(FileCol.NAME, pa.string(), nullable=False),
            pa.field(FileCol.STEM, pa.string(), nullable=False),
            pa.field(FileCol.EXT, pa.string(), nullable=False),
            pa.field(FileCol.SIZE, pa.int64(), nullable=False),
            pa.field(FileCol.MODIFIED, pa.timestamp("us"), nullable=False),
            pa.field(FileCol.CREATED, pa.timestamp("us"), nullable=False),
            pa.field(FileCol.MIME, pa.string(), nullable=False),
            pa.field(FileCol.KIND, pa.string(), nullable=False),
            pa.field(FileCol.IS_BINARY, pa.bool_(), nullable=False),
            pa.field(FileCol.DEPTH, pa.int64(), nullable=False),
            pa.field(FileCol.PARENT, pa.string(), nullable=False),
            pa.field(FileCol.WIDTH, pa.int64(), nullable=True),
            pa.field(FileCol.HEIGHT, pa.int64(), nullable=True),
            # L1
            pa.field(FileCol.CONTENT_HASH, pa.string(), nullable=True),
            pa.field(FileCol.TEXT_PREVIEW, pa.string(), nullable=True),
            pa.field(FileCol.LINE_COUNT, pa.int64(), nullable=True),
            pa.field(FileCol.WORD_COUNT, pa.int64(), nullable=True),
            pa.field(FileCol.LANGUAGE, pa.string(), nullable=True),
            pa.field(FileCol.DIMENSIONS, pa.string(), nullable=True),
            pa.field(FileCol.PAGES, pa.int64(), nullable=True),
            pa.field(FileCol.DURATION_S, pa.float64(), nullable=True),
            pa.field(FileCol.FPS, pa.float64(), nullable=True),
            pa.field(FileCol.MAGIC_MIME, pa.string(), nullable=True),
            pa.field(FileCol.EXIF_CAMERA, pa.string(), nullable=True),
            pa.field(FileCol.EXIF_DATE, pa.string(), nullable=True),
            pa.field(FileCol.EXIF_GPS, pa.string(), nullable=True),
            pa.field(FileCol.EXIF_ORIENTATION, pa.string(), nullable=True),
            pa.field(FileCol.VIDEO_CODEC, pa.string(), nullable=True),
            pa.field(FileCol.AUDIO_CODEC, pa.string(), nullable=True),
            pa.field(FileCol.HAS_AUDIO, pa.bool_(), nullable=True),
            pa.field(FileCol.PHASH, pa.string(), nullable=True),
            # Tracking
            pa.field(FileCol.INDEXED_AT, pa.timestamp("us"), nullable=False),
            pa.field(FileCol.L1_INDEXED_AT, pa.timestamp("us"), nullable=True),
        ]
    )


def l2_results_schema() -> pa.Schema:
    """Arrow schema for the ``l2_results`` table."""
    return pa.schema(
        [
            pa.field(L2Col.URI, pa.string(), nullable=False),
            pa.field(L2Col.CONTENT_HASH, pa.string(), nullable=False),
            pa.field(L2Col.PROFILE, pa.string(), nullable=False),
            pa.field(L2Col.MODEL, pa.string(), nullable=False),
            pa.field(L2Col.MODE, pa.string(), nullable=True),
            pa.field(L2Col.DETAIL, pa.bool_(), nullable=False),
            pa.field(L2Col.EXTRA, pa.string(), nullable=False),
            pa.field(L2Col.SUMMARY, pa.string(), nullable=False),
            pa.field(L2Col.CREATED_AT, pa.timestamp("us"), nullable=False),
        ]
    )


def chunks_schema() -> pa.Schema:
    """Arrow schema for the ``chunks`` table.

    The ``vector`` column is not included here — it is added dynamically
    when embeddings are first stored, since its dimensionality depends on
    the embedding model.
    """
    return pa.schema(
        [
            pa.field(ChunkCol.URI, pa.string(), nullable=False),
            pa.field(ChunkCol.CONTENT_HASH, pa.string(), nullable=False),
            pa.field(ChunkCol.PROFILE, pa.string(), nullable=False),
            pa.field(ChunkCol.MODEL, pa.string(), nullable=False),
            pa.field(ChunkCol.CHUNK_IDX, pa.int64(), nullable=False),
            pa.field(ChunkCol.CHUNK_TEXT, pa.string(), nullable=False),
            pa.field(ChunkCol.EMBED_MODEL, pa.string(), nullable=True),
            pa.field(ChunkCol.CREATED_AT, pa.timestamp("us"), nullable=False),
        ]
    )


# ---------------------------------------------------------------------------
# Table names
# ---------------------------------------------------------------------------

FILES_TABLE = "files"
L2_RESULTS_TABLE = "l2_results"
CHUNKS_TABLE = "chunks"
