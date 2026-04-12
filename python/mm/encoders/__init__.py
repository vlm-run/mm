"""Media encoders for VLM-ready message generation.

Encoders transform media files (images, videos, documents) into
OpenAI-compatible Message dicts ready for chat/completions APIs.

Three ways to use an encoder:
    1. Named:  ``mm cat photo.png -s resize``
    2. File:   ``mm cat photo.png -s ~/my_encoder.py``
    3. Inline: ``mm cat photo.png -s 'def encode(path, **kw): ...'``

Custom encoders use the ``@register_encoder`` decorator::

    from mm.encoders import register_encoder

    @register_encoder(name="my_custom", media_types=("image",))
    def my_custom(path, **kw):
        ...
        yield {"role": "user", "content": [...]}
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Protocol, runtime_checkable

if TYPE_CHECKING:
    from PIL import Image

Message = dict[str, Any]
"""OpenAI-compatible message dict: ``{"role": "user", "content": [...]}``."""


@runtime_checkable
class MessageStrategy(Protocol):
    """Interface that all encoding strategies must satisfy.

    Attributes:
        name: Short identifier used with ``-s`` on the CLI.
        media_types: Tuple of media kinds this strategy handles
            (e.g. ``("image",)``, ``("video",)``).
    """

    name: str
    media_types: tuple[str, ...]

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
_LOADED_SOURCES: dict[str, list[str]] = {}
"""Maps a source key (file path or code hash) to the encoder names it registered."""


def register(strat: MessageStrategy) -> MessageStrategy:
    """Add an encoder instance to the global registry.

    Args:
        strat: Any object satisfying the ``MessageStrategy`` protocol.

    Returns:
        The same encoder, for use as a decorator return value.
    """
    _REGISTRY[strat.name] = strat
    return strat


def get(name: str) -> MessageStrategy:
    """Look up a registered encoder by name.

    Args:
        name: Encoder identifier (e.g. ``"resize"``).

    Raises:
        KeyError: If no encoder with that name is registered.
    """
    _ensure_discovered()
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"Unknown encoder {name!r}. Available: {available}")
    return _REGISTRY[name]


def list_strategies(*, media_type: str | None = None) -> list[str]:
    """Return sorted names of all registered encoders.

    Args:
        media_type: If given, only return encoders that handle this
            kind (``"image"``, ``"video"``, ``"document"``).
    """
    _ensure_discovered()
    if media_type is None:
        return sorted(_REGISTRY)
    return sorted(
        name
        for name, s in _REGISTRY.items()
        if media_type in s.media_types
    )


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
        src = inspect.getsource(type(strat).encode if hasattr(type(strat), "encode") else strat.encode)
    except (TypeError, OSError):
        return results

    for m in re.finditer(r'kwargs\.get\(\s*["\'](\w+)["\']\s*,\s*([^)]+)\)', src):
        param_name = m.group(1)
        default = m.group(2).strip().strip("\"'")
        if param_name == "provider" or param_name.startswith("_"):
            continue
        results.append((param_name, default))
    return results


def list_encoders_detail(*, media_type: str | None = None) -> list[dict[str, Any]]:
    """Return structured info for all registered encoders.

    Each entry contains ``name``, ``media_types``, ``description``, and
    ``params`` (list of ``(param_name, default_value)`` tuples).
    """
    _ensure_discovered()
    entries: list[dict[str, Any]] = []
    for name in sorted(_REGISTRY):
        s = _REGISTRY[name]
        if media_type and media_type not in s.media_types:
            continue
        media_prefix = s.media_types[0] if s.media_types else "unknown"
        entries.append({
            "name": name,
            "prefixed_name": f"{media_prefix}-{name}" if not name.startswith(media_prefix) else name,
            "media_types": s.media_types,
            "description": _encoder_description(s),
            "params": _encoder_params(s),
        })
    return sorted(entries, key=lambda e: e["prefixed_name"])


class _FunctionEncoder:
    """Adapts a bare generator function into a ``MessageStrategy``."""

    __slots__ = ("name", "media_types", "_fn")

    def __init__(self, name: str, media_types: tuple[str, ...], fn: Any) -> None:
        self.name = name
        self.media_types = media_types
        self._fn = fn

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        result: Iterable[Message] = self._fn(path, **kwargs)
        return result


def register_encoder(
    name: str | None = None,
    media_types: tuple[str, ...] = ("image",),
):
    """Decorator that turns a generator function into a registered encoder.

    The ``name`` is optional — if omitted, it is derived from the
    function name by replacing underscores with hyphens.

    Examples::

        @register_encoder(media_types=("image",))
        def my_resize(path, **kw):
            ...
            yield {"role": "user", "content": [...]}
        # Registered as "my-resize"

        @register_encoder(name="custom-name", media_types=("video",))
        def whatever(path, **kw):
            ...

    Args:
        name: Registry key.  Defaults to the function name with
            underscores replaced by hyphens.
        media_types: Tuple of media kinds this encoder handles.
    """

    def decorator(fn: Any) -> _FunctionEncoder:
        resolved_name = name if name is not None else fn.__name__.replace("_", "-")
        s = _FunctionEncoder(resolved_name, media_types, fn)
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


def load_inline_strategy(code: str) -> list[str]:
    """Execute inline Python code and register its encoders.

    The executed code has access to the ``register_encoder`` decorator
    (also available as ``strategy``) and ``pathlib.Path``.  Intended
    for agent-generated code passed via ``mm cat -s '<code>'``.
    Results are cached by code content so repeated calls with
    identical code skip re-execution.

    Args:
        code: Python source code containing ``@register_encoder``-decorated
            functions.

    Returns:
        List of encoder names registered from this code.
    """
    import hashlib

    source_key: str = f"inline:{hashlib.sha256(code.encode()).hexdigest()[:16]}"
    if source_key in _LOADED_SOURCES:
        return _LOADED_SOURCES[source_key]

    before = set(_REGISTRY)
    exec_globals: dict[str, Any] = {
        "register_encoder": register_encoder,
        "strategy": strategy,
        "Path": Path,
        "__builtins__": __builtins__,
    }
    exec(code, exec_globals)  # noqa: S102
    after = set(_REGISTRY)
    names = sorted(after - before)
    _LOADED_SOURCES[source_key] = names
    return names


def _ensure_discovered() -> None:
    """Lazily register built-in encoders and run auto-discovery."""
    global _DISCOVERED
    if _DISCOVERED:
        return
    _DISCOVERED = True
    _register_builtins()
    discover_encoders()


def _register_builtins() -> None:
    """Import built-in encoder modules so their classes self-register."""
    from mm.encoders import audio, document, gemini, image, video  # noqa: F401
    from mm.encoders.document import page_text  # noqa: F401
    from mm.encoders.video import frame_sample_transcript, mosaic  # noqa: F401


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
    d = Path.home() / ".config" / "mm" / "encoders"
    return d if d.is_dir() else None


def resolve_strategy(value: str, media_type: str) -> MessageStrategy:
    """Resolve a ``-s`` CLI value to a concrete ``MessageStrategy``.

    Detection logic applied to *value*:
        1. Contains ``def `` or ``lambda`` -- treated as inline Python.
        2. Ends with ``.py`` or contains ``/`` -- treated as a file path.
        3. Otherwise -- looked up by name in the registry.

    Args:
        value: The raw ``-s`` argument from the CLI.
        media_type: Media kind of the target file (used to disambiguate
            when a loaded file defines multiple encoders).

    Returns:
        A ``MessageStrategy`` ready to call ``.encode()``.

    Raises:
        KeyError: Named encoder not found.
        FileNotFoundError: Encoder file does not exist.
        ValueError: Loaded file/code registered no encoders.
    """
    _ensure_discovered()

    if "def " in value or "lambda " in value:
        names = load_inline_strategy(value)
        return _pick_by_media_type(names, media_type, source="inline code")

    if value.endswith(".py") or "/" in value:
        path = Path(value).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Encoder file not found: {path}")
        names = load_strategy_file(path)
        return _pick_by_media_type(names, media_type, source=str(path))

    return get(value)


def _pick_by_media_type(
    names: list[str], media_type: str, source: str
) -> MessageStrategy:
    """Select the best-matching encoder from a list of registered names.

    Args:
        names: Encoder names registered from *source*.
        media_type: Target media kind to match against.
        source: Human-readable description of the source (for errors).

    Raises:
        ValueError: If *names* is empty (nothing was registered).
    """
    if not names:
        raise ValueError(f"No encoders registered from {source}")
    matching = [n for n in names if media_type in _REGISTRY[n].media_types]
    if matching:
        return _REGISTRY[matching[0]]
    return _REGISTRY[names[0]]


def _resolve_provider() -> str:
    """Infer the message format from the active LLM profile.

    Returns:
        ``"gemini"`` if the active profile name contains *gemini*,
        otherwise ``"openai"``.
    """
    try:
        from mm.profile import get_active_profile_name

        name = get_active_profile_name()
        return "gemini" if "gemini" in name.lower() else "openai"
    except Exception:
        return "openai"


def process_image(
    image: Path | Image.Image,
    *,
    strategy_name: str = "resize",
    max_width: int = 1024,
    **kwargs: Any,
) -> Message:
    """Encode a single image and return an OpenAI-compatible Message.

    Args:
        image: Path to an image file, or a PIL ``Image`` object.
        strategy_name: Registry name of the encoder to use.
        max_width: Maximum width in pixels (passed to the encoder).
        **kwargs: Forwarded to ``encoder.encode()``.

    Returns:
        A single Message dict ``{"role": "user", "content": [...]}``.
    """
    _ensure_discovered()
    s = get(strategy_name)
    path = _ensure_path(image)
    try:
        messages = list(s.encode(path, max_width=max_width, **kwargs))
    finally:
        _cleanup_temp(path, image)
    if not messages:
        raise RuntimeError(f"Encoder {strategy_name!r} produced no messages")
    return messages[0]


def process_image_tiled(
    image: Path | Image.Image,
    *,
    tile_size: int = 1024,
    max_width: int | None = None,
    **kwargs: Any,
) -> Iterable[Message]:
    """Tile an image with overview, yielding all tiles in one Message.

    Args:
        image: Path to an image file, or a PIL ``Image`` object.
        tile_size: Alias for max_width (kept for backward compat).
        max_width: Pixel size for tile dimension and overview bounding box.
            Takes precedence over tile_size if both are given.
        **kwargs: Forwarded to ``encoder.encode()``.

    Yields:
        Messages containing overview + tile crops.
    """
    _ensure_discovered()
    s = get("tile")
    path = _ensure_path(image)
    width = max_width if max_width is not None else tile_size
    try:
        messages = list(s.encode(path, max_width=width, **kwargs))
    finally:
        _cleanup_temp(path, image)
    return messages


def process_video(
    video: Path,
    *,
    strategy_name: str = "frame-sample",
    **kwargs: Any,
) -> Iterable[Message]:
    """Encode a video and yield one Message per chunk.

    Args:
        video: Path to a video file.
        strategy_name: Registry name (e.g. ``"frame-sample"``,
            ``"video-chunk"``).
        **kwargs: Forwarded to ``encoder.encode()``.

    Yields:
        One Message per video chunk.
    """
    _ensure_discovered()
    s = get(strategy_name)
    return s.encode(video, **kwargs)


def process_document(
    document: Path,
    *,
    strategy_name: str = "rasterize",
    **kwargs: Any,
) -> Iterable[Message]:
    """Encode a document and yield one Message per page group.

    Args:
        document: Path to a PDF, DOCX, or PPTX file.
        strategy_name: Registry name (e.g. ``"rasterize"``,
            ``"rasterize-text"``).
        **kwargs: Forwarded to ``encoder.encode()``.

    Yields:
        One Message per group of pages.
    """
    _ensure_discovered()
    s = get(strategy_name)
    return s.encode(document, **kwargs)


def _ensure_path(image: Path | Any) -> Path:
    """Convert a PIL Image to a temporary file path if necessary."""
    if isinstance(image, Path):
        return image
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = Path(f.name)
    image.save(tmp)
    return tmp


def _cleanup_temp(path: Path, original: Path | Any) -> None:
    """Delete *path* if it was created by ``_ensure_path`` (i.e. differs from *original*)."""
    if not isinstance(original, Path) and path.exists():
        try:
            path.unlink()
        except OSError:
            pass
