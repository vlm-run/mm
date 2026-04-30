#!/usr/bin/env python3
"""Download FineVision-vlmbench-mini images for the universal CLI bench.

Fetches the single parquet shard from the public HF dataset
``vlm-run/FineVision-vlmbench-mini``, decodes each row's embedded image bytes,
and writes individual image files to ``benchmarks/data/universal-bench/images/``.

That directory is gitignored, so each teammate runs this once. A ``.ready``
sentinel + image count check makes the script idempotent — re-runs return
immediately.

Usage:
    uv run python benchmarks/universal_cli/download_finevision_images.py

No new dependencies: uses stdlib ``urllib`` + ``pyarrow`` + ``Pillow``
(already core deps).
"""

from __future__ import annotations

import sys
import urllib.request
from io import BytesIO
from pathlib import Path

PARQUET_URL = (
    "https://huggingface.co/datasets/vlm-run/FineVision-vlmbench-mini/"
    "resolve/main/data/train-00000-of-00001.parquet"
)
BENCH_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = BENCH_ROOT / "data" / "universal-bench" / "images"
SENTINEL = OUT_DIR / ".ready"
PARQUET_CACHE = OUT_DIR / ".source.parquet"


def _size_mb(n_bytes: int) -> str:
    return f"{n_bytes / 1e6:.1f} MB"


def _reporthook(chunk_num: int, chunk_size: int, total: int) -> None:
    if total <= 0:
        return
    downloaded = min(chunk_num * chunk_size, total)
    pct = 100 * downloaded / total
    sys.stdout.write(f"\r  downloading: {pct:5.1f}% ({_size_mb(downloaded)})")
    sys.stdout.flush()


def _list_images() -> list[Path]:
    return sorted(p for p in OUT_DIR.iterdir() if p.is_file() and not p.name.startswith("."))


def download_parquet() -> Path:
    """Download the parquet shard unless already cached locally."""
    if PARQUET_CACHE.exists() and PARQUET_CACHE.stat().st_size > 0:
        print(f"  parquet cached: {PARQUET_CACHE.name} ({_size_mb(PARQUET_CACHE.stat().st_size)})")
        return PARQUET_CACHE
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  fetching {PARQUET_URL}")
    tmp = PARQUET_CACHE.with_suffix(".parquet.part")
    urllib.request.urlretrieve(PARQUET_URL, tmp, reporthook=_reporthook)
    tmp.rename(PARQUET_CACHE)
    print()
    return PARQUET_CACHE


def extract_images(parquet_path: Path) -> int:
    """Decode each row's ``images`` list and write files. Returns count."""
    try:
        import pyarrow.parquet as pq
    except ImportError:
        sys.exit("Error: pyarrow required. Run: uv pip install -e '.[dev]'")
    try:
        from PIL import Image
    except ImportError:
        sys.exit("Error: Pillow required. Run: uv pip install -e '.[dev]'")

    table = pq.read_table(parquet_path)
    if "images" not in table.column_names:
        sys.exit(f"Error: parquet has no 'images' column (schema: {table.schema.names})")
    images_col = table.column("images").to_pylist()

    count = 0
    for row_idx, image_list in enumerate(images_col):
        if not image_list:
            continue
        for img_idx, entry in enumerate(image_list):
            img_bytes = None
            if isinstance(entry, dict):
                img_bytes = entry.get("bytes")
            elif isinstance(entry, (bytes, bytearray)):
                img_bytes = bytes(entry)
            if not img_bytes:
                continue
            try:
                with Image.open(BytesIO(img_bytes)) as im:
                    fmt = (im.format or "PNG").lower()
                    ext = "jpg" if fmt == "jpeg" else fmt
                    out_path = OUT_DIR / f"{row_idx:04d}_{img_idx:02d}.{ext}"
                    if out_path.exists() and out_path.stat().st_size > 0:
                        count += 1
                        continue
                    im.save(out_path)
                    count += 1
            except Exception as exc:
                print(f"  warn: row {row_idx} img {img_idx}: {exc}", file=sys.stderr)
    return count


def main() -> None:
    if SENTINEL.exists():
        existing = _list_images()
        print(f"Already prepared: {len(existing)} images in {OUT_DIR}")
        return

    print(f"Preparing FineVision-vlmbench-mini → {OUT_DIR}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    parquet_path = download_parquet()
    count = extract_images(parquet_path)

    total_size = sum(p.stat().st_size for p in _list_images())
    SENTINEL.write_text(f"count={count}\nbytes={total_size}\n")
    print(f"  extracted {count} images ({_size_mb(total_size)})")

    try:
        PARQUET_CACHE.unlink()
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    main()
