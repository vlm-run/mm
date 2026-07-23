"""Per-harness output parser: extracts the agent's text answer + token usage.

Each agent CLI emits its answer and token usage in a different JSON shape.
This module normalizes them into a single :class:`AgentOutput` with the
extracted text answer and optional :class:`TokenUsage`. Hermes is the
exception — it has no JSON mode, so the answer is the stripped stdout and
token usage is fetched post-run from the session store via
``hermes sessions export``.

Example:
    >>> parser = AgentOutputParser()
    >>> out = parser.claude('{"result":"hi","usage":{"input_tokens":10,"output_tokens":2}}')
    >>> out.final_output
    'hi'
    >>> out.token_usage.total_tokens
    12
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass


@dataclass
class TokenUsage:
    """Normalized token usage across all supported harnesses.

    Fields default to 0 when a harness doesn't report them. ``total_tokens``
    is the headline number: every token bucket the model actually processed,
    counted once — uncached input + output (reasoning is already inside output
    for the harnesses that report it that way) + cache read + cache write.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    cost_usd: float = 0.0

    def to_json(self) -> str:
        """Serialize to a JSON string for storage in the results DB."""
        return json.dumps(asdict(self))


@dataclass
class AgentOutput:
    """Normalized agent output: the answer text + optional token usage."""

    final_output: str
    token_usage: TokenUsage | None = None


