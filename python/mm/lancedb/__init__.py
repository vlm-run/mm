"""mm LanceDB integration — global database for file metadata, L2 results, and embeddings."""

__all__ = []


def __getattr__(name: str):
    if name == "MmDatabase":
        from mm.lancedb.db import MmDatabase

        return MmDatabase

    if name in {
        "FileCol",
        "L2Col",
        "ChunkCol",
        "FILES_TABLE",
        "L2_RESULTS_TABLE",
        "CHUNKS_TABLE",
        "files_schema",
        "l2_results_schema",
        "chunks_schema",
    }:
        from mm.lancedb import schema

        return getattr(schema, name)

    raise AttributeError(f"module 'mm.lancedb' has no attribute {name!r}")
