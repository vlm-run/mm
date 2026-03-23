"""mm -- High-performance multi-modal context management."""

__all__ = ["Context"]
__version__ = "0.1.0"


def __getattr__(name: str):
    if name == "Context":
        from mm.context import Context

        return Context
    raise AttributeError(f"module 'mm' has no attribute {name!r}")
