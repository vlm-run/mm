"""mm -- Fast, multimodal context for agents."""

import os as _os

if not _os.environ.get("LOGFIRE_TOKEN"):
    _os.environ.setdefault("PYDANTIC_DISABLE_PLUGINS", "logfire-plugin")

__all__ = [
    "Context",
    "Ref",
    "RefNotFoundError",
    "render_context",
    "render_messages",
    "uuid7",
]

_LAZY_IMPORTS = {
    "Context": ("mm.context", "Context"),
    "Ref": ("mm.refs", "Ref"),
    "RefNotFoundError": ("mm.refs", "RefNotFoundError"),
    "render_context": ("mm.notebook", "render_context"),
    "render_messages": ("mm.notebook", "render_messages"),
    "uuid7": ("mm.refs", "uuid7"),
}


def __getattr__(name: str):
    if name == "__version__":
        # importlib.metadata costs ~45ms; defer until something reads it.
        from importlib.metadata import version

        v = version("mm-ctx")
        globals()["__version__"] = v
        return v
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        import importlib

        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    raise AttributeError(f"module 'mm' has no attribute {name!r}")
