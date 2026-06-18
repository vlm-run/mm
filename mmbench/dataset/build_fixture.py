"""Build the mmbench-agent fixture: a nested, multimodal directory at scale.

Assembled only from the three sanctioned, reproducible sources:

  - mmbench-tiny  (https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-tiny.tar.gz)
  - mmbench-mini  (https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-mini.tar.gz)
  - FineVision-vlmbench-mini images (decoded from the HF parquet by
    benchmarks/bench_universal/helpers/download_finevision_images.py)

The tree is built for *difficult* agent tasks: a deep PDF (15-page paper),
invoices, financial-document images, six floor plans (plus confusers), two
videos, a talk audio, and ~150 photos for scale (so reading every file is too
slow for the baseline). Every file is given an **opaque** name so retrieval and
organization require reading content, not filename matching. ``manifest.json``
records the source->dest mapping and ground-truth labels for case authoring and
review.

Cases pin a *subtree* (e.g. ``mmbench-agent/Documents``) as their dataset so the
per-run sandbox only copies what the task needs.

Usage:
    uv run python mmbench/dataset/build_fixture.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "benchmarks" / "data"
FIXTURE = DATA_ROOT / "mmbench-agent"
# The manifest carries ground-truth labels, so it lives OUTSIDE the fixture dir
# (a sandbox copy of the tree must never leak answers to the agent).
MANIFEST_PATH = DATA_ROOT / "mmbench-agent.manifest.json"

TINY_URL = "https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-tiny.tar.gz"
MINI_URL = "https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-mini.tar.gz"
FINEVISION_HELPER = (
    REPO_ROOT / "benchmarks" / "bench_universal" / "helpers" / "download_finevision_images.py"
)
FINEVISION_IMAGES = DATA_ROOT / "mmbench-universal" / "images"

NUM_DISTRACTORS = 150

# Known-content files: (source relative to data/, dest relative to fixture/, label).
MANIFEST: list[tuple[str, str, str]] = [
    # Downloads/ loose files (organization + triage tasks operate here).
    ("mmbench-mini/images/car.jpg", "Downloads/IMG_2231.jpg", "car"),
    ("mmbench-mini/images/dogs.jpg", "Downloads/IMG_2232.jpg", "dogs"),
    ("mmbench-mini/images/airplanes.png", "Downloads/IMG_2233.png", "airplanes"),
    ("mmbench-tiny/cats.jpg", "Downloads/IMG_2234.jpg", "cats"),
    ("mmbench-mini/images/invoice-1.jpg", "Downloads/IMG_2235.jpg", "invoice-image"),
    ("mmbench-tiny/how_to_build_an_mvp.mp3", "Downloads/rec_0042.mp3", "audio"),
    # The one usable video (the keynote source is corrupt; audio has no speech).
    ("mmbench-tiny/bakery.mp4", "Media/clip_bakery.mp4", "video"),
    # Invoice PDF with known total (artifact + retrieval ground truth).
    ("mmbench-tiny/invoice.pdf", "Downloads/invoices/scan_4471.pdf", "invoice"),
    # Deep PDF: 15-page research paper (deep-PDF QA target).
    (
        "mmbench-tiny/attention-is-all-you-need.pdf",
        "Documents/papers/paper_attn.pdf",
        "research-paper",
    ),
    # Floor plans (6) + 2 confusers (retrieval / classification target).
    ("mmbench-mini/images/floorplan.png", "Documents/plans/DSC_0501.png", "floor-plan"),
    ("mmbench-mini/images/floor-plan-dimensions.png", "Documents/plans/DSC_0502.png", "floor-plan"),
    ("mmbench-mini/images/Sample_Floorplan.jpg", "Documents/plans/DSC_0503.jpg", "floor-plan"),
    (
        "mmbench-mini/images/2-story-residential-house-plan.avif",
        "Documents/plans/DSC_0504.avif",
        "floor-plan",
    ),
    ("mmbench-mini/images/construction-plan-1.jpg", "Documents/plans/DSC_0505.jpg", "floor-plan"),
    ("mmbench-mini/images/floor-plan.gif", "Documents/plans/DSC_0506.gif", "floor-plan"),
    ("mmbench-mini/images/hvac-symbols.webp", "Documents/plans/DSC_0507.webp", "hvac-symbols"),
    ("mmbench-mini/images/layout-mck-1.jpg", "Documents/plans/DSC_0508.jpg", "page-layout"),
    # Financial-document images.
    (
        "mmbench-mini/images/alphabet-balance-sheet-10k-annual-report_0.jpg",
        "Documents/financial/DSC_0601.jpg",
        "balance-sheet",
    ),
    ("mmbench-mini/images/form-10k-page3.webp", "Documents/financial/DSC_0602.webp", "form-10k"),
    ("mmbench-mini/images/form-10k-page4.webp", "Documents/financial/DSC_0603.webp", "form-10k"),
    ("mmbench-mini/images/tech-report-table.jpg", "Documents/financial/DSC_0604.jpg", "table"),
    ("mmbench-mini/images/calendar.png", "Documents/misc/DSC_0701.png", "calendar"),
    # Photo-library needles with known subjects (retrieval among scale noise).
    ("mmbench-mini/images/bus.jpg", "Photos/library/IMG_1001.jpg", "bus"),
    ("mmbench-mini/images/boats.avif", "Photos/library/IMG_1002.avif", "boats"),
    ("mmbench-mini/images/containers.png", "Photos/library/IMG_1003.png", "containers"),
    ("mmbench-mini/images/crowd.png", "Photos/library/IMG_1004.png", "crowd"),
    ("mmbench-mini/images/bottles.png", "Photos/library/IMG_1005.png", "bottles"),
    ("mmbench-mini/images/ocr-truck.png", "Photos/library/IMG_1006.png", "truck"),
    ("mmbench-mini/images/remote-sensing.jpg", "Photos/library/IMG_1007.jpg", "aerial"),
    ("mmbench-mini/images/nyc-workers-gray.webp", "Photos/library/IMG_1008.webp", "workers"),
]

# Ground-truth attributes keyed by dest path (confirmed from mm content catalog).
ATTRS: dict[str, dict] = {
    "Downloads/IMG_2231.jpg": {"subject": "vehicles"},
    "Downloads/IMG_2232.jpg": {"subject": "animals"},
    "Downloads/IMG_2233.png": {"subject": "vehicles"},
    "Downloads/IMG_2234.jpg": {"subject": "animals"},
    "Downloads/IMG_2235.jpg": {
        "subject": "documents",
        "doc": "invoice",
        "total": 4647.68,
        "currency": "USD",
        "issuer": "Google",
    },
    "Downloads/invoices/scan_4471.pdf": {
        "total": 381.12,
        "currency": "EUR",
        "invoice_no": "123100401",
        "issuer": "CPB Software (Germany) GmbH",
        "customer": "Musterkunde AG",
    },
    "Documents/papers/paper_attn.pdf": {
        "title": "Attention Is All You Need",
        "pages": 15,
        "bleu_en_de": 28.4,
    },
    "Documents/plans/DSC_0502.png": {"bedrooms": 4, "bathrooms": 2, "largest_room": "dining"},
    "Documents/financial/DSC_0601.jpg": {"company": "Alphabet", "doc": "balance sheet"},
    "Documents/financial/DSC_0604.jpg": {"doc": "Qwen2.5-VL benchmark tables"},
    "Documents/misc/DSC_0701.png": {"month": "November 2017"},
    "Photos/library/IMG_1006.png": {"carrier": "J.B. Hunt", "container_no": "JBHU 282862"},
    "Media/clip_bakery.mp4": {
        "company": "5 Generation Bakers",
        "legacy_brand": "Jenny Lee",
        "product": "cinnamon swirl bread",
        "location": "McKees Rocks",
        "founded": 1941,
    },
}


def _download_tar(url: str, marker: Path) -> None:
    """Download and extract a .tar.gz into DATA_ROOT if ``marker`` is absent."""
    if marker.exists():
        return
    print(f"  downloading {url}")
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = DATA_ROOT / "_dl.tar.gz"
    urllib.request.urlretrieve(url, tmp)
    with tarfile.open(tmp) as tf:
        tf.extractall(DATA_ROOT)
    tmp.unlink()


def ensure_sources() -> None:
    """Make sure all three sources are present, fetching what is missing."""
    _download_tar(TINY_URL, DATA_ROOT / "mmbench-tiny")
    _download_tar(MINI_URL, DATA_ROOT / "mmbench-mini")
    if not FINEVISION_IMAGES.is_dir() or not any(FINEVISION_IMAGES.iterdir()):
        print("  decoding FineVision images via helper")
        subprocess.run([sys.executable, str(FINEVISION_HELPER)], check=True, cwd=str(REPO_ROOT))


def _distractor_sources() -> list[Path]:
    """A deterministic slice of FineVision images used as opaque scale noise."""
    imgs = sorted(p for p in FINEVISION_IMAGES.glob("*") if p.suffix.lower() in {".png", ".jpg"})
    if len(imgs) < NUM_DISTRACTORS:
        raise FileNotFoundError(
            f"need {NUM_DISTRACTORS} FineVision images, found {len(imgs)} in {FINEVISION_IMAGES}"
        )
    return imgs[:NUM_DISTRACTORS]


def build() -> dict:
    """Assemble the fixture and return the manifest dict (also written to disk)."""
    ensure_sources()
    if FIXTURE.exists():
        shutil.rmtree(FIXTURE)

    entries: list[dict] = []

    def place(src: Path, dest_rel: str, label: str) -> None:
        dest = FIXTURE / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        entry = {"path": dest_rel, "label": label, "source": str(src.relative_to(DATA_ROOT))}
        entry.update(ATTRS.get(dest_rel, {}))
        entries.append(entry)

    for src_rel, dest_rel, label in MANIFEST:
        src = DATA_ROOT / src_rel
        if not src.exists():
            raise FileNotFoundError(f"manifest source missing: {src}")
        place(src, dest_rel, label)

    # Scale noise: ~150 opaque photos split across a nested, dated photo tree.
    buckets = ["Photos/2023", "Photos/2024", "Photos/unsorted"]
    for i, src in enumerate(_distractor_sources()):
        bucket = buckets[i % len(buckets)]
        place(src, f"{bucket}/IMG_{3001 + i}{src.suffix.lower()}", "distractor")

    manifest = {
        "name": "mmbench-agent",
        "file_count": len(entries),
        "files": sorted(entries, key=lambda e: e["path"]),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    m = build()
    print(f"built {FIXTURE} with {m['file_count']} files; manifest at {MANIFEST_PATH}")
