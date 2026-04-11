"""Message serialization strategies for VLM encoding.

Strategies transform media files (images, videos, documents) into
OpenAI-compatible Message dicts ready for chat/completions APIs.

Three ways to use a strategy:
    1. Named:  ``mm cat photo.png -s resize``
    2. File:   ``mm cat photo.png -s ~/my_strat.py``
    3. Inline: ``mm cat photo.png -s 'def encode(path, **kw): ...'``

Custom strategies use the ``@strategy`` decorator::

    from mm.serde import strategy

    @strategy(name="my_custom", media_types=("image",))
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


def register(strat: MessageStrategy) -> MessageStrategy:
    """Add a strategy instance to the global registry.

    Args:
        strat: Any object satisfying the ``MessageStrategy`` protocol.

    Returns:
        The same strategy, for use as a decorator return value.
    """
    _REGISTRY[strat.name] = strat
    return strat


def get(name: str) -> MessageStrategy:
    """Look up a registered strategy by name.

    Args:
        name: Strategy identifier (e.g. ``"resize"``).

    Raises:
        KeyError: If no strategy with that name is registered.
    """
    _ensure_discovered()
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"Unknown strategy {name!r}. Available: {available}")
    return _REGISTRY[name]


def list_strategies(*, media_type: str | None = None) -> list[str]:
    """Return sorted names of all registered strategies.

    Args:
        media_type: If given, only return strategies that handle this
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


class _FunctionStrategy:
    """Adapts a bare generator function into a ``MessageStrategy``."""

    __slots__ = ("name", "media_types", "_fn")

    def __init__(self, name: str, media_types: tuple[str, ...], fn: Any) -> None:
        self.name = name
        self.media_types = media_types
        self._fn = fn

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        return self._fn(path, **kwargs)


def strategy(
    name: str | None = None,
    media_types: tuple[str, ...] = ("image",),
):
    """Decorator that turns a generator function into a registered strategy.

    The ``name`` is optional — if omitted, it is derived from the
    function name by replacing underscores with hyphens.

    Examples::

        @strategy(media_types=("image",))
        def my_resize(path, **kw):
            ...
            yield {"role": "user", "content": [...]}
        # Registered as "my-resize"

        @strategy(name="custom-name", media_types=("video",))
        def whatever(path, **kw):
            ...

    Args:
        name: Registry key.  Defaults to the function name with
            underscores replaced by hyphens.
        media_types: Tuple of media kinds this strategy handles.
    """

    def decorator(fn: Any) -> _FunctionStrategy:
        resolved_name = name if name is not None else fn.__name__.replace("_", "-")
        s = _FunctionStrategy(resolved_name, media_types, fn)
        register(s)
        return s

    return decorator


def load_strategy_file(path: Path) -> list[str]:
    """Dynamically import a ``.py`` file and register its strategies.

    Any ``@strategy``-decorated functions in the file are automatically
    registered when the module is executed.

    Args:
        path: Absolute or relative path to a Python file.

    Returns:
        List of strategy names that were newly registered.

    Raises:
        ImportError: If the file cannot be loaded.
    """
    before = set(_REGISTRY)
    module_name = f"mm_strategy_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load strategy from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    after = set(_REGISTRY)
    return sorted(after - before)


def load_inline_strategy(code: str) -> list[str]:
    """Execute inline Python code and register its strategies.

    The executed code has access to the ``strategy`` decorator and
    ``pathlib.Path``.  Intended for agent-generated code passed via
    ``mm cat -s '<code>'``.

    Args:
        code: Python source code containing ``@strategy``-decorated
            functions.

    Returns:
        List of strategy names that were newly registered.
    """
    before = set(_REGISTRY)
    exec_globals: dict[str, Any] = {
        "strategy": strategy,
        "Path": Path,
        "__builtins__": __builtins__,
    }
    exec(code, exec_globals)  # noqa: S102
    after = set(_REGISTRY)
    return sorted(after - before)


