"""mm -- High-performance multi-modal context management."""

from importlib.metadata import version

__all__ = ["Context"]
__version__ = version("mm")


def __getattr__(name: str):
    if name == "Context":
        from mm.context import Context

        return Context
    raise AttributeError(f"module 'mm' has no attribute {name!r}")
