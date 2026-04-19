"""Reference IDs for files and objects in a Context.

Mirrors the canonical ref scheme from ``vlmrun-python-sdk``
(``vlmrun/types/refs.py``) — a short, kind-prefixed handle of the form
``<prefix>_<6 alphanumeric chars>`` that uniquely identifies an object inside
its owning ``session_id``.

A *global reference* is the string ``<session_id>/<ref_id>``: it resolves to a
single file row in the mm database regardless of the user, machine, or
filesystem path that produced it.

Design notes:

- **Random suffix.** ``make_ref_id`` draws a 6-character lowercase-hex suffix
  from ``secrets.token_hex``. Refs are opaque, not derivable from the file
  path — stability comes from persisting them in the mm SQLite database and
  caching them on the live :class:`mm.Context` instance, not from a hash.
- **Kind-aware prefixes.** The prefix encodes the file ``kind`` so refs are
  self-describing (``img_a1b2c3``, ``vid_d4e5f6``). Prefixes are aligned with
  ``vlmrun-python-sdk`` where the kinds overlap; mm-specific kinds (``code``,
  ``data``, ``config``, ``text``, ``other``) get their own short prefixes.
- **Compatible alphabet.** The suffix uses ``[0-9a-f]`` which is a subset of
  the ``\\w`` pattern enforced by ``vlmrun-python-sdk``'s pydantic models,
  so any mm-generated ref is a valid ``vlmrun`` ref.
"""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass
from typing import Annotated

#: Typed alias for a ref id string (``<prefix>_<6 hex>``).
#:
#: At runtime this is just :class:`str`; IDEs and type checkers treat it as a
#: distinct type thanks to :data:`typing.Annotated`. Use this in type hints
#: where you want to distinguish ref ids from arbitrary strings::
#:
#:     img: mm.Ref = ctx.put(Path("photo.jpg"))
Ref = Annotated[str, "mm.Ref"]


try:
    from mm._mm import RefNotFoundError  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - Rust extension should always be present

    class RefNotFoundError(KeyError):  # type: ignore[no-redef]
        """Raised when a ref id lookup misses.

        Fallback Python implementation used only when the Rust extension
        fails to import (e.g. during development). The real class is
        defined in ``_mm/refs.rs`` and inherits from :class:`KeyError`.
        """


KIND_TO_PREFIX: dict[str, str] = {
    "image": "img",
    "video": "vid",
    "audio": "aud",
    "document": "doc",
    "code": "code",
    "data": "data",
    "config": "cfg",
    "text": "txt",
    "other": "obj",
}

PREFIX_TO_KIND: dict[str, str] = {v: k for k, v in KIND_TO_PREFIX.items()}

REF_ID_RE = re.compile(r"^(?P<prefix>[a-z]{2,5})_(?P<suffix>[0-9a-f]{6})$")
GLOBAL_REF_RE = re.compile(r"^(?P<session>[A-Za-z0-9_\-]+)/(?P<ref>[a-z]{2,5}_[0-9a-f]{6})$")
SUFFIX_LEN = 6


def prefix_for(kind: str) -> str:
    """Return the 3-5 char ref prefix for a given file ``kind``.

    Unknown kinds fall back to ``"obj"`` (matching the ``other`` bucket).
    """
    return KIND_TO_PREFIX.get(kind, "obj")


def kind_for_prefix(prefix: str) -> str:
    """Inverse of :func:`prefix_for` — best-effort prefix → kind lookup."""
    return PREFIX_TO_KIND.get(prefix, "other")


def make_ref_id(kind: str) -> str:
    """Generate a random kind-prefixed reference id.

    Args:
        kind: The mm file kind (``image``, ``video``, ``document``,
            ``code``, ``audio``, ``data``, ``config``, ``text``, ``other``).

    Returns:
        Ref string of the form ``<prefix>_<6 lowercase hex chars>``.

    Examples:
        >>> make_ref_id("image")
        'img_a1b2c3'  # random
        >>> make_ref_id("video")
        'vid_4f7e9c'  # random
    """
    return f"{prefix_for(kind)}_{secrets.token_hex(SUFFIX_LEN // 2)}"


def is_valid_ref_id(s: str) -> bool:
    """Return True if ``s`` matches the ``<prefix>_<6 chars>`` shape."""
    return bool(REF_ID_RE.match(s))


def is_valid_global_ref(s: str) -> bool:
    """Return True if ``s`` matches ``<session_id>/<ref_id>``."""
    return bool(GLOBAL_REF_RE.match(s))


@dataclass(frozen=True, slots=True)
class GlobalRef:
    """Parsed ``<session_id>/<ref_id>`` reference.

    Construct via :meth:`parse` to validate the input; constructing directly
    skips validation and is intended for internal use.
    """

    session_id: str
    ref_id: str

    @classmethod
    def parse(cls, s: str) -> GlobalRef:
        """Parse a ``<session_id>/<ref_id>`` string.

        Raises:
            ValueError: If ``s`` is not a valid global ref.
        """
        m = GLOBAL_REF_RE.match(s)
        if not m:
            raise ValueError(
                f"Invalid global ref {s!r}; expected '<session_id>/<prefix>_<6 chars>'"
            )
        return cls(session_id=m.group("session"), ref_id=m.group("ref"))

    @property
    def kind(self) -> str:
        """Best-effort kind inferred from the ref prefix."""
        m = REF_ID_RE.match(self.ref_id)
        return kind_for_prefix(m.group("prefix")) if m else "other"

    def __str__(self) -> str:
        return f"{self.session_id}/{self.ref_id}"


def new_session_id() -> str:
    """Generate a new external session id (UUIDv4 in canonical hex form).

    Kept for backward compatibility. New code that wants a time-ordered
    session id should use :func:`uuid7`.
    """
    return str(uuid.uuid4())


def uuid7() -> str:
    """Generate a UUIDv7 (time-ordered, hyphenated canonical form).

    Python 3.12's :mod:`uuid` module does not include a ``uuid7``
    helper, so mm ships its own — implemented in Rust (see
    ``crates/mm-core/src/refs.rs``) and exposed via
    :func:`mm._mm.uuid7_py`. The format is
    ``xxxxxxxx-xxxx-7xxx-Nxxx-xxxxxxxxxxxx``: a 48-bit millisecond Unix
    timestamp + 74 random bits + version/variant nibbles.

    UUIDv7 is the preferred default for new :class:`mm.Context` session
    ids because ids sort lexicographically in creation order.

    Examples:
        >>> import mm
        >>> sid = mm.uuid7()
        >>> sid.split("-")[2][0]   # version nibble
        '7'

    Returns:
        36-character UUIDv7 string.
    """
    try:
        from mm._mm import uuid7_py as _uuid7  # type: ignore[attr-defined]
    except ImportError:
        # Pure-Python fallback used only when the Rust extension is missing.
        return str(uuid.uuid4())
    return _uuid7()
