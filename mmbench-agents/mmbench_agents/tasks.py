"""Task catalogue for mmbench-agents.

A :class:`TaskSpec` pairs an identical-across-arms prompt with a deterministic
verifier and the ``mm`` commands the task is *intended* to exercise (agents may
discover others). Prompts deliberately never name an ``mm`` command — the agent
must decide to use ``mm`` — and they pin the answer JSON schema and the kind
taxonomy so baseline and ``mm`` arms are scored identically.

The catalogue spans all three scopes (file/directory/mixed) and collectively
exercises every action command (``find``/``wc``/``sql``/``peek``/``grep``/``cat``).
It is intentionally extensible: richer cases (video, EXIF, near-duplicate,
invoice arithmetic) only need corpus assets plus a verifier, not new harness code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mmbench_agents.types import Scope
from mmbench_agents.verifiers import (
    ContainsVerifier,
    ExactValueVerifier,
    ManifestVerifier,
    SetMembershipVerifier,
    Verifier,
)

_KIND_TAXONOMY = (
    "Classify each file by extension: .md/.txt=text, .py=code, .csv/.json=data, "
    ".png=image, .wav=audio, .pdf=document."
)


@dataclass(frozen=True)
class TaskSpec:
    """One benchmark task: prompt, scope, verifier, and intended commands."""

    id: str
    title: str
    scope: Scope
    prompt: str
    verifier: Verifier
    intended_mm_commands: tuple[str, ...] = field(default_factory=tuple)


TASKS: tuple[TaskSpec, ...] = (
    TaskSpec(
        id="manifest",
        title="Triage a mixed directory",
        scope=Scope.MIXED,
        prompt=(
            "Inspect the directory CORPUS and produce a manifest. " + _KIND_TAXONOMY + " "
            "Return JSON with keys: 'counts_by_kind' (object mapping kind -> file count), "
            "'total_bytes' (integer sum of all file sizes), and 'top_files' (list of the 3 "
            "largest files by size, as POSIX paths relative to CORPUS)."
        ),
        verifier=ManifestVerifier(),
        intended_mm_commands=("find", "wc"),
    ),
    TaskSpec(
        id="exact_duplicates",
        title="Exact duplicate hunt",
        scope=Scope.MIXED,
        prompt=(
            "Find every set of files in CORPUS whose contents are byte-for-byte identical. "
            "Return JSON with key 'duplicate_files': the flat list of all paths (relative to "
            "CORPUS, POSIX) that belong to any such duplicate set."
        ),
        verifier=SetMembershipVerifier(answer_field="duplicate_files", gt_field="duplicate_groups"),
        intended_mm_commands=("peek", "sql", "find"),
    ),
    TaskSpec(
        id="audio_duration",
        title="Audio duration",
        scope=Scope.FILE,
        prompt=(
            "Report the duration in seconds of the audio file CORPUS/audio/tone.wav. "
            "Return JSON with key 'duration_s' (number, seconds)."
        ),
        verifier=ExactValueVerifier(
            {"duration_s": (("audio_durations_s", "audio/tone.wav"), 0.05)}
        ),
        intended_mm_commands=("cat", "peek"),
    ),
    TaskSpec(
        id="largest_file",
        title="Largest file",
        scope=Scope.MIXED,
        prompt=(
            "Identify the single largest file in CORPUS by byte size. Return JSON with key "
            "'largest_file' (its POSIX path relative to CORPUS)."
        ),
        verifier=ExactValueVerifier({"largest_file": (("largest_file",), None)}),
        intended_mm_commands=("find", "sql"),
    ),
    TaskSpec(
        id="loc_count",
        title="Line count across text and code",
        scope=Scope.DIRECTORY,
        prompt=(
            "Count the total number of newline characters across every text and code file in "
            "CORPUS. " + _KIND_TAXONOMY + " Consider only files of kind text or code. Return "
            "JSON with key 'total_lines' (integer)."
        ),
        verifier=ExactValueVerifier({"total_lines": (("total_lines_text_code",), 0)}),
        intended_mm_commands=("wc", "find"),
    ),
    TaskSpec(
        id="wide_images",
        title="Wide images",
        scope=Scope.DIRECTORY,
        prompt=(
            "List every image file in CORPUS whose pixel width is strictly greater than 200. "
            "Return JSON with key 'wide_images' (list of POSIX paths relative to CORPUS)."
        ),
        verifier=SetMembershipVerifier(answer_field="wide_images", gt_field="wide_images"),
        intended_mm_commands=("peek", "find"),
    ),
    TaskSpec(
        id="pdf_secret",
        title="Extract a PDF activation code",
        scope=Scope.FILE,
        prompt=(
            "The document CORPUS/docs/contract.pdf states an activation code. Read the document "
            "and report that code. Return JSON with key 'answer' (string)."
        ),
        verifier=ContainsVerifier(answer_field="answer", gt_field="secret_token"),
        intended_mm_commands=("cat",),
    ),
    TaskSpec(
        id="needle",
        title="Locate a phrase across files",
        scope=Scope.DIRECTORY,
        prompt=(
            "Exactly one file in CORPUS contains the phrase 'activation code'. Identify it. "
            "Return JSON with key 'file' (its POSIX path relative to CORPUS)."
        ),
        verifier=ExactValueVerifier({"file": (("needle_file",), None)}),
        intended_mm_commands=("grep", "find", "cat"),
    ),
    TaskSpec(
        id="scanned_pdf",
        title="Detect image-only PDFs",
        scope=Scope.DIRECTORY,
        prompt=(
            "Some PDFs in CORPUS are image-only (scanned) with no extractable text layer. "
            "List every such PDF. Return JSON with key 'image_only_pdfs' (list of POSIX paths "
            "relative to CORPUS)."
        ),
        verifier=SetMembershipVerifier(answer_field="image_only_pdfs", gt_field="image_only_pdfs"),
        intended_mm_commands=("cat", "find"),
    ),
)

TASKS_BY_ID: dict[str, TaskSpec] = {t.id: t for t in TASKS}
