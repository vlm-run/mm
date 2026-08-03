"""Type stubs for the Rust _mm module."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from pyarrow import Table

class Scanner:
    """High-performance file scanner powered by Rust."""

    def __init__(
        self,
        root: str,
        n_threads: int | None = None,
        *,
        no_ignore: bool = False,
    ) -> None: ...
    def scan(self) -> int: ...
    def num_files(self) -> int: ...
    def to_arrow(self) -> Table: ...
    def write_parquet(self, path: str) -> None: ...
    def to_json(self) -> str: ...
    def to_markdown(self) -> str: ...
    def to_csv(self) -> str: ...
    def to_tsv(self) -> str: ...
    def to_lines(self) -> str: ...
    def to_json_fast(
        self,
        kind: str | None = None,
        ext: str | None = None,
        min_size: int | None = None,
        max_size: int | None = None,
        name: str | None = None,
        limit: int | None = None,
        sort_by: str | None = None,
        descending: bool = False,
    ) -> str: ...
    def to_lines_fast(
        self,
        kind: str | None = None,
        ext: str | None = None,
        min_size: int | None = None,
        max_size: int | None = None,
        name: str | None = None,
        limit: int | None = None,
        sort_by: str | None = None,
        descending: bool = False,
    ) -> str: ...
    def extract_metadata(self, path: str) -> MetadataResult: ...
    def wc(self, kind: str | None = None) -> str: ...

class MetadataResult:
    """Locally-extracted file metadata (dimensions, EXIF, codecs, hash, …)."""

    content_hash: str | None
    text_preview: str | None
    line_count: int | None
    word_count: int | None
    language: str | None
    dimensions: str | None
    pages: int | None
    duration_s: float | None
    magic_mime: str | None
    exif_camera: str | None
    exif_date: str | None
    exif_gps: str | None
    exif_orientation: str | None
    video_codec: str | None
    audio_codec: str | None
    fps: float | None
    has_audio: bool | None
    phash: int | None

def hamming_distance(a: int, b: int) -> int:
    """Hamming distance between two perceptual hashes (0 = identical, <8 = near-duplicate)."""
    ...

def content_hash(path: str) -> str | None:
    """Fast xxh3 content hash of a file via mmap. Returns 16-char hex string."""
    ...

def extract_metadata_one(path: str | Path) -> MetadataResult:
    """Extract metadata for a single file by absolute path, without scanning its parent directory."""
    ...

def directory_hash(path: str) -> str | None:
    """Hash a directory listing (sorted name:mtime:size). Returns 16-char hex string."""
    ...

def perceptual_hash(path: str) -> int | None:
    """Perceptual hash (pHash) of an image file. Returns 64-bit hash."""
    ...

# Serde: image resize/tile + Gemini Part serialization

def resize_image(path: str, max_width: int, quality: int = 85) -> dict[str, object]:
    """Resize image to max_width (Lanczos3), return {base64, mime, width, height}.

    Args:
        path: Filesystem path to the source image.
        max_width: Maximum output width in pixels.
        quality: JPEG quality 1-100 (default 85, ignored for PNG).
    """
    ...

def tile_image(path: str, tile_size: int, quality: int = 85) -> list[dict[str, object]]:
    """Tile image into squares, return list of tile dicts.

    Args:
        path: Filesystem path to the source image.
        tile_size: Maximum tile dimension in pixels.
        quality: JPEG quality 1-100 (default 85, ignored for PNG).
    """
    ...

def gemini_image_part(path: str) -> str:
    """Serialize image as Gemini inline_data Part JSON string."""
    ...

def gemini_video_parts(path: str, max_seconds: int = 120, overlap: int = 10) -> list[str]:
    """Serialize video as Gemini inline_data Part JSON strings."""
    ...

def gemini_document_part(path: str) -> str:
    """Serialize document as Gemini inline_data Part JSON string."""
    ...

class OfficeMetadata:
    """Office document metadata extracted via libreoffice-pure."""

    author: str
    title: str
    subject: str
    description: str
    keywords: list[str]
    created: str
    modified: str
    pages: int | None

class OfficeDoc:
    """Office document content + metadata extracted via libreoffice-pure."""

    content: str
    meta: OfficeMetadata

def office_content(path: str) -> str:
    """Extract just the content of a docx/doc/odt/pdf/xlsx/ods/pptx/odp file."""
    ...

def office_metadata(path: str) -> OfficeMetadata:
    """Extract just the metadata of a docx/doc/odt/pdf/xlsx/ods/pptx/odp file."""
    ...

def office_parse_full(path: str) -> OfficeDoc:
    """Parse a docx/doc/odt/pdf/xlsx/ods/pptx/odp file and return content + metadata."""
    ...

def office_to_pdf(input: str, output: str) -> str:
    """Convert a supported office document to PDF; return the output path."""
    ...

# Incremental multimodal context (Rust-backed Context core)

class PyContext:
    """Rust-core incremental context. Do not instantiate directly — use
    :class:`mm.Context` which wraps this."""

    session_id: str

    def __init__(self, session_id: str | None = None) -> None: ...
    def __len__(self) -> int: ...
    def num_items(self) -> int: ...
    def add(
        self,
        role: str,
        kind: str,
        source_kind: str,
        source_value: str,
        byte_len: int | None = None,
        desc: str | None = None,
        py_obj: object | None = None,
        metadata_json: str | None = None,
    ) -> str: ...
    def remove(self, ref_id: str) -> None: ...
    def get(self, ref_id: str) -> object: ...
    def item(self, ref_id: str) -> dict[str, object]: ...
    def items(self) -> list[dict[str, object]]: ...
    def ref_ids(self) -> list[str]: ...
    def contains(self, ref_id: str) -> bool: ...
    def repr_markdown(self) -> str: ...
    def render_tree_insertion(self) -> str: ...
    def to_md_table(self, contents: dict[str, str]) -> str: ...
    def ref_not_found_message(self, ref_id: str) -> str: ...
    def __repr__(self) -> str: ...

class RefNotFoundError(KeyError):
    """Raised by :meth:`PyContext.get` on miss. Subclass of KeyError."""

def make_ref_id(kind: str) -> str:
    """Generate a random ``<prefix>_<6 hex>`` ref id for ``kind``."""
    ...

def uuid7_py() -> str:
    """Generate a UUIDv7 (time-ordered; hyphenated canonical form)."""
    ...

def kind_for_name(name: str) -> str:
    """Infer the mm kind for a conventional file name (by extension)."""
    ...
