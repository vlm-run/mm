import struct
import zlib
from pathlib import Path

import pyarrow as pa
from mm.store import MmDatabase
from mm.store.schema import FileCol
from mm.store.utils import get_content_hash

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


def ensure_metadata(
    db: MmDatabase,
    uris: list[str],
    kinds: list[str] | None = None,
) -> int:
    return db.upsert_files(scanner_table([Path(uri).name for uri in uris], kinds), ROOT)


def ensure_fast(
    db: MmDatabase,
    uri: str,
    fast_content="fast content",
    *,
    metadata_kinds: list[str] | None = None,
) -> None:
    """Ensure fast (locally extracted) content exists for a file."""
    ensure_metadata(db, [uri], metadata_kinds)
    db.put_file_content(
        uri,
        {
            FileCol.CONTENT_HASH: get_hash(uri),
            FileCol.TEXT_PREVIEW: fast_content,
        },
    )


def write_png(path: Path, width: int, height: int):
    """Create a valid PNG by constructing the binary format directly."""
    raw = b""
    for _ in range(height):
        raw += b"\x00" + b"\x80\x00\x40" * width
    compressed = zlib.compress(raw)

    def _chunk(ctype, data):
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", ihdr_data)
    png += _chunk(b"IDAT", compressed)
    png += _chunk(b"IEND", b"")
    path.write_bytes(png)


def write_minimal_mp4(path: Path) -> None:
    """Encode a 1-frame, 16x16 mp4 PyAV can probe.

    The previous ``b"\\x00" * 200`` placeholder relied on ffprobe being
    forgiving; the new PyAV-based ``mm.video.probe`` is stricter, so the
    fixture must be a real (tiny) mp4 file.
    """
    import av
    import numpy as np

    container = av.open(str(path), mode="w")
    try:
        stream = container.add_stream("mpeg4", rate=24)
        stream.width = 16
        stream.height = 16
        stream.pix_fmt = "yuv420p"
        frame = av.VideoFrame.from_ndarray(
            np.zeros((16, 16, 3), dtype=np.uint8),
            format="rgb24",
        )
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    finally:
        container.close()
