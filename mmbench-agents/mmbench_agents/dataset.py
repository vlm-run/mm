"""Frozen corpus + independently-computed ground truth for mmbench-agents.

The corpus is generated **deterministically** from constants in this module
(fixed text/code/data files, fixed PNG blobs, a stdlib-``wave`` tone), so its
bytes are identical on every machine and pinned by ``dataset_hash``. Ground
truth is computed with tools **independent of ``mm``** (``os.stat``,
``hashlib``, ``wave``) to avoid circularity, then frozen into
``dataset/ground_truth.json``.

Regenerate the committed corpus + ground truth with::

    python -m mmbench_agents.dataset freeze

and verify a checkout matches the pin with::

    python -m mmbench_agents.dataset verify
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import wave
from pathlib import Path

_DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"
CORPUS_DIR = _DATASET_DIR / "corpus"
GROUND_TRUTH_PATH = _DATASET_DIR / "ground_truth.json"
MANIFEST_PATH = _DATASET_DIR / "MANIFEST.json"

KIND_BY_EXT: dict[str, str] = {
    ".md": "text",
    ".txt": "text",
    ".py": "code",
    ".csv": "data",
    ".json": "data",
    ".png": "image",
    ".wav": "audio",
}

_README_MD = "# Sample Corpus\n\nA tiny mixed directory for mmbench-agents.\n"
_NOTES_TXT = "alpha\nbeta\ngamma\ndelta\n"
_APP_PY = (
    "def main() -> None:\n    print('hello mmbench')\n\n\nif __name__ == '__main__':\n    main()\n"
)
_UTIL_PY = "def add(a: int, b: int) -> int:\n    return a + b\n"
_RECORDS_CSV = "id,name,score\n1,ada,42\n2,linus,37\n3,grace,55\n"

_RED_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAUAAAADwCAIAAAD+Tyo8AAAC00lEQVR4nO3TMQ0AIADAMEAI/qUgCw88"
    "ZEmrYM/m2XsATet3APDOwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEh"
    "zMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwM"
    "YQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZg"
    "CDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjAD"
    "Q5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZ"
    "GMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHM"
    "wBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxh"
    "BoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAI"
    "MzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMAND"
    "mIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkY"
    "wgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoawC4+fAuT34w+9AAAAAElFTkSuQmCC"
)
_BLUE_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAIAAABMXPacAAABMElEQVR4nO3RQQ0AIBDAMEDI+ZeCLGT0"
    "wapgyfbMXXGODvhdA7AGYA3AGoA1AGsA1gCsAVgDsAZgDcAagDUAawDWAKwBWAOwBmANwBqANQBrANYA"
    "rAFYA7AGYA3AGoA1AGsA1gCsAVgDsAZgDcAagDUAawDWAKwBWAOwBmANwBqANQBrANYArAFYA7AGYA3A"
    "GoA1AGsA1gCsAVgDsAZgDcAagDUAawDWAKwBWAOwBmANwBqANQBrANYArAFYA7AGYA3AGoA1AGsA1gCs"
    "AVgDsAZgDcAagDUAawDWAKwBWAOwBmANwBqANQBrANYArAFYA7AGYA3AGoA1AGsA1gCsAVgDsAZgDcAa"
    "gDUAawDWAKwBWAOwBmANwBqANQBrANYArAFYA7AGYA3AGoA1AGsA9gCQ6gIEGGlAtQAAAABJRU5ErkJg"
    "gg=="
)

_AUDIO_RATE = 8000
_AUDIO_FRAMES = 16000  # 2.0 seconds of 16-bit mono silence


def _write_wav(path: Path) -> None:
    """Write a deterministic 2.0s, 8 kHz, 16-bit mono silent WAV."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_AUDIO_RATE)
        w.writeframes(b"\x00\x00" * _AUDIO_FRAMES)


