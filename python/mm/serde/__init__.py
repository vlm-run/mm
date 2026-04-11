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

# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class MessageStrategy(Protocol):
    """Interface for media encoding strategies."""

    name: str
    media_types: tuple[str, ...]

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]: ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, MessageStrategy] = {}
_DISCOVERED = False


def register(strat: MessageStrategy) -> MessageStrategy:
    """Register a strategy instance by name."""
    _REGISTRY[strat.name] = strat
    return strat


def get(name: str) -> MessageStrategy:
    """Look up a registered strategy. Raises KeyError if not found."""
    _ensure_discovered()
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"Unknown strategy {name!r}. Available: {available}")
    return _REGISTRY[name]


def list_strategies(*, media_type: str | None = None) -> list[str]:
    """List registered strategy names, optionally filtered by media type."""
    _ensure_discovered()
    if media_type is None:
        return sorted(_REGISTRY)
    return sorted(
        name
        for name, s in _REGISTRY.items()
        if media_type in s.media_types
    )


# ---------------------------------------------------------------------------
# @strategy decorator
# ---------------------------------------------------------------------------


class _FunctionStrategy:
    """Wraps a generator function as a MessageStrategy."""

    __slots__ = ("name", "media_types", "_fn")

    def __init__(
        self,
        name: str,
        media_types: tuple[str, ...],
        fn: Any,
    ) -> None:
        self.name = name
        self.media_types = media_types
        self._fn = fn

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        return self._fn(path, **kwargs)


def strategy(name: str, media_types: tuple[str, ...]):
    """Decorator: turn a function into a registered MessageStrategy.

    Example::

        @strategy(name="my_resize", media_types=("image",))
        def my_resize(path, **kw):
            ...
            yield {"role": "user", "content": [...]}
    """

    def decorator(fn: Any) -> _FunctionStrategy:
        s = _FunctionStrategy(name, media_types, fn)
        register(s)
        return s

    return decorator


# ---------------------------------------------------------------------------
# Dynamic loading
# ---------------------------------------------------------------------------


def load_strategy_file(path: Path) -> list[str]:
    """Import a .py file and register any @strategy-decorated functions.

    Returns list of strategy names registered from the file.
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
    """Execute inline Python code and register any @strategy-decorated functions.

    The code has access to:
      - ``strategy``: the decorator
      - ``Path``: pathlib.Path
      - Standard library modules

    Returns list of strategy names registered.
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


# ---------------------------------------------------------------------------
# Auto-discovery
# ---------------------------------------------------------------------------


def _ensure_discovered() -> None:
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
    """Auto-discover strategies from known directories."""
    # 1. Project-level: python/mm/strategies/
    _discover_from_dir(_project_strategies_dir())
    # 2. User-level: ~/.config/mm/strategies/
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
            pass  # Skip broken strategy files silently


def _project_strategies_dir() -> Path | None:
    """Return python/mm/strategies/ relative to the package."""
    d = Path(__file__).resolve().parent.parent / "strategies"
    return d if d.is_dir() else None


def _user_strategies_dir() -> Path | None:
    """Return ~/.config/mm/strategies/."""
    d = Path.home() / ".config" / "mm" / "strategies"
    return d if d.is_dir() else None


# ---------------------------------------------------------------------------
# Resolve -s value
# ---------------------------------------------------------------------------


def resolve_strategy(value: str, media_type: str) -> MessageStrategy:
    """Resolve a ``-s`` value to a MessageStrategy.

    Detection logic:
      1. Contains ``def `` or ``lambda`` -> inline Python code
      2. Ends with ``.py`` or contains ``/`` -> file path
      3. Otherwise -> named strategy lookup
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
    """From a list of newly registered strategy names, pick the one matching media_type."""
    if not names:
        raise ValueError(f"No strategies registered from {source}")
    # Filter by media type
    matching = [n for n in names if media_type in _REGISTRY[n].media_types]
    if len(matching) == 1:
        return _REGISTRY[matching[0]]
    if len(matching) > 1:
        return _REGISTRY[matching[0]]
    # No media type match — return the first one
    return _REGISTRY[names[0]]


# ---------------------------------------------------------------------------
# Provider resolution
# ---------------------------------------------------------------------------


def _resolve_provider() -> str:
    """Infer message format from active profile. Returns 'gemini' or 'openai'."""
    try:
        from mm.profile import get_active_profile_name

        name = get_active_profile_name()
        return "gemini" if "gemini" in name.lower() else "openai"
    except Exception:
        return "openai"


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def process_image(
    image: Path | Image.Image,
    *,
    strategy_name: str = "resize",
    max_width: int = 1024,
    **kwargs: Any,
) -> Message:
    """Process a single image and return an OpenAI-compatible Message dict.

    Args:
        image: Path to image or PIL Image object.
        strategy_name: Strategy name (default: "resize").
        max_width: Maximum width in pixels.
        **kwargs: Additional strategy-specific parameters.

    Returns:
        A single Message dict: ``{"role": "user", "content": [...]}``.
    """
    _ensure_discovered()
    s = get(strategy_name)
    path = _ensure_path(image)
    messages = list(s.encode(path, max_width=max_width, **kwargs))
    if not messages:
        raise RuntimeError(f"Strategy {strategy_name!r} produced no messages")
    return messages[0]


def process_image_tiled(
    image: Path | Image.Image,
    *,
    tile_size: int = 1024,
    **kwargs: Any,
) -> Iterable[Message]:
    """Process a large image as tiles. Returns iterable of Messages."""
    _ensure_discovered()
    s = get("tile")
    path = _ensure_path(image)
    return s.encode(path, tile_size=tile_size, **kwargs)


def process_video(
    video: Path,
    *,
    strategy_name: str = "frame_sample",
    **kwargs: Any,
) -> Iterable[Message]:
    """Process video into chunks. Returns iterable of Messages."""
    _ensure_discovered()
    s = get(strategy_name)
    return s.encode(video, **kwargs)


def process_document(
    document: Path,
    *,
    strategy_name: str = "rasterize",
    **kwargs: Any,
) -> Iterable[Message]:
    """Process document into page groups. Returns iterable of Messages."""
    _ensure_discovered()
    s = get(strategy_name)
    return s.encode(document, **kwargs)


def _ensure_path(image: Path | Any) -> Path:
    """Convert PIL Image to a temp file path if needed."""
    if isinstance(image, Path):
        return image
    # Assume PIL Image
    import tempfile

    tmp = Path(tempfile.mktemp(suffix=".png"))
    image.save(tmp)
    return tmp
