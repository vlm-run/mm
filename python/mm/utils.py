from __future__ import annotations

import sys
import time as _time
from enum import Enum
from pathlib import Path
from typing import Callable, ParamSpec, TypeVar

from mm.constants import (
    AUDIO_EXTS,
    CODE_EXTS,
    DOCUMENT_EXTS,
    IMAGE_EXTS,
    VIDEO_EXTS,
    FileKind,
)

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


def expand_path_arg(path: Path | str, *, no_ignore: bool = False) -> list[Path]:
    """Expand a single CLI path argument into the file list it represents.

    Files are returned as a one-element list. Directories are walked
    recursively via the Rust ``Scanner`` (gitignore-aware by default; pass
    ``no_ignore=True`` to include ignored entries) and the resulting paths
    are returned sorted by their relative path within the directory so the
    output is deterministic across runs.

    Returned paths are always absolute (``Path.resolve()`` applied) so the
    helper has a single, predictable contract regardless of whether the
    caller passed a file or a directory. This is what lets the de-dup
    logic in :func:`expand_path_args` and :mod:`mm.commands.cat` use the
    string form as a reliable set key.

    Args:
        path: A filesystem path. May be a file or a directory.
        no_ignore: When True, bypass ``.gitignore`` while walking
            directories. Has no effect on file inputs.

    Returns:
        Ordered list of resolved ``Path`` objects. Empty if ``path`` is a
        directory with no scannable files.

    Raises:
        FileNotFoundError: If ``path`` does not exist on disk.
    """
    import json as _json

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    if p.is_file():
        return [p.resolve()]

    from mm._mm import Scanner

    root = p.resolve()
    scanner = Scanner(str(root), None, no_ignore=no_ignore)
    scanner.scan()
    rows = _json.loads(scanner.to_json_fast(sort_by="path"))
    return [root / row["path"] for row in rows]


def expand_path_args(
    paths: list[Path] | list[str],
    *,
    no_ignore: bool = False,
) -> list[Path]:
    """Expand a list of CLI path arguments, flattening directories into files.

    Equivalent to calling :func:`expand_path_arg` on each entry and
    concatenating the results, with duplicates removed while preserving
    first-seen order.

    Args:
        paths: Mix of file and directory paths.
        no_ignore: Forwarded to :func:`expand_path_arg`.

    Returns:
        De-duplicated, order-preserving list of file ``Path`` objects.

    Raises:
        FileNotFoundError: If any entry does not exist.
    """
    seen: set[str] = set()
    out: list[Path] = []
    for entry in paths:
        for f in expand_path_arg(entry, no_ignore=no_ignore):
            key = str(f)
            if key in seen:
                continue
            seen.add(key)
            out.append(f)
    return out


def is_binary_content(*, kind: str, content: str | None = None) -> bool:
    """Heuristic to determine if content is binary based on kind and content."""
    return kind in ("image", "document", "video", "audio") or bool(
        content and "\x00" in content[:512]
    )
