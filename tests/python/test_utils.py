from pathlib import Path

import pyarrow as pa
from mm.store import MmDatabase
from mm.store.util import get_content_hash

ROOT = Path("/test/data")


def get_hash(path: Path | str) -> str:
    return get_content_hash(Path(path)) or "hash1"


def scanner_table(
    paths: list[str],
    kinds: list[str] | None = None,
) -> pa.Table:
    """Build a minimal scanner-like Arrow table with relative paths."""
    n = len(paths)
    if kinds is None:
        kinds = ["text"] * n
    return pa.table(
        {
            "path": paths,
            "name": [p.split("/")[-1] for p in paths],
            "stem": [p.split("/")[-1].rsplit(".", 1)[0] for p in paths],
            "ext": ["." + p.split(".")[-1] if "." in p else "" for p in paths],
            "size": pa.array([100] * n, type=pa.uint64()),
            "modified": pa.array([1712000000000000] * n, type=pa.timestamp("us")),
            "created": pa.array([1712000000000000] * n, type=pa.timestamp("us")),
            "mime": ["text/plain"] * n,
            "kind": kinds,
            "is_binary": [False] * n,
            "depth": pa.array([0] * n, type=pa.uint16()),
            "parent": [""] * n,
            "width": pa.array([None] * n, type=pa.uint32()),
            "height": pa.array([None] * n, type=pa.uint32()),
        }
    )


def ensure_l0(
    db: MmDatabase,
    uris: list[str],
    kinds: list[str] | None = None,
) -> int:
    return db.upsert_files(scanner_table([Path(uri).name for uri in uris], kinds), ROOT)


def ensure_l1(
    db: MmDatabase,
    uri: str,
    l1_content="L1 content",
    *,
    l0_kinds: list[str] | None = None,
) -> None:
    """Helper to ensure L1 content exists for a file."""
    ensure_l0(db, [uri], l0_kinds)
    db.put_l1(uri, get_hash(uri), l1_content)
