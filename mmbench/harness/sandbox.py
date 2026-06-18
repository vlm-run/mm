"""Per-run sandboxes: isolated, disposable working copies of a dataset subtree.

Organization and artifact tasks mutate the filesystem, so every cell runs in its
own pristine copy. A sandbox is tagged with `(assistant, profile, case, arm,
run_index)` so concurrent and repeated cells never collide. The authoritative
result lives in SQLite; the sandbox directory exists only so the grader can
inspect the final filesystem state and so a human can review what the agent did.
Sandboxes are therefore safe to delete at will.

Example:
    >>> mgr = SandboxManager()
    >>> with mgr.materialize(fixture, assistant="claude", profile="gateway",
    ...                       case_id="find-floor-plans", arm="treatment",
    ...                       run_index=0) as sb:
    ...     run_agent_in(sb.path)
    ...     grade(sb.path)
    # sandbox auto-disposed on exit (override with keep=True)
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SANDBOX_ROOT = Path(__file__).resolve().parents[2] / "benchmarks" / "data" / "_sandboxes"

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(value: str) -> str:
    """Filesystem-safe slug for a tag component."""
    return _SAFE.sub("-", value).strip("-") or "x"


@dataclass
class Sandbox:
    """A materialized working copy. Use as a context manager to auto-dispose.

    Attributes:
        path: the sandbox root the agent operates in.
        tag: the directory name encoding the originating cell.
        keep: if True, the sandbox is retained on context exit.
    """

    path: Path
    tag: str
    keep: bool = False

    def dispose(self) -> None:
        """Delete the sandbox directory (idempotent)."""
        if self.path.exists():
            shutil.rmtree(self.path)

    def __enter__(self) -> Sandbox:
        return self

    def __exit__(self, *exc) -> None:
        if not self.keep:
            self.dispose()


class SandboxManager:
    """Creates tagged, disposable copies of a dataset subtree.

    Args:
        root: base directory under which sandboxes are created. Defaults under
            ``benchmarks/data/`` which is gitignored.
    """

    def __init__(self, root: Path = DEFAULT_SANDBOX_ROOT) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def tag_for(
        self, *, assistant: str, profile: str, case_id: str, arm: str, run_index: int
    ) -> str:
        """The deterministic sandbox directory name for a cell."""
        parts = [assistant, profile, case_id, arm, f"r{run_index}"]
        return "__".join(_slug(p) for p in parts)

    def materialize(
        self,
        source: Path,
        *,
        assistant: str,
        profile: str,
        case_id: str,
        arm: str,
        run_index: int,
        keep: bool = False,
    ) -> Sandbox:
        """Copy ``source`` into a fresh tagged sandbox and return its handle.

        A pre-existing sandbox with the same tag is removed first so the copy is
        always pristine. ``source`` may be a directory (copied recursively) or a
        single file (copied into the sandbox root).
        """
        if not source.exists():
            raise FileNotFoundError(f"sandbox source does not exist: {source}")
        tag = self.tag_for(
            assistant=assistant, profile=profile, case_id=case_id, arm=arm, run_index=run_index
        )
        dest = self.root / tag
        if dest.exists():
            shutil.rmtree(dest)
        if source.is_dir():
            shutil.copytree(source, dest)
        else:
            dest.mkdir(parents=True)
            shutil.copy2(source, dest / source.name)
        return Sandbox(path=dest, tag=tag, keep=keep)

    def prune_all(self) -> int:
        """Delete every sandbox under the root. Returns the count removed."""
        n = 0
        for child in self.root.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
                n += 1
        return n