class AgentOutputParser:
    """Parse agent stdout into a normalized :class:`AgentOutput`.

    Seven harnesses emit JSON with the answer text and token usage inline.
    :meth:`hermes` is the exception: the answer is plain-text stdout and
    token usage is fetched from the session store via ``hermes sessions
    export``, requiring a session_id. ``token_usage`` is ``None`` when a
    harness doesn't report usage or the JSON is malformed.
    """

    _hermes_timeout_s: int = 30

    def __init__(self):
        pass

    def claude(self, stdout: str) -> AgentOutput:
        """claude -p --output-format json: single object; ``result`` is the answer, ``usage`` has tokens.

        ``usage.input_tokens`` is the *uncached* remainder only; cache reads and
        cache writes are reported separately and dominate a multi-turn agentic
        session. The headline total must add them back, or it collapses to a tiny
        number (the symptom the leaderboard showed for Claude).
        """
        d = self._load_json(stdout)
        if not isinstance(d, dict):
            return AgentOutput(final_output=stdout.strip())
        u = d.get("usage") or {}
        inp, out = u.get("input_tokens", 0), u.get("output_tokens", 0)
        cache_read = u.get("cache_read_input_tokens", 0)
        cache_write = u.get("cache_creation_input_tokens", 0)
        return AgentOutput(
            final_output=str(d.get("result", "") or ""),
            token_usage=TokenUsage(
                input_tokens=inp,
                output_tokens=out,
                total_tokens=inp + out + cache_read + cache_write,
                cache_read=cache_read,
                cache_write=cache_write,
                cost_usd=d.get("total_cost_usd", 0.0) or 0.0,
            ),
        )

    def codex(self, stdout: str) -> AgentOutput:
        """codex exec --json: NDJSON stream; ``item.completed`` events carry agent text, ``turn.completed`` carries usage."""
        text_parts: list[str] = []
        usage = None
        for line in stdout.splitlines():
            d = self._load_json(line)
            if not isinstance(d, dict):
                continue
            if d.get("type") == "item.completed":
                item = d.get("item") or {}
                if item.get("type") == "agent_message" and item.get("text"):
                    text_parts.append(item["text"])
            elif d.get("type") == "turn.completed" and isinstance(d.get("usage"), dict):
                usage = d["usage"]
        if not text_parts and not usage:
            return AgentOutput(final_output=stdout.strip())
        u = usage or {}
        inp = u.get("input_tokens", 0)
        out = u.get("output_tokens", 0)
        reasoning = u.get("reasoning_output_tokens", 0)
        return AgentOutput(
            final_output="\n".join(text_parts),
            token_usage=TokenUsage(
                input_tokens=inp,
                output_tokens=out,
                total_tokens=inp + out + reasoning,
                cache_read=u.get("cached_input_tokens", 0),
            )
            if usage
            else None,
        )

    def gemini(self, stdout: str) -> AgentOutput:
        """gemini -o json: single object; ``response`` is the answer, ``stats.models.*.tokens`` summed for usage."""
        d = self._load_json(stdout)
        if not isinstance(d, dict):
            return AgentOutput(final_output=stdout.strip())
        models = (d.get("stats") or {}).get("models") or {}
        inp = out = total = cached = 0
        for info in models.values():
            t = (info or {}).get("tokens") or {}
            inp += t.get("input", 0)
            out += t.get("candidates", 0)
            total += t.get("total", 0)
            cached += t.get("cached", 0)
        has_usage = bool(models)
        return AgentOutput(
            final_output=str(d.get("response", "") or ""),
            token_usage=TokenUsage(
                input_tokens=inp,
                output_tokens=out,
                total_tokens=total or (inp + out),
                cache_read=cached,
            )
            if has_usage
            else None,
        )

    def qwen(self, stdout: str) -> AgentOutput:
        """qwen -o json: JSON array (or NDJSON) of events; ``assistant`` events carry text, ``result``/``assistant`` carry usage."""
        events = self._load_json(stdout)
        if not isinstance(events, list):
            events = [self._load_json(line) for line in stdout.splitlines()]
            events = [e for e in events if isinstance(e, dict)]
        if not events:
            return AgentOutput(final_output=stdout.strip())
        text_parts: list[str] = []
        usage = None
        for e in events:
            if e.get("type") == "assistant":
                msg = e.get("message") or {}
                for c in msg.get("content") or []:
                    if c.get("type") == "text" and c.get("text"):
                        text_parts.append(c["text"])
                if isinstance(msg.get("usage"), dict):
                    usage = msg["usage"]
            elif e.get("type") == "result" and isinstance(e.get("usage"), dict):
                usage = e["usage"]
        u = usage or {}
        inp, out = u.get("input_tokens", 0), u.get("output_tokens", 0)
        return AgentOutput(
            final_output="\n".join(text_parts),
            token_usage=TokenUsage(input_tokens=inp, output_tokens=out, total_tokens=inp + out)
            if usage
            else None,
        )

    def opencode(self, stdout: str) -> AgentOutput:
        """opencode run --format json: NDJSON stream; ``text`` events carry answer, ``step_finish`` events carry per-step tokens."""
        text_parts: list[str] = []
        inp = out = total = cache_r = cache_w = 0
        has_usage = False
        has_text = False
        for line in stdout.splitlines():
            d = self._load_json(line)
            if not isinstance(d, dict):
                continue
            if d.get("type") == "text":
                part = d.get("part") or {}
                if part.get("text"):
                    has_text = True
                    text_parts.append(part["text"])
            elif d.get("type") == "step_finish":
                t = ((d.get("part") or {}).get("tokens")) or {}
                if t:
                    has_usage = True
                    inp += t.get("input", 0)
                    out += t.get("output", 0)
                    total += t.get("total", 0)
                    cache = t.get("cache") or {}
                    cache_r += cache.get("read", 0)
                    cache_w += cache.get("write", 0)
        if not has_text and not has_usage:
            return AgentOutput(final_output=stdout.strip())
        return AgentOutput(
            final_output="\n".join(text_parts),
            token_usage=TokenUsage(
                input_tokens=inp,
                output_tokens=out,
                total_tokens=total or (inp + out),
                cache_read=cache_r,
                cache_write=cache_w,
            )
            if has_usage
            else None,
        )

    def pi(self, stdout: str) -> AgentOutput:
        """pi --mode json: NDJSON stream; ``text_end`` events carry complete text blocks, last ``message_*`` event carries usage."""
        text_parts: list[str] = []
        last_usage = None
        for line in stdout.splitlines():
            d = self._load_json(line)
            if not isinstance(d, dict):
                continue
            evt = d.get("assistantMessageEvent") or {}
            if d.get("type") == "message_update" and evt.get("type") == "text_end":
                if evt.get("content"):
                    text_parts.append(evt["content"])
            msg = d.get("message")
            if isinstance(msg, dict) and isinstance(msg.get("usage"), dict):
                last_usage = msg["usage"]
        if not text_parts and last_usage is None:
            return AgentOutput(final_output=stdout.strip())
        u = last_usage or {}
        cost = u.get("cost") or {}
        return AgentOutput(
            final_output="\n".join(text_parts),
            token_usage=TokenUsage(
                input_tokens=u.get("input", 0),
                output_tokens=u.get("output", 0),
                total_tokens=u.get("totalTokens", 0),
                cache_read=u.get("cacheRead", 0),
                cache_write=u.get("cacheWrite", 0),
                cost_usd=cost.get("total", 0.0) or 0.0,
            )
            if last_usage
            else None,
        )

    def openclaw(self, stdout: str) -> AgentOutput:
        """openclaw agent --local --json: object with ``payloads[].text`` (answer) + ``meta.agentMeta.usage`` (tokens).

        ``usage.total`` is not the cumulative processed total — it has been
        observed below ``input + output`` and excludes cache entirely — so it is
        recomputed from the component buckets like the Claude harness.
        """
        d = self._load_json(stdout)
        if not isinstance(d, dict):
            return AgentOutput(final_output=stdout.strip())
        meta = d.get("meta") or {}
        text = str(meta.get("finalAssistantVisibleText") or "")
        if not text:
            parts = [p.get("text", "") for p in (d.get("payloads") or []) if isinstance(p, dict)]
            text = "\n".join(p for p in parts if p)
        u = (meta.get("agentMeta") or {}).get("usage")
        inp = u.get("input", 0) if isinstance(u, dict) else 0
        out = u.get("output", 0) if isinstance(u, dict) else 0
        cache_read = u.get("cacheRead", 0) if isinstance(u, dict) else 0
        cache_write = u.get("cacheWrite", 0) if isinstance(u, dict) else 0
        return AgentOutput(
            final_output=text,
            token_usage=TokenUsage(
                input_tokens=inp,
                output_tokens=out,
                total_tokens=inp + out + cache_read + cache_write,
                cache_read=cache_read,
                cache_write=cache_write,
            )
            if isinstance(u, dict)
            else None,
        )

    def hermes(self, stdout: str, session_id: str, cwd: str | None = None) -> AgentOutput:
        """hermes -z: plain-text answer on stdout; tokens fetched from the session store.

        Args:
            stdout: the agent's plain-text stdout (the answer).
            session_id: the hermes session id to fetch token usage for.
            cwd: working directory for the export subprocess.
        """
        final_output = stdout.strip()
        usage = None
        try:
            r = subprocess.run(
                ["hermes", "sessions", "export", "-", "--session-id", session_id],
                capture_output=True,
                text=True,
                timeout=self._hermes_timeout_s,
                cwd=cwd,
            )
            if r.returncode == 0:
                d = self._load_json(r.stdout)
                if isinstance(d, dict):
                    inp, out = d.get("input_tokens", 0), d.get("output_tokens", 0)
                    usage = TokenUsage(
                        input_tokens=inp,
                        output_tokens=out,
                        total_tokens=inp + out,
                        cost_usd=d.get("estimated_cost_usd", 0.0) or 0.0,
                    )
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            pass
        return AgentOutput(final_output=final_output, token_usage=usage)

    def _hermes_latest_session(self, cwd: str | None = None) -> str | None:
        """Find the most recent hermes session id via ``hermes sessions list``."""
        try:
            r = subprocess.run(
                ["hermes", "sessions", "list"],
                capture_output=True,
                text=True,
                timeout=self._hermes_timeout_s,
                cwd=cwd,
            )
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            return None
        if r.returncode != 0:
            return None
        for line in r.stdout.splitlines():
            line = line.strip()
            if (
                not line
                or line.startswith("Title")
                or line.startswith("Preview")
                or line.startswith("─")
            ):
                continue
            parts = line.split()
            if parts:
                return parts[-1]
        return None

    @staticmethod
    def _load_json(text: str) -> dict | list | None:
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None
