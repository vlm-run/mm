"""Unit tests for the frozen dataset and the deterministic verifiers.

Covers two things: (1) the corpus rebuilds to the committed hash + ground
truth (the dataset pin), and (2) each verifier passes on a ground-truth-correct
answer and fails when the answer is corrupted.
"""

from __future__ import annotations

from mmbench import dataset
from mmbench.tasks import TASKS_BY_ID


def test_dataset_rebuilds_to_pinned_hash_and_ground_truth(tmp_path):
    corpus = dataset.build_corpus(tmp_path)
    assert dataset.compute_dataset_hash(corpus) == dataset.pinned_hash()
    assert dataset.compute_ground_truth(corpus) == dataset.load_ground_truth()


def test_manifest_verifier_pass_and_fail():
    gt = dataset.load_ground_truth()
    verifier = TASKS_BY_ID["manifest"].verifier

    correct = {
        "counts_by_kind": gt["counts_by_kind"],
        "total_bytes": gt["total_bytes"],
        "top_files": gt["top_files"],
    }
    assert verifier.verify(correct, gt).passed

    wrong = {**correct, "total_bytes": gt["total_bytes"] + 1}
    report = verifier.verify(wrong, gt)
    assert not report.passed
    assert 0.0 < report.score < 1.0


def test_exact_duplicate_verifier_pass_and_fail():
    gt = dataset.load_ground_truth()
    verifier = TASKS_BY_ID["exact_duplicates"].verifier
    expected = [p for group in gt["duplicate_groups"] for p in group]

    assert verifier.verify({"duplicate_files": expected}, gt).passed
    assert not verifier.verify({"duplicate_files": expected[:1]}, gt).passed
    assert not verifier.verify({}, gt).passed


def test_audio_duration_verifier_tolerance():
    gt = dataset.load_ground_truth()
    verifier = TASKS_BY_ID["audio_duration"].verifier
    truth = gt["audio_durations_s"]["audio/tone.wav"]

    assert verifier.verify({"duration_s": truth}, gt).passed
    assert verifier.verify({"duration_s": truth + 0.04}, gt).passed  # within tol
    assert not verifier.verify({"duration_s": truth + 0.5}, gt).passed
    assert not verifier.verify({"duration_s": "two seconds"}, gt).passed
