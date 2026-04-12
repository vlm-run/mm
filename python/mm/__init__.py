"""mm -- High-performance multi-modal context management."""

from importlib.metadata import version

__all__ = [
    "Context",
    "process_image",
    "process_image_tiled",
    "process_video",
    "process_document",
]
__version__ = version("mm")

_LAZY_IMPORTS = {
    "Context": ("mm.context", "Context"),
    "process_image": ("mm.encoders", "process_image"),
    "process_image_tiled": ("mm.encoders", "process_image_tiled"),
    "process_video": ("mm.encoders", "process_video"),
    "process_document": ("mm.encoders", "process_document"),
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        import importlib

        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    raise AttributeError(f"module 'mm' has no attribute {name!r}")
