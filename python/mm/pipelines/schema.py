"""Pydantic schema for YAML-based MLLM generation pipelines.

Each pipeline configures a 2-stage flow:

    file → encode → generate (LLM) → text output

Pipelines live in ``python/mm/pipelines/{kind}/{mode}.yaml`` and are
validated at load time against these models.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Encode(BaseModel, extra="allow"):
    """Input encoding: how to convert a file into LLM-ready parts.

    The ``strategy`` field selects a registered encoder (e.g.
    ``resize``, ``frame-sample``, ``rasterize``).  All other fields
    are forwarded as kwargs to ``encoder.encode()``.

    ``pyfunc`` allows inline Python to transform/filter the parts list
    before it reaches the LLM.  Signature:
        def transform(parts: list[dict], context: dict) -> list[dict]
    """

    strategy: str | None = Field(
        default=None,
        description="Encoder name (e.g. resize, tile, frame-sample). "
        "None = use kind-specific default.",
    )
    pyfunc: str | None = Field(
        default=None,
        description="Inline Python function body for custom transform. "
        "Receives (parts, context) and must return list[dict].",
    )

    @property
    def encoder_kwargs(self) -> dict[str, Any]:
        """All extra fields beyond strategy/pyfunc, forwarded to the encoder."""
        if self.model_extra:
            return dict(self.model_extra)
        return {}


class Generate(BaseModel):
    """LLM generation parameters.

    The ``prompt`` is a Python format string that receives the ``context``
    dict, so you can use ``{filename}``, ``{duration}``, ``{kind}`` etc.
    """

    prompt: str = Field(
        description="System/user prompt template. Supports {filename}, "
        "{kind}, {duration}, {word_count} interpolation from context.",
    )
    max_tokens: int = Field(
        default=256,
        description="Max completion tokens.",
    )
    temperature: float | None = Field(
        default=None,
        description="Sampling temperature. None = use model default (0.1).",
    )
    json_mode: bool = Field(
        default=False,
        description="Request JSON-formatted response from the model.",
    )


class PipelineSpec(BaseModel):
    """Complete pipeline for a single (kind, mode) processing call.

    When ``generate`` is ``None`` the pipeline is encode-only — no LLM
    call is made and the raw extraction output is returned directly.
    """

    kind: str = Field(description="Media kind: image, video, audio, document.")
    mode: str = Field(description="Processing mode: fast, accurate.")
    encode: Encode = Field(default_factory=Encode)
    generate: Generate | None = Field(default=None)


TemplateSpec = PipelineSpec
