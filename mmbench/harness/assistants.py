"""Agent-CLI adapters: invoke an agent on a case, capture answer, timing, grounding.

Each supported agent is a non-interactive CLI that runs agentically against its
working directory. Invocations differ per agent (subcommand, autonomy flag,
prompt position), so each registry entry carries the full arg vector that
precedes the prompt; the prompt is always the final argument.

Both arms get the same task prompt and run with the agent's autonomy flag so tool
use does not stall on an interactive permission gate. The only intended
difference is mm availability, enforced by a PATH shim:

  - baseline:  ``mm`` resolves to a stub that exits 127 ("command not found"), so
               the agent genuinely has no mm.
  - treatment: ``mm`` resolves to a logging shim that records every invocation to
               ``$MMBENCH_MM_LOG`` then execs the real mm. mm-grounding is read
               from that log (reliable and agent-agnostic), and the prompt is
               prefixed with the mm primer. ``MM_PROFILE`` selects mm's backend
               and a temp ``XDG_DATA_HOME`` isolates mm's index per run.

Autonomy is verified per agent via ``probe_autonomy`` (used by preflight): the
agent must non-interactively execute a shell command and echo a sentinel.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .cases import EvalCase

PRIMER_PATH = Path(__file__).resolve().parent / "primer.md"
DEFAULT_TIMEOUT_S = 360
MM_COMMANDS = ("find", "peek", "wc", "sql", "grep", "cat")

_REGISTRY: dict[str, list[str]] = {
    "claude": ["claude", "--dangerously-skip-permissions", "-p"],
    "codex": ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox"],
    "gemini": ["gemini", "--yolo", "-p"],
    "qwen": ["qwen", "--yolo", "-p"],
    "opencode": ["opencode", "run"],
    "openclaw": ["openclaw", "agent"],
}

SUPPORTED = tuple(_REGISTRY)


@dataclass
class AssistantResult:
    """Outcome of one agent invocation.

    Attributes:
        final_output: the agent's stdout (its answer in non-interactive mode).
        transcript: stdout + stderr, for postmortem.
        elapsed_s: wall-clock seconds.
        exit_code: process exit code (None if it timed out).
        timed_out: whether the invocation hit the timeout.
        mm_commands_used: mm subcommands the agent actually ran (treatment only),
            from the PATH-shim log; reliable, not a transcript heuristic.
    """

    final_output: str
    transcript: str
    elapsed_s: float
    exit_code: int | None
    timed_out: bool = False
    mm_commands_used: list[str] = field(default_factory=list)


class Assistant:
    """One agent-CLI adapter."""

    def __init__(self, name: str) -> None:
        if name not in _REGISTRY:
            raise ValueError(f"unknown assistant {name!r}; expected one of {SUPPORTED}")
        self.name = name
        self.cmd = _REGISTRY[name]

    @classmethod
    def get(cls, name: str) -> Assistant:
        return cls(name)

    def is_installed(self) -> bool:
        """Whether the CLI is on PATH."""
        return shutil.which(self.name) is not None

    def build_prompt(self, case: EvalCase, arm: str, input_path: Path, primer: str) -> str:
        """Assemble the prompt; treatment prepends the mm primer. Same task both arms."""
        kind = "directory" if input_path.is_dir() else "file"
        body = f"The input {kind} is at: {input_path}\n\n{case.prompt.strip()}\n"
        return f"{primer.strip()}\n\n---\n\n{body}" if arm == "treatment" else body

    def build_argv(self, prompt: str) -> list[str]:
        """argv for a non-interactive run; prompt is the final positional argument."""
        return [*self.cmd, prompt]

    def run(
        self,
        case: EvalCase,
        *,
        arm: str,
        input_path: Path,
        primer: str,
        profile_name: str | None = None,
        timeout_s: int = DEFAULT_TIMEOUT_S,
    ) -> AssistantResult:
        """Invoke the agent on one (case, arm), returning answer + timing + grounding."""
        prompt = self.build_prompt(case, arm, input_path, primer)
        cwd = input_path if input_path.is_dir() else input_path.parent
        with _mm_shim(arm) as (shim_dir, mm_log):
            env = self._env(arm, shim_dir, mm_log, profile_name)
            out = _exec(self.build_argv(prompt), cwd, env, timeout_s)
            used = _read_mm_log(mm_log) if arm == "treatment" else []
        return AssistantResult(mm_commands_used=used, **out)

    def _env(self, arm: str, shim_dir: Path, mm_log: Path, profile_name: str | None) -> dict:
        env = os.environ.copy()
        env["PATH"] = f"{shim_dir}{os.pathsep}{env.get('PATH', '')}"
        env["MMBENCH_MM_LOG"] = str(mm_log)
        if arm == "treatment":
            if profile_name:
                env["MM_PROFILE"] = profile_name
            env["XDG_DATA_HOME"] = str(shim_dir / "xdg")  # isolate mm's index per run
        return env

    def probe_autonomy(self, timeout_s: int = 90) -> tuple[bool, str]:
        """Verify the agent runs a shell tool non-interactively. Returns (ok, detail)."""
        token = uuid.uuid4().hex
        with _mm_shim("baseline") as (shim_dir, mm_log):
            probe_file = shim_dir / "autonomy_probe.txt"
            probe_file.write_text(token)
            prompt = f"Run this shell command and report only its output: cat {probe_file}"
            env = self._env("baseline", shim_dir, mm_log, None)
            out = _exec(self.build_argv(prompt), shim_dir, env, timeout_s)
        if out["timed_out"]:
            return False, f"timed out after {timeout_s}s"
        if token in out["final_output"] or token in out["transcript"]:
            return True, "ok"
        return False, f"did not execute the tool (exit {out['exit_code']})"


def _exec(argv: list[str], cwd: Path, env: dict, timeout_s: int) -> dict:
    """Run argv, capturing stdout/stderr/timing. Never raises on agent failure."""
    t0 = time.perf_counter()
    try:
        p = subprocess.run(
            argv,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            stdin=subprocess.DEVNULL,
        )
        stdout, stderr, code, timed_out = p.stdout, p.stderr, p.returncode, False
    except subprocess.TimeoutExpired as e:
        stdout = (e.stdout.decode() if isinstance(e.stdout, bytes) else e.stdout) or ""
        stderr = (e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr) or ""
        code, timed_out = None, True
    elapsed = time.perf_counter() - t0
    transcript = (stdout + ("\n[stderr]\n" + stderr if stderr else "")).strip()
    return {
        "final_output": stdout.strip(),
        "transcript": transcript,
        "elapsed_s": elapsed,
        "exit_code": code,
        "timed_out": timed_out,
    }


class _mm_shim:
    """Context manager: a temp bin dir whose ``mm`` is a stub (baseline) or a
    logging shim over the real mm (treatment). Yields (shim_dir, mm_log)."""

    def __init__(self, arm: str) -> None:
        self.arm = arm
        self._tmp: tempfile.TemporaryDirectory | None = None

    def __enter__(self) -> tuple[Path, Path]:
        self._tmp = tempfile.TemporaryDirectory(prefix="mmbench-shim-")
        d = Path(self._tmp.name)
        mm_log = d / "mm.log"
        mm_log.touch()
        shim = d / "mm"
        if self.arm == "treatment":
            real = shutil.which("mm")
            if real is None:
                raise RuntimeError("mm not found on PATH; treatment arm cannot run")
            shim.write_text(
                f'#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$MMBENCH_MM_LOG"\nexec "{real}" "$@"\n'
            )
        else:
            shim.write_text('#!/bin/sh\necho "mm: command not found" >&2\nexit 127\n')
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return d, mm_log

    def __exit__(self, *exc) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()


def _read_mm_log(mm_log: Path) -> list[str]:
    """Distinct mm subcommands recorded by the treatment shim, in first-seen order."""
    seen: list[str] = []
    for line in mm_log.read_text().splitlines():
        parts = line.split()
        if parts and parts[0] in MM_COMMANDS and parts[0] not in seen:
            seen.append(parts[0])
    return seen