def _ensure_discovered() -> None:
    """Lazily register built-in strategies and run auto-discovery."""
    global _DISCOVERED
    if _DISCOVERED:
        return
    _DISCOVERED = True
    _register_builtins()
    discover_strategies()


def _register_builtins() -> None:
    """Import built-in strategy modules so their classes self-register."""
    from mm.serde import document, gemini, image, video  # noqa: F401


def discover_strategies() -> None:
    """Scan known directories for user-defined strategy files.

    Discovery order:
        1. ``python/mm/strategies/*.py`` (project-level, checked into repo)
        2. ``~/.config/mm/strategies/*.py`` (per-user, not in repo)
    """
    _discover_from_dir(_project_strategies_dir())
    _discover_from_dir(_user_strategies_dir())


def _discover_from_dir(directory: Path | None) -> None:
    if directory is None or not directory.is_dir():
        return
    for py_file in sorted(directory.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            load_strategy_file(py_file)
        except Exception:
            pass


def _project_strategies_dir() -> Path | None:
    d = Path(__file__).resolve().parent.parent / "strategies"
    return d if d.is_dir() else None


def _user_strategies_dir() -> Path | None:
    d = Path.home() / ".config" / "mm" / "strategies"
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
            when a loaded file defines multiple strategies).

    Returns:
        A ``MessageStrategy`` ready to call ``.encode()``.

    Raises:
        KeyError: Named strategy not found.
        FileNotFoundError: Strategy file does not exist.
        ValueError: Loaded file/code registered no strategies.
    """
    _ensure_discovered()

    if "def " in value or "lambda " in value:
        names = load_inline_strategy(value)
        return _pick_by_media_type(names, media_type, source="inline code")

    if value.endswith(".py") or "/" in value:
        path = Path(value).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Strategy file not found: {path}")
        names = load_strategy_file(path)
        return _pick_by_media_type(names, media_type, source=str(path))

    return get(value)


def _pick_by_media_type(
    names: list[str], media_type: str, source: str
) -> MessageStrategy:
    """Select the best-matching strategy from a set of newly registered names.

    If *names* is empty (e.g. a strategy file was re-loaded and the name
    was already in the registry), falls back to searching the full
    registry for strategies matching *media_type*.
    """
    if not names:
        # Re-load case: the strategy was already registered on a prior call.
        # Search the registry for a matching media_type.
        candidates = [
            s for s in _REGISTRY.values() if media_type in s.media_types
        ]
        if candidates:
            return candidates[0]
        raise ValueError(f"No strategies registered from {source}")
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
        strategy_name: Registry name of the strategy to use.
        max_width: Maximum width in pixels (passed to the strategy).
        **kwargs: Forwarded to ``strategy.encode()``.

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
        raise RuntimeError(f"Strategy {strategy_name!r} produced no messages")
    return messages[0]


def process_image_tiled(
    image: Path | Image.Image,
    *,
    tile_size: int = 1024,
    **kwargs: Any,
) -> Iterable[Message]:
    """Tile a large image and yield one Message per tile.

    Args:
        image: Path to an image file, or a PIL ``Image`` object.
        tile_size: Maximum tile dimension in pixels.
        **kwargs: Forwarded to ``strategy.encode()``.

    Yields:
        One Message per tile, suitable for parallel VLM inference.
    """
    _ensure_discovered()
    s = get("tile")
    path = _ensure_path(image)
    try:
        messages = list(s.encode(path, tile_size=tile_size, **kwargs))
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
        **kwargs: Forwarded to ``strategy.encode()``.

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
        **kwargs: Forwarded to ``strategy.encode()``.

    Yields:
        One Message per group of pages.
    """
    _ensure_discovered()
    s = get(strategy_name)
    return s.encode(document, **kwargs)


def _ensure_path(image: Path | Any) -> Path:
    """Convert a PIL Image to a temporary file path if necessary.

    Uses ``NamedTemporaryFile`` with ``delete=False`` so the caller
    retains access to the path.  The file is deleted after strategy
    execution in the convenience functions above.
    """
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
