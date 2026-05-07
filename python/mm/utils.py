from __future__ import annotations

import sys
import time as _time
from enum import Enum
from pathlib import Path
from typing import Callable, Literal, ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


class BaseFormat(str, Enum):
    rich = "rich"
    json = "json"
    pretty_json = "pretty-json"
    tsv = "tsv"
    csv = "csv"
    stdout = "stdout"


class Format(str, Enum):
    rich = "rich"
    json = "json"
    pretty_json = "pretty-json"
    tsv = "tsv"
    csv = "csv"
    dataset_jsonl = "dataset-jsonl"
    dataset_hf = "dataset-hf"


def get_elapsed_ms(
    callback: Callable[P, T],
    *args: P.args,
    **kwargs: P.kwargs,
) -> tuple[T, float]:
    """Run callback and return (result, elapsed_ms)."""
    _t0 = _time.perf_counter()
    result = callback(*args, **kwargs)
    elapsed_ms = (_time.perf_counter() - _t0) * 1000

    return result, elapsed_ms


def benchmark_func(
    callback: Callable[P, T],
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Run callback and return (result, elapsed_ms)."""
    name = getattr(callback, "__name__", repr(callback))
    print(f"Benchmarking function: {name}", file=sys.stderr)
    result, elapsed_ms = get_elapsed_ms(callback, *args, **kwargs)
    print(f"Execution time for {name}: {elapsed_ms:.2f} ms", file=sys.stderr)

    return result


def batch_array(arr: list[T], x: int) -> list[list[T]]:
    if x <= 0:
        raise ValueError("x must be greater than 0")
    return [arr[i : i + x] for i in range(0, len(arr), x)]


# ---------------------------------------------------------------------------
# Piped-input helper
# ---------------------------------------------------------------------------

IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".svg"})
VIDEO_EXTS = frozenset(
    {
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
    }
)
AUDIO_EXTS = frozenset({".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus"})
DOCUMENT_EXTS = frozenset({".pdf", ".docx", ".doc", ".odt", ".pptx", ".odp", ".xlsx", ".ods"})
CODE_EXTS = frozenset(
    {
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
    }
)

BinaryFileKind = Literal["image", "video", "audio", "document"]
FileKind = Literal["text"] | BinaryFileKind


def file_kind(path: Path | str) -> FileKind:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in DOCUMENT_EXTS:
        return "document"
    return "text"


def file_kind_with_code(path: Path) -> str:
    kind = file_kind(path)
    if kind != "text":
        return kind
    if path.suffix.lower() in CODE_EXTS:
        return "code"
    return "text"


def is_binary_content(*, kind: str, content: str | None = None) -> bool:
    """Heuristic to determine if content is binary based on kind and content."""
    return kind in ("image", "document", "video", "audio") or bool(
        content and "\x00" in content[:512]
    )
