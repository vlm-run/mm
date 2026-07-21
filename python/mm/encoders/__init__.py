"""Media encoders for VLM-ready message generation.

Encoders transform media files (images, videos, documents, audio) into
OpenAI-compatible Message dicts ready for chat/completions APIs. Each
encoder is registered by name and referenced from pipeline YAMLs via
the ``encode.strategy`` field.

Built-in encoders extend the :class:`~mm.encoders.base.Encoder` ABC.
Custom function-based encoders use the :func:`register_encoder` decorator::

    from mm.encoders import register_encoder

    @register_encoder(name="my_custom", kind="image")
    def my_custom(path, **kw):
        ...
        yield {"role": "user", "content": [...]}

User-defined encoder files placed in ``~/.config/mm/encoders/*.py`` are
auto-discovered and registered at import time.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path
from typing import Any, Iterable, Protocol, runtime_checkable

from mm.encoders.base import Encoder, Message, to_message

__all__ = [
    "Encoder",
    "Message",
    "MessageStrategy",
    "register",
    "register_encoder",
    "get",
    "to_message",
]


@runtime_checkable
class MessageStrategy(Protocol):
    """Interface that all encoding strategies must satisfy.

    Attributes:
        name: Short identifier used with ``-s`` on the CLI.
        kind: media kind this strategy handles (e.g. `"image"`, `"video"`).
    """

    name: str
    kind: str

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        """Encode a media file into one or more Message dicts.

        Args:
            path: Absolute path to the source file.
            **kwargs: Strategy-specific parameters (``max_width``,
                ``tile_size``, ``fps``, etc.).

        Yields:
            OpenAI-compatible Message dicts.  Each dict is independently
            sendable to a VLM, which enables parallel inference over tiles
            or video chunks.
        """
        ...


_REGISTRY: dict[str, MessageStrategy] = {}
_DISCOVERED = False
_DISCOVERY_LOCK = threading.Lock()
_LOADED_SOURCES: dict[str, list[str]] = {}
"""Maps a source key (file path or code hash) to the encoder names it registered."""


def register(strat: MessageStrategy) -> MessageStrategy:
    """Add an encoder instance to the global registry.

    Args:
        strat: Any object satisfying the ``MessageStrategy`` protocol.

    Returns:
        The same encoder, for use as a decorator return value.
    """
    _REGISTRY[f"{strat.kind}/{strat.name}"] = strat
    return strat


def get(name: str, kind: str) -> MessageStrategy:
    """Look up a registered encoder by name.

    Args:
        name: Encoder name (e.g. ``"mosaic"``, ``"resize"``).
        kind: Media kind. Required when ``name`` is shared across kinds
            (e.g. ``"gemini-native"`` exists for audio, video, and document).

    Raises:
        KeyError: If no encoder matches.
    """
    _ensure_discovered()
    key = f"{kind}/{name}"
    if key in _REGISTRY:
        return _REGISTRY[key]
    available = ", ".join(f"{k.split('/')[1]} [{k.split('/')[0]}]" for k in sorted(_REGISTRY))
    raise KeyError(f"Unknown encoder {name!r}. Available: {available}")


def list_strategies(*, kind: str | None = None) -> list[str]:
    """Return sorted names of all registered encoders.

    Args:
        kind: If given, only return encoders that handle this
            kind := (``"image"``, ``"audio"``, ``"video"``, ``"document"``).
    """
    _ensure_discovered()
    if kind is not None:
        return sorted(enc.name for enc in _REGISTRY.values() if enc.kind == kind)
    return sorted({enc.name for enc in _REGISTRY.values()})


def _encoder_description(strat: MessageStrategy) -> str:
    """Extract a one-line description from an encoder's class docstring."""
    doc = getattr(strat, "__doc__", None) or getattr(type(strat), "__doc__", None) or ""
    first_line = doc.strip().split("\n")[0].strip() if doc.strip() else ""
    return first_line.rstrip(".")


def _encoder_params(strat: MessageStrategy) -> list[tuple[str, str]]:
    """Extract (param_name, default_value) pairs from the encode() method body.

    Looks for ``kwargs.get("param", default)`` patterns in the source.
    """
    import inspect
    import re

    results: list[tuple[str, str]] = []
    try:
        src = inspect.getsource(
            type(strat).encode if hasattr(type(strat), "encode") else strat.encode
        )
    except (TypeError, OSError):
        return results

    for m in re.finditer(r'kwargs\.get\(\s*["\'](\w+)["\']\s*,\s*([^)]+)\)', src):
        param_name = m.group(1)
        default = m.group(2).strip().strip("\"'")
        if param_name == "provider" or param_name.startswith("_"):
            continue
        results.append((param_name, default))
    return results


def list_encoders_detail(*, kind: str | None = None) -> list[dict[str, Any]]:
    """Return structured info for all registered encoders.

    Each entry contains ``name``, ``kind``, ``description``, and
    ``params`` (list of ``(param_name, default_value)`` tuples).
    """
    _ensure_discovered()
    entries: list[dict[str, Any]] = []
    for key in sorted(_REGISTRY):
        s = _REGISTRY[key]
        if kind and kind != s.kind:
            continue
        entries.append(
            {
                "name": s.name,
                "kind": s.kind,
                "description": _encoder_description(s),
                "params": _encoder_params(s),
            }
        )
    return sorted(entries, key=lambda e: (e["kind"], e["name"]))


