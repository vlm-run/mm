"""mm -- Fast, multimodal context for agents."""

import os as _os

if not _os.environ.get("LOGFIRE_TOKEN"):
    _os.environ.setdefault("PYDANTIC_DISABLE_PLUGINS", "logfire-plugin")

from importlib.metadata import version

__all__ = [
    "ChatCompletionError",
    "Context",
    "ImageURLError",
    "Ref",
    "RefNotFoundError",
    "render_context",
    "render_messages",
    "uuid7",
]
__version__ = version("mm-ctx")

_LAZY_IMPORTS = {
    "ChatCompletionError": ("mm.errors", "ChatCompletionError"),
    "Context": ("mm.context", "Context"),
    "ImageURLError": ("mm.errors", "ImageURLError"),
    "Ref": ("mm.refs", "Ref"),
    "RefNotFoundError": ("mm.refs", "RefNotFoundError"),
    "render_context": ("mm.notebook", "render_context"),
    "render_messages": ("mm.notebook", "render_messages"),
    "uuid7": ("mm.refs", "uuid7"),
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        import importlib

        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    raise AttributeError(f"module 'mm' has no attribute {name!r}")
