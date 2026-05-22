"""Encoder abstract base class for all built-in media encoders.

Defines the contract that every encoder must satisfy:

- ``name`` — registry key.
- ``kind`` — the :data:`~mm.constants.BinaryFileKind` this encoder handles.
- ``generate`` — per-mode :class:`~mm.pipelines.schema.Generate` overrides
  that take precedence over the pipeline YAML's ``generate`` block.
- ``encode()`` — transforms a file into OpenAI-compatible Message dicts.

Resolution order (highest priority first)::

    CLI flags (--generate.*)
    → encoder ``generate[mode]`` override
    → pipeline YAML ``generate`` block

``Message`` is re-exported here so encoder submodules can import it from
one place::

    from mm.encoders.base import Encoder, Message
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar, Iterable

from mm.cat_utils.base_utils import CatMode
from mm.constants import BinaryFileKind
from mm.pipelines.schema import Generate

Message = dict[str, Any]  # OpenAI-compatible message dict: ``{"role": "user", "content": [...]}``.


class Encoder(ABC):
    """Abstract base for media encoders.

    Subclasses must set :attr:`name` and :attr:`kind` as class variables and
    implement :meth:`encode`. The optional :attr:`generate` dict lets each
    encoder declare per-mode generate overrides that take precedence over the
    pipeline YAML's ``generate`` block.

    **Passthrough encoder** (suppresses the LLM call for both modes)::

        class MyTextEncoder(Encoder):
            name = "my-text"
            kind = "document"
            generate = {"fast": None, "accurate": None}

            def encode(self, path, **kwargs):
                yield {"role": "user", "content": [{"type": "text", "text": path.read_text()}]}

    Encoders with no ``generate`` override (the default, ``{}``) defer
    entirely to the pipeline YAML. Only declare ``generate`` when the
    encoder genuinely needs to diverge from the YAML default — for
    example, to suppress the LLM call entirely (passthrough) or to use
    prompts that are fundamentally incompatible with the shared YAML block.
    Duplicating YAML content here is an anti-pattern.
    """

    name: ClassVar[str]
    kind: ClassVar[BinaryFileKind]
    generate: ClassVar[dict[CatMode, Generate | None]] = {}

    @abstractmethod
    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        """Transform a file into one or more OpenAI-compatible Message dicts.

        Args:
            path: Absolute path to the source file.
            **kwargs: Encoder-specific parameters from ``encode.strategy_opts``
                plus ``mode`` (the active pipeline mode: ``"fast"`` or ``"accurate"``).

        Yields:
            OpenAI-compatible Message dicts. Each dict is independently
            sendable to a VLM, enabling parallel inference over tiles or
            video chunks.
        """
        ...
