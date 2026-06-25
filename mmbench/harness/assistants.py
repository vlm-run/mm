"""Agent-CLI adapters: invoke an agent on a case, capture answer, timing, grounding.

Each supported agent is a non-interactive CLI that runs agentically against its
working directory. Invocations differ per agent (subcommand, autonomy flag,
prompt position), so each registry entry carries the full arg vector that
precedes the prompt; the prompt is always the final argument.

Both arms get the same task prompt and run with the agent's autonomy flag so tool
use does not stall on an interactive permission gate. The only intended
difference is mm availability, enforced by a PATH shim:

  - without_mm:  ``mm`` resolves to a stub that exits 127 ("command not found"), so
               the agent genuinely has no mm.
  - with_mm: ``mm`` resolves to a logging shim that runs the real mm (passing its
               output and exit status straight through) and records each call to
               ``$MMBENCH_MM_LOG`` with its exit code, duration, and args.
               mm-grounding is read from that log (reliable and agent-agnostic),
               and the prompt is prefixed with the mm primer. ``MM_PROFILE``
               selects mm's backend; temp ``MM_DATA_DIR`` and ``MM_CACHE_DIR``
               isolate mm's DB and on-disk cache per run (no cross-run/session leak).

Autonomy is verified per agent via ``probe_autonomy`` (used by preflight): the
agent must non-interactively execute a shell command and echo a sentinel.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .agent_output import AgentOutput, AgentOutputParser, TokenUsage
from .cases import EvalCase

PRIMER_PATH = Path(__file__).resolve().parent / "primer.md"
DEFAULT_TIMEOUT_S = 600  # global cap; per-case timeout_s (360-600) is honored under it
MM_COMMANDS = ("find", "peek", "wc", "sql", "grep", "cat")

_REGISTRY: dict[str, list[str]] = {
    "claude": ["claude", "--dangerously-skip-permissions", "--output-format", "json", "-p"],
    "codex": ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--json"],
    "gemini": ["gemini", "--yolo", "-o", "json", "-p"],
    "qwen": ["qwen", "--yolo", "-o", "json", "-p"],
    "opencode": ["opencode", "run", "--dangerously-skip-permissions", "--format", "json"],
    "openclaw": ["openclaw", "agent", "--local", "--json"],
    "hermes": ["hermes", "--yolo", "-z"],
    "pi": ["pi", "--no-session", "--mode", "json", "-p"],
}

SUPPORTED = tuple(_REGISTRY)


@dataclass
class AssistantResult:
    """Outcome of one agent invocation.

    Attributes:
        final_output: the agent's stdout (its answer in non-interactive mode).
        stderr: the agent's stderr, for postmortem.
        elapsed_s: wall-clock seconds.
        exit_code: process exit code (None if it timed out).
        timed_out: whether the invocation hit the timeout.
        mm_commands_used: mm subcommands the agent actually ran (with_mm only),
            from the PATH-shim log; reliable, not a transcript heuristic.
        mm_log: the full ordered mm invocation log (every ``mm ...`` line with its
            flags and args), as recorded by the shim; empty in the without_mm arm.
        mm_token_total: mm's own LLM token usage (prompt + completion) summed across
            this run's ``mm cat`` extractions; 0 in the without_mm arm.
    """

    final_output: str
    stderr: str
    elapsed_s: float
    exit_code: int | None
    timed_out: bool = False
    mm_commands_used: list[str] = field(default_factory=list)
    mm_log: str = ""
    token_usage: TokenUsage | None = None
    mm_token_total: int = 0


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
        """Assemble the prompt; with_mm prepends the mm primer. Same task both arms."""
        kind = "directory" if input_path.is_dir() else "file"
        body = f"The input {kind} is at: {input_path}\n\n{case.prompt.strip()}\n"
        return f"{primer.strip()}\n\n---\n\n{body}" if arm == "with_mm" else body

    def build_argv(self, prompt: str) -> list[str]:
        """argv for a non-interactive run; prompt is the final positional argument.

        openclaw is the only agent that needs a session selector: it gets a unique
        per-run session key so no agent state leaks across cases or runs, and the
        prompt is passed via ``-m`` (still the final argument).
        """
        if self.name == "openclaw":
            key = f"agent:main:mmbench-{uuid.uuid4().hex}"
            return [*self.cmd, "--session-key", key, "-m", prompt]
        return [*self.cmd, prompt]

    def run(
        self,
        case: EvalCase,
        *,
        arm: str,
        input_path: Path,
        primer: str,
        profile_name: str | None = None,
        config_dir: str | None = None,
        timeout_s: int = DEFAULT_TIMEOUT_S,
        stream: bool = False,
    ) -> AssistantResult:
        """Invoke the agent on one (case, arm), returning answer + timing + grounding.

        When ``stream`` is set, the agent's stdout/stderr are also teed to this
        process's terminal live; the captured result is identical either way.
        ``config_dir`` (ad-hoc profiles) overrides ``MM_CONFIG_DIR`` for the agent.
        """
        prompt = self.build_prompt(case, arm, input_path, primer)
        cwd = input_path if input_path.is_dir() else input_path.parent
        with _mm_shim(arm) as (shim_dir, mm_log):
            env = self._env(arm, shim_dir, mm_log, profile_name, config_dir)
            out = _exec(self.build_argv(prompt), cwd, env, timeout_s, stream=stream)
            used = _read_mm_log(mm_log) if arm == "with_mm" else []
            log_text = _read_mm_log_full(mm_log) if arm == "with_mm" else ""
            # mm's own token spend lives in its run-isolated cache (MM_DATA_DIR set
            # by _env). Read it post-run — no extra mm call, no agent-runtime impact.
            mm_tokens = (
                _read_mm_token_total(Path(env["MM_DATA_DIR"]) / "mm.db") if arm == "with_mm" else 0
            )
        parsed = self._parse_output(out["final_output"], cwd=str(cwd))
        out["final_output"] = parsed.final_output
        out["token_usage"] = parsed.token_usage
        return AssistantResult(
            mm_commands_used=used, mm_log=log_text, mm_token_total=mm_tokens, **out
        )

    def _parse_output(self, stdout: str, *, cwd: str | None = None) -> AgentOutput:
        """Parse raw agent stdout into extracted text + token usage via AgentOutputParser."""
        parser = AgentOutputParser()
        if self.name == "hermes":
            sid = parser._hermes_latest_session(cwd)
            if sid is None:
                return AgentOutput(final_output=stdout.strip())
            return parser.hermes(stdout, session_id=sid, cwd=cwd)
        return getattr(parser, self.name)(stdout)

    def _env(
        self,
        arm: str,
        shim_dir: Path,
        mm_log: Path,
        profile_name: str | None,
        config_dir: str | None = None,
    ) -> dict:
        env = os.environ.copy()
        env["PATH"] = f"{shim_dir}{os.pathsep}{env.get('PATH', '')}"
        env["MMBENCH_MM_LOG"] = str(mm_log)
        if arm == "with_mm":
            if profile_name:
                env["MM_PROFILE"] = profile_name
            # Ad-hoc profiles live in a throwaway config dir; point mm at it so the
            # backend resolves without a global profile. Named profiles leave this
            # unset and resolve from the user's real mm config.
            if config_dir:
                env["MM_CONFIG_DIR"] = config_dir
            # Isolate mm's storage AND on-disk cache per run so neither the DB nor
            # the memoize cache (transcripts, shot detection, ...) leaks across
            # runs or sessions. Config is left shared so the profile still resolves.
            env["MM_DATA_DIR"] = str(shim_dir / "mm-data")
            env["MM_CACHE_DIR"] = str(shim_dir / "mm-cache")
        return env

    def probe_autonomy(self, timeout_s: int = 90) -> tuple[bool, str]:
        """Verify the agent runs a shell tool non-interactively. Returns (ok, detail)."""
        token = uuid.uuid4().hex
        with _mm_shim("without_mm") as (shim_dir, mm_log):
            probe_file = shim_dir / "autonomy_probe.txt"
            probe_file.write_text(token)
            prompt = f"Run this shell command and report only its output: cat {probe_file}"
            env = self._env("without_mm", shim_dir, mm_log, None)
            out = _exec(self.build_argv(prompt), shim_dir, env, timeout_s)
        if out["timed_out"]:
            return False, f"timed out after {timeout_s}s"
        parsed = self._parse_output(out["final_output"], cwd=str(shim_dir))
        if token in parsed.final_output or token in out["stderr"]:
            return True, "ok"
        return False, f"did not execute the tool (exit {out['exit_code']})"


def _exec(argv: list[str], cwd: Path, env: dict, timeout_s: int, *, stream: bool = False) -> dict:
    """Run argv, capturing stdout/stderr/timing. Never raises on agent failure.

    With ``stream``, output is teed to this process's terminal as it arrives while
    still being captured in full; the returned dict is identical to the buffered path.
    """
    t0 = time.perf_counter()
    if stream:
        stdout, stderr, code, timed_out = _exec_streaming(argv, cwd, env, timeout_s)
    else:
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
    return {
        "final_output": stdout.strip(),
        "stderr": stderr.strip(),
        "elapsed_s": elapsed,
        "exit_code": code,
        "timed_out": timed_out,
    }


def _exec_streaming(
    argv: list[str], cwd: Path, env: dict, timeout_s: int
) -> tuple[str, str, int | None, bool]:
    """Run argv, teeing stdout->stdout and stderr->stderr live while capturing both.

    Returns ``(stdout, stderr, exit_code, timed_out)``. stdout and stderr stay
    separate (reader thread per stream) so ``final_output`` is unaffected by tee.
    """
    p = subprocess.Popen(
        argv,
        cwd=str(cwd),
        env=env,
        text=True,
        bufsize=1,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out_buf: list[str] = []
    err_buf: list[str] = []
    write_lock = threading.Lock()

    def _pump(pipe, buf, sink) -> None:
        for line in iter(pipe.readline, ""):
            buf.append(line)
            with write_lock:
                sink.write(line)
                sink.flush()
        pipe.close()

    threads = [
        threading.Thread(target=_pump, args=(p.stdout, out_buf, sys.stdout), daemon=True),
        threading.Thread(target=_pump, args=(p.stderr, err_buf, sys.stderr), daemon=True),
    ]
    for t in threads:
        t.start()
    timed_out = False
    try:
        code = p.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        p.kill()
        code, timed_out = None, True
        p.wait()
    for t in threads:
        t.join()
    return "".join(out_buf), "".join(err_buf), code, timed_out


class _mm_shim:
    """Context manager: a temp bin dir whose ``mm`` is a stub (without_mm) or a
    logging shim over the real mm (with_mm). Yields (shim_dir, mm_log)."""

    def __init__(self, arm: str) -> None:
        self.arm = arm
        self._tmp: tempfile.TemporaryDirectory | None = None

    def __enter__(self) -> tuple[Path, Path]:
        self._tmp = tempfile.TemporaryDirectory(prefix="mmbench-shim-")
        d = Path(self._tmp.name)
        mm_log = d / "mm.log"
        mm_log.touch()
        shim = d / "mm"
        if self.arm == "with_mm":
            real = shutil.which("mm")
            if real is None:
                raise RuntimeError("mm not found on PATH; with_mm arm cannot run")
            # Run (not exec) real mm so we can record exit code + duration; mm's
            # stdout/stderr and exit status pass straight through to the agent.
            shim.write_text(
                "#!/bin/sh\n"
                "start=$(date +%s)\n"
                f'"{real}" "$@"\n'
                "code=$?\n"
                "end=$(date +%s)\n"
                'printf \'%s\\t%s\\t%s\\n\' "$code" "$((end - start))" "$*" >> "$MMBENCH_MM_LOG"\n'
                "exit $code\n"
            )
        else:
            shim.write_text('#!/bin/sh\necho "mm: command not found" >&2\nexit 127\n')
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return d, mm_log

    def __exit__(self, *exc) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()


def _read_mm_log(mm_log: Path) -> list[str]:
    """Distinct mm subcommands recorded by the with_mm shim, in first-seen order."""
    seen: list[str] = []
    for line in mm_log.read_text().splitlines():
        args = line.split("\t")[-1]  # log line is <code>\t<duration>\t<args>
        parts = args.split()
        if parts and parts[0] in MM_COMMANDS and parts[0] not in seen:
            seen.append(parts[0])
    return seen


_VERBOSE_TOKENS = re.compile(r"(\d+)→(\d+)\s*tokens")


def _read_mm_token_total(db_path: Path) -> int:
    """Sum mm's own LLM token usage (prompt + completion) from the run's mm cache.

    mm persists its verbose pipeline tail — which carries ``prompt→completion
    tokens`` — into ``extractions.metadata``. Reading it recovers mm's token spend
    without a second ``mm`` invocation, so the agent's measured runtime is
    unaffected. Returns 0 when the cache is absent or held no LLM-backed cat.
    """
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT metadata FROM extractions WHERE metadata IS NOT NULL"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return 0
    total = 0
    for (meta_json,) in rows:
        try:
            suffix = (json.loads(meta_json) or {}).get("verbose_suffix") or ""
        except (json.JSONDecodeError, TypeError):
            continue
        m = _VERBOSE_TOKENS.search(suffix)
        if m:
            total += int(m.group(1)) + int(m.group(2))
    return total


def _read_mm_log_full(mm_log: Path) -> str:
    """The full ordered mm invocation log: every recorded ``mm ...`` line, verbatim."""
    return "\n".join(line for line in mm_log.read_text().splitlines() if line.strip())
