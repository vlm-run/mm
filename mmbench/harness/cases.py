"""Declarative eval cases: typed model, loader, and validator.

Cases are data, not code. Each case is a YAML file under ``cases/`` carrying the
task prompt (handed verbatim to both arms), a frozen ground truth, deterministic
``checks`` for partial credit, and an LLM-judge objective. The same case feeds
every assistant, profile, and arm.

A case belongs to one of three real-world archetypes:

  - **retrieval**: locate the right file(s) in a tree (read-only).
  - **organization**: restructure the tree (mutates the sandbox).
  - **artifact**: synthesize across files into a written output file.

``checks`` therefore span three families (see ``CHECK_SPECS``): answer checks
run against the agent's final text, filesystem checks against the sandbox's
final state, and artifact checks against a file the agent wrote.

Example:
    >>> cases = load_cases()
    >>> cases[0].archetype
    'retrieval'
    >>> cases[0].resolve_dataset(Path("mmbench/data")).name
    'mmbench-agent'
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Cases ship inside the HF dataset; the harness downloads it to mmbench/data/.
CASES_FILE = Path(__file__).resolve().parents[1] / "data" / "cases.jsonl"

ARCHETYPES = ("retrieval", "organization", "artifact")
DIFFICULTIES = ("easy", "medium", "hard")
MODALITIES = ("image", "video", "audio", "pdf", "doc", "mixed")
MM_COMMANDS = ("find", "peek", "wc", "sql", "grep", "cat")

# check kind -> required parameter names (beyond `kind` and `weight`).
CHECK_SPECS: dict[str, tuple[str, ...]] = {
    # answer checks: against the agent's final text output
    "names_file": ("path",),
    "contains_number": ("value",),
    "contains_text": ("value",),
    # filesystem checks: against the sandbox's final state
    "path_exists": ("path",),
    "path_absent": ("path",),
    # artifact checks: against a file the agent wrote
    "artifact_exists": ("path",),
    "artifact_contains": ("path", "value"),
    "artifact_row_count": ("path", "count"),
}


@dataclass(frozen=True)
class Check:
    """A deterministic, partial-credit check.

    Attributes:
        kind: one of ``CHECK_SPECS``.
        weight: contribution to the deterministic score; weights across a case
            should sum to 1.0.
        params: kind-specific parameters (e.g. ``path``, ``value``, ``count``).
    """

    kind: str
    weight: float
    params: dict

    def __post_init__(self) -> None:
        if self.kind not in CHECK_SPECS:
            raise ValueError(f"check kind {self.kind!r} not in {tuple(CHECK_SPECS)}")
        if self.weight <= 0:
            raise ValueError(f"check weight must be positive, got {self.weight}")
        missing = set(CHECK_SPECS[self.kind]) - set(self.params)
        if missing:
            raise ValueError(f"check {self.kind!r} missing params {missing}")


@dataclass(frozen=True)
class EvalCase:
    """A single benchmark task.

    Attributes:
        id: stable slug, unique across the suite.
        title: human-readable one-liner.
        archetype: ``retrieval`` | ``organization`` | ``artifact``.
        modality: media kinds the task touches.
        dataset: subtree path under the datasets root (e.g. ``mmbench-agent``).
        mm_commands: mm surfaces a good with_mm solution exercises (coverage).
        difficulty: ``easy`` | ``medium`` | ``hard``.
        prompt: the task, given verbatim to both arms.
        ground_truth: the frozen, checkable answer.
        checks: deterministic partial-credit checks.
        judge_objective: rubric string scored 0-5 by the LLM judge.
    """

    id: str
    title: str
    archetype: str
    modality: list[str]
    dataset: str
    mm_commands: list[str]
    difficulty: str
    prompt: str
    ground_truth: dict
    checks: list[Check] = field(default_factory=list)
    judge_objective: str = ""

    def __post_init__(self) -> None:
        if self.archetype not in ARCHETYPES:
            raise ValueError(f"{self.id}: archetype {self.archetype!r} invalid")
        if self.difficulty not in DIFFICULTIES:
            raise ValueError(f"{self.id}: difficulty {self.difficulty!r} invalid")
        bad_mod = set(self.modality) - set(MODALITIES)
        if bad_mod:
            raise ValueError(f"{self.id}: unknown modality {bad_mod}")
        bad_cmd = set(self.mm_commands) - set(MM_COMMANDS)
        if bad_cmd:
            raise ValueError(f"{self.id}: unknown mm command {bad_cmd}")
        if not self.prompt.strip():
            raise ValueError(f"{self.id}: empty prompt")
        if not self.ground_truth:
            raise ValueError(f"{self.id}: missing ground_truth")
        if not self.judge_objective.strip():
            raise ValueError(f"{self.id}: missing judge_objective")

    def resolve_dataset(self, datasets_root: Path) -> Path:
        """Absolute path to this case's dataset subtree under ``datasets_root``.

        Raises:
            FileNotFoundError: if the resolved subtree does not exist.
        """
        path = (datasets_root / self.dataset).resolve()
        if not path.exists():
            raise FileNotFoundError(f"{self.id}: dataset not found at {path}")
        return path

    @classmethod
    def from_dict(cls, data: dict) -> EvalCase:
        """Build a case from parsed YAML, coercing the check list.

        Each YAML check is ``{kind, weight, ...params}``; ``kind`` and ``weight``
        are pulled out and everything else becomes ``params``.
        """
        raw = dict(data)
        checks = []
        for c in data.get("checks", []):
            c = dict(c)
            kind = c.pop("kind")
            weight = c.pop("weight")
            checks.append(Check(kind=kind, weight=weight, params=c))
        raw["checks"] = checks
        return cls(**raw)


def load_cases(cases_file: Path = CASES_FILE) -> list[EvalCase]:
    """Load and validate cases from the downloaded ``cases.jsonl``, sorted by id.

    Raises:
        FileNotFoundError: if the dataset has not been downloaded yet.
        ValueError: on a malformed case or a duplicate id.
    """
    if not cases_file.exists():
        raise FileNotFoundError(f"{cases_file} missing; run the benchmark to download the dataset")
    cases: list[EvalCase] = []
    seen: set[str] = set()
    for line in cases_file.read_text().splitlines():
        if not line.strip():
            continue
        case = EvalCase.from_dict(json.loads(line))
        if case.id in seen:
            raise ValueError(f"duplicate case id {case.id!r}")
        seen.add(case.id)
        cases.append(case)
    return sorted(cases, key=lambda c: c.id)
