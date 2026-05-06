"""mm -- Fast, multimodal context for agents."""

from importlib.metadata import version

__all__ = [
    "Context",
    "MessageView",
    "Ref",
    "RefNotFoundError",
    "render_context",
    "render_messages_html",
    "uuid7",
]
__version__ = version("mm-ctx")

_LAZY_IMPORTS = {
    "Context": ("mm.context", "Context"),
    "MessageView": ("mm.notebook", "MessageView"),
    "Ref": ("mm.refs", "Ref"),
    "RefNotFoundError": ("mm.refs", "RefNotFoundError"),
    "render_context": ("mm.notebook", "render_context"),
    "render_messages_html": ("mm.notebook", "render_messages_html"),
    "uuid7": ("mm.refs", "uuid7"),
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        import importlib

        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    raise AttributeError(f"module 'mm' has no attribute {name!r}")
