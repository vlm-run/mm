"""Schema definitions for the mm SQLite database.

Relationships::
    files  1 ──→ N  extractions  1 ──→ N  chunks

Three content tiers carry through the schema:

  ``metadata`` — locally-extracted file content (``files.text_preview``);
                 never invokes an LLM. Image dimensions, PDF text, video codec
                 metadata, audio transcript via Whisper, etc. all land here.
  ``fast``     — output of a fast-mode pipeline run. *May* invoke an LLM with
                 a short prompt (e.g. ``image/fast.yaml`` does).
  ``accurate`` — output of an accurate-mode pipeline run. LLM-heavy.

  - ``extractions.mode``  ∈ {fast, accurate} — which pipeline produced this row
  - ``chunks.mode``       ∈ {metadata, fast, accurate} — which content tier
                            this chunk belongs to

Usage::
    from mm.store.schema import FileCol, ExtractionCol, ChunkCol
"""

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        pass


class FileCol(StrEnum):
    """Column names for the ``files`` table (metadata + locally extracted content)."""

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

    # Local content extraction — nullable, filled on demand
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

    # Session / global addressing
    SESSION_ID = "session_id"
    REF_ID = "ref_id"

    # Tracking
    INDEXED_AT = "indexed_at"
    CONTENT_INDEXED_AT = "content_indexed_at"


class ExtractionCol(StrEnum):
    """Column names for the ``extractions`` table."""

    ID = "id"
    FILE_URI = "file_uri"
    CONTENT_HASH = "content_hash"
    PROFILE = "profile"
    MODEL = "model"
    MODE = "mode"
    DETAIL = "detail"
    EXTRA = "extra"
    SUMMARY = "summary"
    METADATA = "metadata"
    CREATED_AT = "created_at"


class ChunkCol(StrEnum):
    """Column names for the ``chunks`` table."""

    ID = "id"
    EXTRACTION_ID = "extraction_id"
    FILE_URI = "file_uri"
    CONTENT_HASH = "content_hash"
    PROFILE = "profile"
    MODEL = "model"
    MODE = "mode"
    CHUNK_IDX = "chunk_idx"
    CHUNK_TEXT = "chunk_text"
    CREATED_AT = "created_at"


METADATA_COLUMNS: tuple[str, ...] = (
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

CONTENT_COLUMNS: frozenset[str] = frozenset(
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
        FileCol.CONTENT_INDEXED_AT,
    }
)

FILES_DDL = """\
CREATE TABLE IF NOT EXISTS files (
    uri                 TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    stem                TEXT NOT NULL,
    ext                 TEXT NOT NULL,
    size                INTEGER NOT NULL,
    modified            INTEGER NOT NULL,
    created             INTEGER NOT NULL,
    mime                TEXT NOT NULL,
    kind                TEXT NOT NULL,
    is_binary           INTEGER NOT NULL,
    depth               INTEGER NOT NULL,
    parent              TEXT NOT NULL,
    width               INTEGER,
    height              INTEGER,
    content_hash        TEXT,
    text_preview        TEXT,
    line_count          INTEGER,
    word_count          INTEGER,
    language            TEXT,
    dimensions          TEXT,
    pages               INTEGER,
    duration_s          REAL,
    fps                 REAL,
    magic_mime          TEXT,
    exif_camera         TEXT,
    exif_date           TEXT,
    exif_gps            TEXT,
    exif_orientation    TEXT,
    video_codec         TEXT,
    audio_codec         TEXT,
    has_audio           INTEGER,
    phash               TEXT,
    session_id          TEXT,
    ref_id              TEXT,
    indexed_at          INTEGER NOT NULL,
    content_indexed_at  INTEGER
);
"""

FILES_INDEX_DDL = """\
CREATE INDEX IF NOT EXISTS idx_files_kind ON files (kind);
CREATE INDEX IF NOT EXISTS idx_files_ext ON files (ext);
CREATE INDEX IF NOT EXISTS idx_files_content_hash ON files (content_hash);
CREATE INDEX IF NOT EXISTS idx_files_content_lookup ON files (content_hash, content_indexed_at DESC);
CREATE INDEX IF NOT EXISTS idx_files_session_ref ON files (session_id, ref_id);
CREATE INDEX IF NOT EXISTS idx_files_session ON files (session_id);
"""

# FILES_MIGRATIONS — idempotent ALTER TABLE statements applied at connection
# time. Each entry is (column_name, ddl). The DDL is only executed when
# column_name is missing from PRAGMA table_info(files). This keeps the
# migration safe to re-run on existing user databases without an Alembic-style
# migration framework.
FILES_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("session_id", "ALTER TABLE files ADD COLUMN session_id TEXT"),
    ("ref_id", "ALTER TABLE files ADD COLUMN ref_id TEXT"),
)

EXTRACTIONS_DDL = """\
CREATE TABLE IF NOT EXISTS extractions (
    id           TEXT PRIMARY KEY,
    file_uri     TEXT NOT NULL REFERENCES files(uri) ON DELETE CASCADE,
    content_hash TEXT NOT NULL,
    profile      TEXT NOT NULL,
    model        TEXT NOT NULL,
    mode         TEXT NOT NULL CHECK (mode IN ('fast', 'accurate')),
    detail       INTEGER NOT NULL,
    extra        TEXT NOT NULL DEFAULT '',
    summary      TEXT NOT NULL,
    metadata     TEXT,
    created_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_extractions_file_uri ON extractions (file_uri);
"""

CHUNKS_DDL = """\
CREATE TABLE IF NOT EXISTS chunks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    extraction_id TEXT REFERENCES extractions(id) ON DELETE CASCADE,
    file_uri      TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    profile       TEXT NOT NULL,
    model         TEXT NOT NULL,
    mode          TEXT NOT NULL DEFAULT 'metadata' CHECK (mode IN ('metadata', 'fast', 'accurate')),
    chunk_idx     INTEGER NOT NULL,
    chunk_text    TEXT NOT NULL,
    created_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_extraction_id ON chunks (extraction_id);
CREATE INDEX IF NOT EXISTS idx_chunks_reassembly
ON chunks (extraction_id, mode, chunk_idx);
CREATE INDEX IF NOT EXISTS idx_chunks_file_lookup
ON chunks (file_uri, content_hash, profile, model, mode, chunk_idx);
"""

FILES_TABLE = "files"
EXTRACTIONS_TABLE = "extractions"
CHUNKS_TABLE = "chunks"
