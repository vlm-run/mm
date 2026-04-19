"""mm -- Fast, multimodal file intelligence for agents."""

from importlib.metadata import version

__all__ = ["Context", "GlobalRef", "make_ref_id", "new_session_id"]
__version__ = version("mm")


_LAZY_IMPORTS = {
    "Context": ("mm.context", "Context"),
    "GlobalRef": ("mm.refs", "GlobalRef"),
    "make_ref_id": ("mm.refs", "make_ref_id"),
    "new_session_id": ("mm.refs", "new_session_id"),
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        import importlib

        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    raise AttributeError(f"module 'mm' has no attribute {name!r}")
