"""vlmctx -- High-performance multi-modal context management."""

__all__ = ["Context"]
__version__ = "0.1.0"


def __getattr__(name: str):
    if name == "Context":
        from vlmctx.context import Context

        return Context
    raise AttributeError(f"module 'vlmctx' has no attribute {name!r}")
