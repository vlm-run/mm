"""Reference answers derived from frozen ground truth.

These functions produce the schema-correct answer for each task directly from
``ground_truth.json``. They are **not** part of the evaluation of real
assistants (which must inspect the corpus themselves) — they exist so the mock
adapter and the unit tests have a known-good answer to emit, degrade, and
verify against.
"""

from __future__ import annotations

from typing import Any, Callable

Answer = dict[str, Any]
_BUILDERS: dict[str, Callable[[dict], Answer]] = {
    "manifest": lambda gt: {
        "counts_by_kind": dict(gt["counts_by_kind"]),
        "total_bytes": gt["total_bytes"],
        "top_files": list(gt["top_files"]),
    },
    "exact_duplicates": lambda gt: {
        "duplicate_files": [p for group in gt["duplicate_groups"] for p in group]
    },
    "audio_duration": lambda gt: {"duration_s": gt["audio_durations_s"]["audio/tone.wav"]},
    "largest_file": lambda gt: {"largest_file": gt["largest_file"]},
    "loc_count": lambda gt: {"total_lines": gt["total_lines_text_code"]},
    "wide_images": lambda gt: {"wide_images": list(gt["wide_images"])},
    "pdf_secret": lambda gt: {"answer": f"The activation code is {gt['secret_token']}."},
    "needle": lambda gt: {"file": gt["needle_file"]},
    "scanned_pdf": lambda gt: {"image_only_pdfs": list(gt["image_only_pdfs"])},
}


def correct_answer(task_id: str, gt: dict) -> Answer:
    """Return the schema-correct answer for ``task_id`` given ground truth."""
    return _BUILDERS[task_id](gt)


def corrupt_answer(task_id: str, gt: dict) -> Answer:
    """Return a deterministically wrong-but-plausible answer for ``task_id``."""
    answer = correct_answer(task_id, gt)
    if "total_bytes" in answer:
        answer["total_bytes"] = int(answer["total_bytes"]) + 999
    if "duration_s" in answer:
        answer["duration_s"] = float(answer["duration_s"]) + 1.0
    if "total_lines" in answer:
        answer["total_lines"] = int(answer["total_lines"]) + 5
    if "largest_file" in answer:
        answer["largest_file"] = "docs/readme.md"
    if "file" in answer:
        answer["file"] = "docs/readme.md"
    if "answer" in answer:
        answer["answer"] = "The activation code is UNKNOWN."
    for key in ("duplicate_files", "wide_images", "image_only_pdfs", "top_files"):
        if key in answer and answer[key]:
            answer[key] = answer[key][:-1]
    return answer
