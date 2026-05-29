"""Canonical file-type constants for mm.

This module is the single source of truth for file extensions, MIME types,
and media-kind literals used across the CLI, serde strategies, LLM backend,
and storage layer.  Import from here instead of defining local copies.
"""

from __future__ import annotations

from typing import Literal

# -- Media kind type ---------------------------------------------------------

BinaryFileKind = Literal["image", "video", "audio", "document"]
FileKind = Literal["text"] | BinaryFileKind


# -- Extension sets ----------------------------------------------------------

IMAGE_EXTS: frozenset[str] = frozenset(
    (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif", ".svg", ".heif", ".heic")
)

VIDEO_EXTS: frozenset[str] = frozenset(
    (
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".wmv",
        ".flv",
        ".webm",
        ".m4v",
        ".mpg",
        ".mpeg",
        ".3gp",
        ".ogv",
    )
)

AUDIO_EXTS: frozenset[str] = frozenset(
    (
        ".mp3",
        ".wav",
        ".flac",
        ".aac",
        ".ogg",
        ".m4a",
        ".wma",
        ".opus",
    )
)

OFFICE_EXTS: frozenset[str] = frozenset((".docx", ".odt", ".pptx", ".odp", ".xlsx", ".ods"))
DOCUMENT_EXTS: frozenset[str] = frozenset((".pdf", ".doc", *OFFICE_EXTS))
CODE_EXTS: frozenset[str] = frozenset(
    (
        ".py",
        ".rs",
        ".js",
        ".ts",
        ".go",
        ".c",
        ".cpp",
        ".h",
        ".java",
        ".rb",
        ".sh",
        ".toml",
        ".yaml",
        ".yml",
    )
)


# -- Extension → MIME mapping ------------------------------------------------

EXT_TO_MIME: dict[str, str] = {
    # Images
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    # Video
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
    ".wmv": "video/x-ms-wmv",
    ".flv": "video/x-flv",
    ".m4v": "video/x-m4v",
    ".mpg": "video/mpeg",
    ".mpeg": "video/mpeg",
    ".3gp": "video/3gpp",
    ".ogv": "video/ogg",
    # Audio
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".wma": "audio/x-ms-wma",
    ".opus": "audio/opus",
    # Documents
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def guess_mime(path_or_ext: str, *, fallback: str = "application/octet-stream") -> str:
    """Return the MIME type for a file path or bare extension.

    Args:
        path_or_ext: A filename, full path, or dotted extension (e.g. ".png").
        fallback: Returned when the extension is not recognised.

    Returns:
        MIME string such as ``"image/jpeg"``.
    """
    from pathlib import PurePosixPath

    ext = PurePosixPath(path_or_ext).suffix.lower()
    if not ext and path_or_ext.startswith("."):
        ext = path_or_ext.lower()
    return EXT_TO_MIME.get(ext, fallback)
