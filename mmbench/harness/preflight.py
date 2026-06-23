"""Preflight: fail fast before any expensive run if the setup is not sound.

Checks, in order:
  1. Fixture: every selected case's dataset subtree exists.
  2. Assistants: each is installed AND passes a live autonomy probe (it must run
     a shell tool non-interactively).
  3. Profiles: each mm profile resolves and its chat endpoint answers a 1-token
     ping (this is the backend the with_mm arm uses).
  4. Judge: if enabled, the fixed judge endpoint answers a 1-token ping.

No silent fallbacks: a failure aborts the run with a precise reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .assistants import Assistant
from .cases import EvalCase
from .grader import JudgeConfig, ping_adhoc, ping_judge, ping_profile
from .profiles import ProfileSpec


@dataclass
class PreflightReport:
    """Collected pass/fail lines; ``ok`` is True only if there are no failures."""

    lines: list[str] = field(default_factory=list)
    ok: bool = True

    def add(self, passed: bool, label: str, detail: str = "") -> None:
        mark = "ok" if passed else "FAIL"
        self.lines.append(f"  [{mark}] {label}{f' - {detail}' if detail else ''}")
        if not passed:
            self.ok = False


def preflight(
    *,
    assistants: list[str],
    profiles: list[ProfileSpec],
    cases: list[EvalCase],
    datasets_root: Path,
    use_judge: bool,
    judge: JudgeConfig | None = None,
    autonomy_timeout_s: int = 90,
) -> PreflightReport:
    """Run every check and return the report. Does not raise."""
    r = PreflightReport()

    for c in cases:
        try:
            c.resolve_dataset(datasets_root)
            r.add(True, f"fixture: {c.id}")
        except FileNotFoundError as e:
            r.add(False, f"fixture: {c.id}", str(e))

    for name in assistants:
        try:
            a = Assistant.get(name)
        except ValueError as e:
            r.add(False, f"assistant: {name}", str(e))
            continue
        if not a.is_installed():
            r.add(False, f"assistant: {name}", "not on PATH")
            continue
        ok, detail = a.probe_autonomy(timeout_s=autonomy_timeout_s)
        r.add(ok, f"assistant: {name} (autonomy)", detail)

    for p in profiles:
        if p.is_adhoc:
            ok, detail = ping_adhoc(p.base_url or "", p.model or "", p.api_key or "")
        else:
            ok, detail = ping_profile(p.name)
        r.add(ok, f"profile: {p.name}", detail)

    if use_judge:
        ok, detail = ping_judge(judge or JudgeConfig.resolve())
        r.add(ok, "judge", detail)

    return r
