"""Base types and registry for transcription backends.

Third-party backends can subclass :class:`TranscriptionBackend` and
call :func:`register_backend` to add themselves to the registry.

Example — a Gemini backend using the OpenAI-compatible endpoint
(https://ai.google.dev/gemini-api/docs/openai#audio-understanding)::

    from pathlib import Path
    from mm.common.audio import (
        TranscriptionBackend, TranscriptionResult, register_backend,
    )

    class GeminiBackend(TranscriptionBackend):
        name = "gemini"

        GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"

        def __init__(self, *, api_key: str | None = None) -> None:
            self._api_key = api_key

        def available(self) -> bool:
            return self._api_key is not None

        def clone_with_config(self, *, base_url=None, api_key=None):
            return GeminiBackend(api_key=api_key or self._api_key)

        def transcribe(
            self,
            audio_path: Path,
            *,
            model: str | None = None,
            language: str | None = None,
            beam_size: int = 1,
            audio_speed: float = 1.0,
        ) -> TranscriptionResult:
            from openai import OpenAI

            client = OpenAI(
                base_url=self.GEMINI_BASE_URL,
                api_key=self._api_key,
            )
            with open(audio_path, "rb") as f:
                resp = client.audio.transcriptions.create(
                    model=model or "gemini-2.0-flash",
                    file=f,
                    response_format="verbose_json",
                )
            return TranscriptionResult(
                text=getattr(resp, "text", ""),
                backend="gemini",
            )

    register_backend(GeminiBackend(api_key="..."))

Then use it via ``mm cat audio.mp3 --encode.backend gemini``.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path

#: Backend name.  Built-in values are ``"openai"``, ``"mlx"``, and
#: ``"ctranslate2"``, but any string is accepted for custom backends.
BackendLabel = str


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


class TranscriptionBackend(abc.ABC):
    """Abstract base for pluggable transcription backends.

    Subclasses must set :attr:`name` (any unique string) and implement
    :meth:`available` and :meth:`transcribe`.

    Override :meth:`clone_with_config` if the backend supports
    runtime ``base_url`` / ``api_key`` overrides (like the built-in
    ``openai`` backend does).

    See the module docstring for a full Gemini example.
    """

    name: str

    @abc.abstractmethod
    def available(self) -> bool:
        """Return ``True`` if this backend can run on the current system."""

    @abc.abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        *,
        model: str | None = None,
        language: str | None = None,
        beam_size: int = 1,
        audio_speed: float = 1.0,
    ) -> TranscriptionResult:
        """Transcribe an audio file and return a result."""

    def clone_with_config(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> TranscriptionBackend:
        """Return a copy of this backend with overridden URL / key.

        The default implementation returns ``self`` unchanged — only
        backends that accept remote configuration need to override this.
        """
        return self


_BACKENDS: list[TranscriptionBackend] = []
_ACTIVE: TranscriptionBackend | None = None
_DETECTED = False


def register_backend(backend: TranscriptionBackend) -> None:
    """Add a backend to the registry, replacing any existing backend with the same name."""
    for i, b in enumerate(_BACKENDS):
        if b.name == backend.name:
            _BACKENDS[i] = backend
            return
    _BACKENDS.append(backend)


def unregister_backend(name: str) -> bool:
    """Remove a backend by name. Returns ``True`` if it was found."""
    global _ACTIVE, _DETECTED
    for i, b in enumerate(_BACKENDS):
        if b.name == name:
            _BACKENDS.pop(i)
            if _ACTIVE is not None and _ACTIVE.name == name:
                _ACTIVE = None
                _DETECTED = False
            return True
    return False


def list_backends() -> list[tuple[str, bool]]:
    """Return ``(name, available)`` for every registered backend."""
    return [(b.name, b.available()) for b in _BACKENDS]


def detect_backend(
    *,
    name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> TranscriptionBackend | None:
    """Find a backend by name, or return the default (openai) backend.

    When *name* is given the named backend is returned (even if
    ``available()`` is False — the caller requested it explicitly).

    When *name* is ``None`` the ``openai`` backend is returned.
    Local backends (mlx, ctranslate2) are never auto-selected — the
    user must explicitly request them via ``--encode.backend``.
    """
    global _ACTIVE, _DETECTED

    if name is not None:
        for b in _BACKENDS:
            if b.name == name:
                if base_url is not None or api_key is not None:
                    b = b.clone_with_config(base_url=base_url, api_key=api_key)
                return b
        return None

    if _DETECTED:
        return _ACTIVE

    for b in _BACKENDS:
        if b.name == "openai" and b.available():
            _ACTIVE = b
            _DETECTED = True
            return b

    _DETECTED = True
    return None


def transcribe_available() -> bool:
    """Return True if at least one backend (local or remote) can run."""
    return any(b.available() for b in _BACKENDS)


def _reset() -> None:
    """Reset cached detection (for testing)."""
    global _ACTIVE, _DETECTED
    _ACTIVE = None
    _DETECTED = False