def build_corpus(dest: Path) -> Path:
    """Generate the frozen corpus under ``dest/corpus`` (idempotent)."""
    corpus = dest / "corpus"
    files: dict[str, bytes] = {
        "docs/readme.md": _README_MD.encode(),
        "docs/notes.txt": _NOTES_TXT.encode(),
        "code/app.py": _APP_PY.encode(),
        "code/util.py": _UTIL_PY.encode(),
        "data/records.csv": _RECORDS_CSV.encode(),
        "img/red.png": base64.b64decode(_RED_PNG_B64),
        "img/red_copy.png": base64.b64decode(_RED_PNG_B64),
        "img/blue.png": base64.b64decode(_BLUE_PNG_B64),
    }
    for rel, data in files.items():
        path = corpus / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    audio = corpus / "audio" / "tone.wav"
    audio.parent.mkdir(parents=True, exist_ok=True)
    _write_wav(audio)
    return corpus


def _iter_files(corpus: Path) -> list[Path]:
    """Return all corpus files sorted by POSIX relative path."""
    return sorted(
        (p for p in corpus.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(corpus).as_posix(),
    )


def compute_dataset_hash(corpus: Path) -> str:
    """SHA-256 over ``(relpath, bytes)`` of every file — the corpus pin."""
    h = hashlib.sha256()
    for path in _iter_files(corpus):
        h.update(path.relative_to(corpus).as_posix().encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def compute_ground_truth(corpus: Path) -> dict:
    """Compute ground truth with tools independent of ``mm``.

    Produces per-kind counts, total bytes, the three largest files, exact
    duplicate groups (SHA-256), and audio durations (``wave``).
    """
    paths = _iter_files(corpus)
    rels = [p.relative_to(corpus).as_posix() for p in paths]

    counts: dict[str, int] = {}
    for rel in rels:
        kind = KIND_BY_EXT.get(Path(rel).suffix.lower(), "other")
        counts[kind] = counts.get(kind, 0) + 1

    sizes = {rel: path.stat().st_size for rel, path in zip(rels, paths)}
    total_bytes = sum(sizes.values())
    top_files = sorted(sizes, key=lambda r: (-sizes[r], r))[:3]

    by_digest: dict[str, list[str]] = {}
    for rel, path in zip(rels, paths):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        by_digest.setdefault(digest, []).append(rel)
    duplicate_groups = sorted(sorted(g) for g in by_digest.values() if len(g) > 1)

    durations: dict[str, float] = {}
    for rel, path in zip(rels, paths):
        if Path(rel).suffix.lower() == ".wav":
            with wave.open(str(path), "rb") as w:
                durations[rel] = round(w.getnframes() / w.getframerate(), 3)

    return {
        "counts_by_kind": counts,
        "total_bytes": total_bytes,
        "top_files": top_files,
        "duplicate_groups": duplicate_groups,
        "audio_durations_s": durations,
    }


def freeze(dest: Path = _DATASET_DIR) -> dict:
    """Build the corpus and write ``ground_truth.json`` + ``MANIFEST.json``."""
    corpus = build_corpus(dest)
    gt = compute_ground_truth(corpus)
    dataset_hash = compute_dataset_hash(corpus)
    GROUND_TRUTH_PATH.write_text(json.dumps(gt, indent=2, sort_keys=True) + "\n")
    MANIFEST_PATH.write_text(
        json.dumps({"dataset_hash": dataset_hash}, indent=2, sort_keys=True) + "\n"
    )
    return {"dataset_hash": dataset_hash, "ground_truth": gt}


def load_ground_truth() -> dict:
    """Load the frozen ground truth committed to the repo."""
    return json.loads(GROUND_TRUTH_PATH.read_text())


def pinned_hash() -> str:
    """Return the committed ``dataset_hash`` from ``MANIFEST.json``."""
    return json.loads(MANIFEST_PATH.read_text())["dataset_hash"]


def verify_pin() -> bool:
    """Build the corpus and check it reproduces the committed pin + GT."""
    corpus = build_corpus(_DATASET_DIR)
    return (
        compute_dataset_hash(corpus) == pinned_hash()
        and compute_ground_truth(corpus) == load_ground_truth()
    )


def _main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "freeze"
    if cmd == "freeze":
        result = freeze()
        print(f"froze corpus: dataset_hash={result['dataset_hash']}")
        return 0
    if cmd == "verify":
        ok = verify_pin()
        print("pin OK" if ok else "pin MISMATCH")
        return 0 if ok else 1
    print(f"unknown command: {cmd!r} (expected 'freeze' or 'verify')")
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
