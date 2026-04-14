"""mm -- High-performance multimodal context management library."""

from importlib.metadata import version

__all__ = ["Context"]
__version__ = version("mm")

_LAZY_IMPORTS = {
    "Context": ("mm.context", "Context"),
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        import importlib

        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    raise AttributeError(f"module 'mm' has no attribute {name!r}")
