"""mm storage — SQLite + sqlite-vec database for file metadata, L2 results, and embeddings."""

__all__ = []


def __getattr__(name: str):
    if name == "MmDatabase":
        from mm.store.db import MmDatabase

        return MmDatabase

    if name in {
        "FileCol",
        "L2Col",
        "ChunkCol",
        "FILES_TABLE",
        "L2_RESULTS_TABLE",
        "CHUNKS_TABLE",
    }:
        from mm.store import schema

        return getattr(schema, name)

    raise AttributeError(f"module 'mm.store' has no attribute {name!r}")
