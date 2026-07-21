"""Micro-benchmark for DB write paths affected by PRAGMA NORMAL + transaction batching.

Measures:
1. put_extraction (was 3 commits, now 1 transaction)
2. put_text_chunks (was 1 commit via _put_chunks, now 1 via `with db:`)
3. upsert_files fill_metadata loop (was 1 trailing commit, now 1 transaction)
"""

import tempfile
import time
from pathlib import Path

from mm.store.db import MmDatabase
from mm.store.schema import FileCol


def _seed_files(db: MmDatabase, files: list[Path]) -> list[tuple[str, str]]:
    """Seed files with content_hash + text_preview. Returns [(uri, hash), ...]."""
    entries = []
    for i, p in enumerate(files):
        uri = str(p.resolve())
        content_hash = f"hash_{i:08x}"
        db.ensure_metadata(uri)
        db.put_file_content(
            uri,
            {
                FileCol.CONTENT_HASH: content_hash,
                FileCol.TEXT_PREVIEW: f"Content for file {i}. " * 100,
            },
        )
        entries.append((uri, content_hash))
    return entries


def bench_put_extraction(n: int = 50) -> float:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        files = []
        for i in range(n):
            p = root / f"file_{i:04d}.txt"
            p.write_text(f"content {i}")
            files.append(p)

        db = MmDatabase(db_path=root / "test.db")
        entries = _seed_files(db, files)

        t0 = time.perf_counter()
        for uri, content_hash in entries:
            db.put_extraction(
                uri=uri,
                content_hash=content_hash,
                profile="default",
                model="test-model",
                content="Extraction result. " * 50,
                mode="fast",
                detail=False,
                extra="",
            )
        return time.perf_counter() - t0


def bench_put_text_chunks(n: int = 50) -> float:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        files = []
        for i in range(n):
            p = root / f"text_{i:04d}.txt"
            p.write_text(f"content {i}")
            files.append(p)

        db = MmDatabase(db_path=root / "test.db")
        entries = _seed_files(db, files)

        t0 = time.perf_counter()
        for uri, content_hash in entries:
            db.put_text_chunks(
                uri=uri,
                content_hash=content_hash,
                content="Text content. " * 80,
            )
        return time.perf_counter() - t0


def bench_upsert_files(n: int = 100) -> float:
    from mm._mm import Scanner

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        for i in range(n):
            (root / f"file_{i:04d}.txt").write_text(f"content {i}")

        db = MmDatabase(db_path=root / "test.db")
        scanner = Scanner(str(root))
        scanner.scan()
        table = scanner.to_arrow()

        t0 = time.perf_counter()
        db.upsert_files(table, root, scanner=scanner)
        return time.perf_counter() - t0


if __name__ == "__main__":
    print("=== DB write micro-benchmark (with PRAGMA NORMAL + transaction batching) ===\n")

    bench_put_extraction(n=5)  # warm up

    for label, func, n in [
        ("put_extraction (50 files)", bench_put_extraction, 50),
        ("put_text_chunks (50 files)", bench_put_text_chunks, 50),
        ("upsert_files (100 files)", bench_upsert_files, 100),
    ]:
        times = []
        for _ in range(5):
            t = func(n=n)
            times.append(t)
        median = sorted(times)[len(times) // 2]
        print(f"{label}:")
        print(f"  runs:   {['%.2fms' % (t * 1000) for t in times]}")
        print(f"  median: {median * 1000:.2f}ms")
        print()
