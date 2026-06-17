"""mm storage — SQLite + sqlite-vec database for files, extractions, and embeddings."""

__all__ = ["list_tables"]


def list_tables() -> list[dict[str, str]]:
    """Describe the queryable tables in the default store.

    Thin convenience over :meth:`mm.store.db.MmDatabase.list_tables` for
    callers that don't hold a database handle.
    """
    from mm.store.db import MmDatabase

    return MmDatabase().list_tables()


def __getattr__(name: str):
    if name == "MmDatabase":
        from mm.store.db import MmDatabase

        return MmDatabase

    if name in {
        "FileCol",
        "ExtractionCol",
        "ChunkCol",
        "FILES_TABLE",
        "EXTRACTIONS_TABLE",
        "CHUNKS_TABLE",
    }:
        from mm.store import schema

        return getattr(schema, name)

    raise AttributeError(f"module 'mm.store' has no attribute {name!r}")
