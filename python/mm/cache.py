"""Memoisation keyed on file fingerprints, in-memory or disk-backed.

Many of mm's expensive helpers (``probe``, ``detect_scenes``, the Whisper
transcript) take a file path and return something heavy.  Within a single
process we want repeated calls to be free; across CLI invocations we want
the slow ones (Whisper, scene detection) to be free too.  Either way, any
underlying file change must invalidate the cache automatically.

This module centralises that pattern so individual encoders don't each
re-implement an LRU + mtime check.

In-memory (process-local) cache::

    from mm.cache import memoize_file

    @memoize_file(maxsize=64)
    def probe(path: Path) -> VideoInfo:
        ...

Disk-backed cache (persists across CLI invocations)::

    from mm.cache import memoize_file, cache_dir

    @memoize_file(maxsize=16, path=lambda: cache_dir() / "transcripts")
    def transcript_messages(path: Path, ...) -> list[Message]:
        ...

Either way::

    fn.cache_clear()                # drop everything
    fn.cache_info()["hits"]         # quick introspection

The cache key is ``(absolute_path, mtime, size, *other_args, **kwargs)``:

* The same path with the same mtime hits the cache.
* Editing or replacing the file on disk invalidates automatically.
* Different keyword arguments get separate cache entries.
* Calls passing default arguments explicitly hash to the same key as
  calls that omit them — no cache splits over redundant kwargs.
* Calls against a missing path bypass the cache entirely.

Disk backend semantics:

* ``path`` may be a :class:`~pathlib.Path`, ``str``, or a no-arg
  ``Callable`` returning one.  Callables are resolved lazily on first
  use, so tests that set ``MM_CACHE_DIR`` in ``conftest.py`` after this
  module is imported still take effect.
* The backend is :class:`cachetools_ext.fs.FSLRUCache` — one pickle
  file per entry under ``path/``.  Cache directories are created on
  demand.
* Keys are SHA-1 hashes of the in-memory ``hashkey`` tuple to ensure
  filename-safe strings.  Hash collisions are astronomically unlikely.
* Values must be picklable.  All current call sites
  (:class:`VideoInfo`, :class:`SceneResult`, ``list[Message]``) qualify.

Cache directory resolution (``cache_dir``):

1. ``MM_CACHE_DIR`` env var (mm-specific override, used by tests).
2. ``XDG_CACHE_HOME/mm`` (Linux/macOS XDG convention).
3. ``~/.cache/mm`` (fallback).
"""

from __future__ import annotations

import functools
import hashlib
import inspect
import threading
from collections.abc import Callable, Hashable, MutableMapping
from pathlib import Path
from typing import Any, ParamSpec, Protocol, TypeVar, cast

from cachetools import LRUCache
from cachetools.keys import hashkey

__all__ = ["cache_dir", "file_fingerprint", "memoize_file"]

# A path can be supplied directly or via a no-arg factory.  The factory
# form lets tests override ``MM_CACHE_DIR`` *after* this module is
# imported, since the resolution is deferred to first use.
PathLike = str | Path
PathSpec = PathLike | Callable[[], PathLike] | None


def cache_dir() -> Path:
    """Return mm's on-disk cache directory, honouring XDG conventions.

    Delegates to :class:`~mm.settings.MmSettings`, which resolves the path in
    order:

    1. ``$MM_CACHE_DIR`` — mm-specific override (used in tests/CI).
    2. ``$XDG_CACHE_HOME/mm`` — XDG Base Directory spec.
    3. ``~/.cache/mm`` — fallback.

    Resolution is lazy (read on access, not at import), so tests that set
    ``MM_CACHE_DIR`` after importing mm still take effect. The directory is
    *not* created here; callers (or the disk-cache backend) create it on
    demand so a read-only check is free.
    """
    from mm.settings import get_settings

    return get_settings().cache_dir


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


def _key_to_str(key: Hashable) -> str:
    """Hash an arbitrary hashable to a filename-safe SHA-1 hex string.

    ``FSLRUCache`` uses keys as filenames, so they must be safe across
    filesystems.  SHA-1 is overkill for cache keying (collisions are
    astronomically unlikely) but keeps every key a fixed 40 chars and
    sidesteps every filename quirk (length limits, illegal characters,
    case-folding, etc.).
    """
    return hashlib.sha1(repr(key).encode("utf-8")).hexdigest()


def _resolve_path(spec: PathSpec) -> Path | None:
    """Resolve a ``PathSpec`` to an absolute :class:`Path` or ``None``."""
    if spec is None:
        return None
    # Narrow via ``isinstance`` (instead of ``callable()``) so ty can
    # tell concrete paths from the factory branch — both str and Path
    # are handled uniformly, anything else is treated as a no-arg
    # callable returning a path.
    if isinstance(spec, (str, Path)):
        return Path(spec).expanduser()
    return Path(spec()).expanduser()


