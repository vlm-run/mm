"""Lightweight schema types for YAML-based MLLM generation pipelines.

Each pipeline configures a 2-stage flow:

    file → encode → generate (LLM) → text output

Pipelines live in ``python/mm/pipelines/{kind}/{mode}.yaml`` and are
parsed with :func:`PipelineSpec.from_dict`. Validation failures raise
:class:`PipelineValidationError` (a plain ``ValueError`` subclass).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any


class PipelineValidationError(ValueError):
    """Raised when a pipeline dict fails schema validation."""


_MISSING = object()


@dataclass
class Encode:
    """Input encoding stage: how to convert a file into LLM-ready parts.

    ``strategy`` selects a registered encoder (e.g. ``resize``,
    ``frame-sample``, ``rasterize``). Encoder-specific parameters live
    nested under ``strategy_opts`` and are forwarded as kwargs to
    ``encoder.encode()``.

    ``pyfunc`` allows inline Python to transform/filter the parts list
    before it reaches the LLM. Signature::

        def transform(parts: list[dict], context: dict) -> list[dict]
    """

    strategy: str | None = None
    pyfunc: str | None = None
    strategy_opts: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Encode":
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise PipelineValidationError(
                f"encode must be a mapping, got {type(data).__name__}"
            )
        opts = data.get("strategy_opts") or {}
        if not isinstance(opts, dict):
            raise PipelineValidationError(
                f"encode.strategy_opts must be a mapping, got {type(opts).__name__}"
            )
        return cls(
            strategy=data.get("strategy"),
            pyfunc=data.get("pyfunc"),
            strategy_opts=dict(opts),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.strategy is not None:
            out["strategy"] = self.strategy
        if self.pyfunc is not None:
            out["pyfunc"] = self.pyfunc
        if self.strategy_opts:
            out["strategy_opts"] = dict(self.strategy_opts)
        return out


@dataclass
class Generate:
    """LLM generation parameters.

    The ``prompt`` is a Python format string that receives the ``context``
    dict, so you can use ``{filename}``, ``{duration}``, ``{kind}`` etc.
    """

    prompt: str
    max_tokens: int = 256
    temperature: float | None = None
    json_mode: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Generate | None":
        if data is None:
            return None
        if not isinstance(data, dict):
            raise PipelineValidationError(
                f"generate must be a mapping or null, got {type(data).__name__}"
            )
        if "prompt" not in data:
            raise PipelineValidationError("generate.prompt is required")
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "json_mode": self.json_mode,
        }


@dataclass
class PipelineSpec:
    """Complete pipeline for a single (kind, mode) processing call.

    When ``generate`` is ``None`` the pipeline is encode-only — no LLM
    call is made and the raw extraction output is returned directly.
    """

    kind: str
    mode: str
    encode: Encode = field(default_factory=Encode)
    generate: Generate | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipelineSpec":
        if not isinstance(data, dict):
            raise PipelineValidationError(
                f"pipeline must be a mapping, got {type(data).__name__}"
            )
        kind = data.get("kind", _MISSING)
        mode = data.get("mode", _MISSING)
        if kind is _MISSING:
            raise PipelineValidationError("pipeline.kind is required")
        if mode is _MISSING:
            raise PipelineValidationError("pipeline.mode is required")
        encode = Encode.from_dict(data.get("encode"))
        generate = Generate.from_dict(data.get("generate")) if "generate" in data else None
        return cls(kind=kind, mode=mode, encode=encode, generate=generate)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "kind": self.kind,
            "mode": self.mode,
            "encode": self.encode.to_dict(),
        }
        out["generate"] = self.generate.to_dict() if self.generate is not None else None
        return out
