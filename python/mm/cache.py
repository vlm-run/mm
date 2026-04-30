"""Process-local memoisation keyed on file fingerprints.

Many of mm's expensive helpers (``probe``, ``detect_scenes``, the Whisper
transcript) take a file path and return something heavy.  Within a single
process we want repeated calls to be free, but we also want any underlying
file change to invalidate the cache automatically.

This module centralises that pattern so individual encoders don't each
re-implement an LRU + mtime check.

Usage::

    from mm.cache import memoize_file

    @memoize_file(maxsize=64)
    def probe(path: Path) -> VideoInfo:
        ...

    probe.cache_clear()                # drop everything
    probe.cache_info()["hits"]         # quick introspection

The cache key is ``(absolute_path, mtime, size, *other_args, **kwargs)`` so:

* The same path with the same mtime hits the cache.
* Editing or replacing the file on disk invalidates automatically.
* Different keyword arguments (e.g. ``threshold=27`` vs ``threshold=15``)
  get separate cache entries.
* Calls against a missing path bypass the cache entirely and let the
  underlying function raise naturally — no spurious cache poisoning.

The implementation is a thin wrapper around :class:`cachetools.LRUCache`;
all locking is process-local and cheap.
"""

from __future__ import annotations

import functools
import inspect
import threading
from collections.abc import Callable, Hashable
from pathlib import Path
from typing import Any, cast

from cachetools import LRUCache
from cachetools.keys import hashkey

__all__ = ["file_fingerprint", "memoize_file"]


def file_fingerprint(path: Any) -> tuple[str, float, int] | None:
    """Return a stable cache key for *path* or ``None`` if the file is missing.

    The fingerprint is ``(absolute_path, mtime, size)``.  Returning ``None``
    is a signal to the caller that the path can't be cached safely (e.g.
    nonexistent file, unreadable directory, non-string-coercible value).
    """
    try:
        st = Path(path).stat()
    except (TypeError, OSError, ValueError):
        return None
    return (str(Path(path).resolve()), st.st_mtime, st.st_size)


def memoize_file(*, maxsize: int = 64) -> Callable[[Callable[..., Any]], Any]:
    """Decorator: cache by ``(file fingerprint, *normalised args)``.

    The first positional argument MUST be a file path (``str`` or
    :class:`~pathlib.Path`).  Repeated calls with the same fingerprint
    return the cached value; mtime changes invalidate; missing files
    bypass the cache so the wrapped function still runs (and raises) as
    expected.

    Args binding semantics:

    All other arguments are normalised against the wrapped function's
    signature via :func:`inspect.Signature.bind` *with defaults applied*.
    That means ``f(path)`` and ``f(path, threshold=27.0)`` (where 27.0
    is the default) hash to the same key — encoders that rely on the
    default for one parameter still hit cache entries written by callers
    that pass the value explicitly.

    The decorated function gains ``cache_clear`` and ``cache_info``
    helpers, plus a ``cache`` attribute for tests that need direct
    access.  The return type is left as :class:`~typing.Any` because
    static checkers can't model attribute injection through a generic
    decorator without losing the wrapped signature.

    Args:
        maxsize: Maximum number of entries before LRU eviction.

    Returns:
        A decorator that wraps the target function.
    """

    def decorator(fn: Callable[..., Any]) -> Any:
        cache: LRUCache[Hashable, Any] = LRUCache(maxsize=maxsize)
        lock = threading.Lock()
        sig = inspect.signature(fn)
        first_param = next(iter(sig.parameters))
        hits = misses = 0

        def _build_key(
            fp: tuple[str, float, int],
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
        ) -> Hashable:
            # Bind to the function signature so defaults are part of the key
            # and (path, threshold=27) hashes equal to (path) when 27 is the
            # default.  ``args[0]`` (the path) is replaced with the
            # fingerprint so identical files at different paths share the
            # cache.
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            normalised = dict(bound.arguments)
            normalised.pop(first_param, None)
            return hashkey(fp, *sorted(normalised.items()))

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal hits, misses
            if not args:
                return fn(*args, **kwargs)

            fp = file_fingerprint(args[0])
            if fp is None:
                # Missing file → run the function uncached so the caller
                # sees the natural error (or the function's own fallback).
                return fn(*args, **kwargs)

            key = _build_key(fp, args, kwargs)
            with lock:
                if key in cache:
                    hits += 1
                    return cache[key]
                misses += 1

            result = fn(*args, **kwargs)
            with lock:
                cache[key] = result
            return result

        def cache_clear() -> None:
            """Drop all cached entries."""
            nonlocal hits, misses
            with lock:
                cache.clear()
                hits = misses = 0

        def cache_info() -> dict[str, int]:
            """Snapshot of cache stats: ``{hits, misses, currsize, maxsize}``."""
            with lock:
                return {
                    "hits": hits,
                    "misses": misses,
                    "currsize": len(cache),
                    "maxsize": cache.maxsize,
                }

        wrapped = cast(Any, wrapper)
        wrapped.cache = cache
        wrapped.cache_clear = cache_clear
        wrapped.cache_info = cache_info
        return wrapped

    return decorator
