"""Task catalogue for mmbench-agents.

A :class:`TaskSpec` pairs an identical-across-arms prompt with a deterministic
verifier and the ``mm`` commands the task is *intended* to exercise (agents may
discover others). Prompts deliberately never name an ``mm`` command — the agent
must decide to use ``mm`` — and they pin the answer JSON schema and the kind
taxonomy so baseline and ``mm`` arms are scored identically.

This module currently encodes the foundational slice of tasks; the full
20-case catalogue (see ``README.md`` §3) is added incrementally.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mmbench_agents.types import Scope
from mmbench_agents.verifiers import (
    ExactValueVerifier,
    ManifestVerifier,
    SetMembershipVerifier,
    Verifier,
)

_KIND_TAXONOMY = (
    "Classify each file by extension: .md/.txt=text, .py=code, .csv/.json=data, "
    ".png=image, .wav=audio."
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
)

TASKS_BY_ID: dict[str, TaskSpec] = {t.id: t for t in TASKS}