class _FunctionEncoder:
    """Adapts a bare generator function into a ``MessageStrategy``."""

    __slots__ = ("name", "kind", "_fn")

    def __init__(self, name: str, kind: str, fn: Any) -> None:
        self.name = name
        self.kind = kind
        self._fn = fn

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        result: Iterable[Message] = self._fn(path, **kwargs)
        return result


def register_encoder(name: str, kind: str):
    """Decorator that turns a generator function into a registered encoder.

    The ``name`` is optional — if omitted, it is derived from the
    function name by replacing underscores with hyphens.

    Examples::

        @register_encoder(kind="image")
        def my_resize(path, **kw):
            ...
            yield {"role": "user", "content": [...]}
        # Registered as "my-resize"

        @register_encoder(name="custom-name", kind="video")
        def whatever(path, **kw):
            ...

    Args:
        name: Registry key.  Defaults to the function name with
            underscores replaced by hyphens.
        kind: kind this encoder handles.
    """

    def decorator(fn: Any) -> _FunctionEncoder:
        resolved_name = name if name is not None else fn.__name__.replace("_", "-")
        s = _FunctionEncoder(resolved_name, kind, fn)
        register(s)
        return s

    return decorator


strategy = register_encoder
"""Backward-compatible alias for ``register_encoder``."""


def load_strategy_file(path: Path) -> list[str]:
    """Dynamically import a ``.py`` file and register its encoders.

    Any ``@register_encoder``-decorated functions in the file are automatically
    registered when the module is executed.  Results are cached so
    repeated loads of the same file return the same names without
    re-executing.

    Args:
        path: Absolute or relative path to a Python file.

    Returns:
        List of encoder names registered from this file.

    Raises:
        ImportError: If the file cannot be loaded.
    """
    source_key: str = str(path.resolve())
    if source_key in _LOADED_SOURCES:
        return _LOADED_SOURCES[source_key]

    resolved = path.resolve()
    for mod in sys.modules.values():
        mod_file = getattr(mod, "__file__", None)
        if mod_file and Path(mod_file).resolve() == resolved:
            _LOADED_SOURCES[source_key] = []
            return []

    before = set(_REGISTRY)
    module_name = f"mm_encoder_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load encoder from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    after = set(_REGISTRY)
    names = sorted(after - before)
    _LOADED_SOURCES[source_key] = names
    return names


def _ensure_discovered() -> None:
    """Lazily register built-in encoders and run auto-discovery."""
    global _DISCOVERED
    if _DISCOVERED:
        return
    with _DISCOVERY_LOCK:
        if _DISCOVERED:
            return
        _register_builtins()
        discover_encoders()
        _DISCOVERED = True


def _register_builtins() -> None:
    """Import built-in encoder modules so their classes self-register."""
    from mm.encoders import audio, document, gemini, image, video  # noqa: F401
    from mm.encoders.document import (  # noqa: F401
        document_url,
        native as _doc_native,
        page_text,
        rasterize,
    )
    from mm.encoders.video import (  # noqa: F401
        captions,
        chunks,
        clips,
        frames,
        keyframes,
        mosaic,
        native,
        shots,
        summary,
        transcript,
    )


def discover_encoders() -> None:
    """Scan known directories for user-defined encoder files.

    Discovery order:
        1. ``python/mm/encoders/{image,video}/*.py`` (project-level subdirs)
        2. ``~/.config/mm/encoders/*.py`` (per-user, not in repo)

    Top-level ``.py`` files in the project encoders directory are
    registered by ``_register_builtins`` and are skipped here.
    """
    project_dir = _project_encoders_dir()
    if project_dir is not None:
        for subdir in sorted(project_dir.iterdir()):
            if subdir.is_dir() and not subdir.name.startswith("_"):
                _discover_from_dir(subdir)
    _discover_from_dir(_user_encoders_dir())


def _discover_from_dir(directory: Path | None) -> None:
    if directory is None or not directory.is_dir():
        return
    for py_file in sorted(directory.rglob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            load_strategy_file(py_file)
        except Exception:
            pass


def _project_encoders_dir() -> Path | None:
    """Return the encoders package directory for auto-discovery.

    Only subdirectories (image/, video/) are scanned — top-level
    modules (document.py, gemini.py) are imported by _register_builtins.
    """
    d = Path(__file__).resolve().parent
    return d if d.is_dir() else None


def _user_encoders_dir() -> Path | None:
    from mm.settings import get_settings

    d = get_settings().config_dir / "encoders"
    return d if d.is_dir() else None


def resolve_provider(model: str | None = None) -> str:
    """Infer the message format from the active LLM profile.

    Returns:
        ``"gemini"`` if the active profile name contains *gemini*,
        otherwise ``"openai"``.
    """
    try:
        from mm.profile import get_active_profile_name, get_profile_by_name

        name = get_active_profile_name()
        profile = get_profile_by_name(name)
        _model = (model or profile["model"] or "").lower()

        for kw in ("gemini", "google", "gemma"):
            if kw in f"{name.lower()}:{(_model)}":
                return "gemini"
    except Exception:
        pass

    return "openai"