P = ParamSpec("P")
T = TypeVar("T")


class _CachedCallable(Protocol[P, T]):
    """Typed wrapper returned by ``memoize_file``."""

    __call__: Callable[P, T]
    cache_clear: Callable[[], None]
    cache_info: Callable[[], dict[str, int]]
    cache: Callable[[], MutableMapping[Hashable, Any]]


def memoize_file(
    *,
    maxsize: int = 64,
    path: PathSpec = None,
) -> Callable[[Callable[P, T]], _CachedCallable[P, T]]:
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
        path: When ``None`` (default) the cache lives in process memory
            (:class:`cachetools.LRUCache`).  When a path or path-factory
            is supplied, the cache is backed by
            :class:`cachetools_ext.fs.FSLRUCache` — one pickle file per
            entry.  A factory (no-arg callable) is resolved lazily on
            first use, which lets tests override ``MM_CACHE_DIR`` after
            this module loads.

    Returns:
        A decorator that wraps the target function.
    """

    def decorator(fn: Callable[..., Any]) -> Any:
        sig = inspect.signature(fn)
        first_param = next(iter(sig.parameters))

        # Cache backend is created on first use so:
        #   (a) module import stays cheap (no FSLRUCache file scan), and
        #   (b) callers can set MM_CACHE_DIR after import (e.g. conftest).
        cache_holder: dict[str, MutableMapping[Hashable, Any]] = {}
        lock = threading.Lock()
        init_lock = threading.Lock()
        hits = misses = 0

        def _ensure_cache() -> MutableMapping[Hashable, Any]:
            # Double-checked init: fast path skips the lock when already
            # populated; slow path (first call only) holds ``init_lock``
            # so concurrent threads don't race on FSLRUCache creation.
            if "cache" in cache_holder:
                return cache_holder["cache"]
            with init_lock:
                if "cache" in cache_holder:
                    return cache_holder["cache"]
                resolved = _resolve_path(path)
                if resolved is None:
                    backend: MutableMapping[Hashable, Any] = cast(
                        "MutableMapping[Hashable, Any]",
                        LRUCache(maxsize=maxsize),
                    )
                else:
                    # Local import keeps in-memory users from paying for
                    # cachetools_ext (and its filesystem checks) on import.
                    from cachetools_ext.fs import FSLRUCache

                    resolved.mkdir(parents=True, exist_ok=True)
                    backend = cast(
                        "MutableMapping[Hashable, Any]",
                        FSLRUCache(maxsize=maxsize, path=str(resolved)),
                    )
                cache_holder["cache"] = backend
                return backend

        def _build_key(
            fp: tuple[str, float, int],
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
        ) -> Hashable:
            # Bind to the function signature so defaults are part of the
            # key and (path, threshold=27) hashes equal to (path) when 27
            # is the default.  The path is replaced with the fingerprint
            # so identical files at different paths share the cache.
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            normalised = dict(bound.arguments)
            normalised.pop(first_param, None)
            key: Hashable = hashkey(fp, *sorted(normalised.items()))
            # FSLRUCache writes one pickle file per key, so the key must
            # be filename-safe. Hashing keeps in-memory and on-disk
            # backends symmetric — both store under the same string.
            if path is not None:
                return _key_to_str(key)
            return key

        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            nonlocal hits, misses
            if not args:
                return fn(*args, **kwargs)

            fp = file_fingerprint(args[0])
            if fp is None:
                return fn(*args, **kwargs)

            key = _build_key(fp, args, kwargs)
            cache = _ensure_cache()
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
            """Drop all cached entries (in-memory or on disk)."""
            nonlocal hits, misses
            with lock:
                cache = _ensure_cache()
                cache.clear()
                hits = misses = 0

        def cache_info() -> dict[str, int]:
            """Snapshot of cache stats: ``{hits, misses, currsize, maxsize}``."""
            with lock:
                cache = _ensure_cache()
                return {
                    "hits": hits,
                    "misses": misses,
                    "currsize": len(cache),
                    "maxsize": getattr(cache, "maxsize", maxsize),
                }

        wrapped = cast(_CachedCallable[P, T], wrapper)
        wrapped.cache_clear = cache_clear
        wrapped.cache_info = cache_info
        # Lazy backend accessor for tests / introspection.  Calling it
        # materialises the cache on first touch — matching the lazy
        # decoration story for the disk-backed variant.
        wrapped.cache = _ensure_cache
        return wrapped

    return decorator
