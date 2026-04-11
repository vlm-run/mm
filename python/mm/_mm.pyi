"""Type stubs for the Rust _mm module."""

from __future__ import annotations

import pyarrow as pa

class Scanner:
    """High-performance file scanner powered by Rust."""

    def __init__(self, root: str, n_threads: int | None = None) -> None: ...
    def scan(self) -> int: ...
    def num_files(self) -> int: ...
    def to_arrow(self) -> pa.Table: ...
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
    def extract_l1(self, path: str) -> L1Result: ...
    def wc(self, kind: str | None = None) -> str: ...

class L1Result:
    """Result of L1 content extraction."""

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

def directory_hash(path: str) -> str | None:
    """Hash a directory listing (sorted name:mtime:size). Returns 16-char hex string."""
    ...

def perceptual_hash(path: str) -> int | None:
    """Perceptual hash (pHash) of an image file. Returns 64-bit hash."""
    ...

# Serde: image resize/tile + Gemini Part serialization

def resize_image(path: str, max_width: int) -> dict[str, object]:
    """Resize image to max_width (Lanczos3), return {base64, mime, width, height}."""
    ...

def tile_image(path: str, tile_size: int) -> list[dict[str, object]]:
    """Tile image into squares, return list of {base64, mime, col, row, total_cols, total_rows, width, height}."""
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
