"""Base types and registry for transcription backends."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class TranscriptionSegment:
    """Single segment of a transcription result."""

    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    """Result of a transcription run."""

    text: str
    segments: list[TranscriptionSegment] = field(default_factory=list)
    language: str = ""
    language_probability: float = 0.0
    elapsed_ms: float = 0.0
    model_size: str = ""
    device: str = ""
    backend: str = ""


BackendLabel = Literal["mlx", "ctranslate2", "openai"]


class TranscriptionBackend(abc.ABC):
    """Abstract base for pluggable transcription backends.

    Subclasses set ``name`` and ``priority`` (lower = preferred), implement
    ``available()`` to probe the current system, and ``transcribe()`` to
    run inference.
    """

    name: BackendLabel
    priority: int

    @abc.abstractmethod
    def available(self) -> bool:
        """Return True if this backend can run on the current system."""

    @abc.abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        *,
        model: str = "tiny",
        language: str | None = None,
        beam_size: int = 1,
        audio_speed: float = 1.0,
    ) -> TranscriptionResult:
        """Transcribe an audio file and return a result."""


_BACKENDS: list[TranscriptionBackend] = []
_ACTIVE: TranscriptionBackend | None = None
_DETECTED = False


def register_backend(backend: TranscriptionBackend) -> None:
    """Add a backend to the registry (sorted by priority on access)."""
    _BACKENDS.append(backend)


def list_backends() -> list[tuple[str, bool]]:
    """Return ``(name, available)`` for every registered backend."""
    return [(b.name, b.available()) for b in sorted(_BACKENDS, key=lambda b: b.priority)]


def detect_backend(
    *,
    name: BackendLabel | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> TranscriptionBackend | None:
    """Find a backend by name, or auto-detect the best available one.

    When *name* is given the named backend is returned (even if
    ``available()`` is False — the caller requested it explicitly).

    When *name* is ``None`` the registry is walked in priority order and
    the first backend whose ``available()`` returns ``True`` is returned
    and cached for subsequent calls.
    """
    global _ACTIVE, _DETECTED

    if name is not None:
        for b in _BACKENDS:
            if b.name == name:
                if base_url is not None or api_key is not None:
                    b = _clone_with_url(b, base_url=base_url, api_key=api_key)
                return b
        return None

    if _DETECTED:
        return _ACTIVE

    for b in sorted(_BACKENDS, key=lambda b: b.priority):
        if b.available():
            _ACTIVE = b
            _DETECTED = True
            return b

    _DETECTED = True
    return None


def transcribe_available() -> bool:
    """Return True if at least one local backend can run."""
    return any(b.available() for b in _BACKENDS if b.name != "openai")


def _reset() -> None:
    """Reset cached detection (for testing)."""
    global _ACTIVE, _DETECTED
    _ACTIVE = None
    _DETECTED = False


def _clone_with_url(
    backend: TranscriptionBackend,
    *,
    base_url: str | None,
    api_key: str | None,
) -> TranscriptionBackend:
    """Return a copy of *backend* with overridden URL/key (OpenAI only)."""
    from mm.common.audio._openai import OpenAIBackend

    if isinstance(backend, OpenAIBackend):
        return OpenAIBackend(
            base_url=base_url or backend._base_url,
            api_key=api_key or backend._api_key,
        )
    return backend
