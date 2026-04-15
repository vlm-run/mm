"""Lazy import helpers for optional dependency extras.

Provides ``try_import_or_raise`` — a single entry point that attempts a
module import and, on failure, raises an ``ImportError`` with a
human-friendly message telling the user which ``mm[extra]`` to install.
"""

from __future__ import annotations

import importlib
from types import ModuleType

_EXTRA_INSTALL_HINTS: dict[str, str] = {
    "mlx": "pip install mm-ctx[mlx]",
    "experimental": "pip install mm-ctx[experimental]",
}


def try_import_or_raise(
    module_name: str,
    *,
    extra: str,
    package: str | None = None,
) -> ModuleType:
    """Import *module_name* or raise ``ImportError`` with install guidance.

    Args:
        module_name: Dotted module path, e.g. ``"google.genai.types"``.
        extra: The ``mm`` extras key (``"gemini"``, ``"mlx"``, ``"experimental"``).
        package: Optional pip package name shown in the error message.
            Defaults to *module_name*.

    Returns:
        The imported module.

    Raises:
        ImportError: With a message recommending the correct ``mm[extra]``.
    """
    try:
        return importlib.import_module(module_name)
    except ImportError:
        hint = _EXTRA_INSTALL_HINTS.get(extra, f"pip install mm-ctx[{extra}]")
        pkg = package or module_name
        raise ImportError(
            f"{pkg} is required but not installed. Install it with:  {hint}"
        ) from None
