"""Context -- the main Python API for mm.

Two modes share the same class:

1. **Incremental put-based context** (the primary, VLM-prompt-building API):

   .. code-block:: python

       import mm
       from pathlib import Path
       from PIL import Image

       ctx = mm.Context(session_id=mm.uuid7())
       img  = ctx.put(Path("photo.jpg"), metadata={"note": "hero shot"})
       doc  = ctx.put(Path("paper.pdf"),
                      metadata={"summary": "Attention is all you need"})
       img2 = ctx.put(Image.open("x.png"))

       messages = ctx.to_messages(format="openai")
       obj = ctx.get(img)

2. **Directory-scan context** (legacy mode, still supported for backward
   compat): ``Context("~/data")`` scans a directory and exposes the Arrow
   table via :meth:`to_polars`, :meth:`sql`, :meth:`show`, etc.

Mode is selected by whether ``root`` is supplied to the constructor. The
incremental mode is backed by the Rust ``_mm.PyContext`` for O(1)
insert/lookup and a sub-millisecond tree/repr render on 1K items.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from mm.refs import Ref, new_session_id, uuid7
from mm.store.db import MmDatabase

if TYPE_CHECKING:
    from PIL import Image as PILImage


_FormatLiteral = Literal["openai", "gemini"]
_TreeLayout = Literal["insertion", "paths", "kind", "flat", "hybrid"]


class _HybridGet:
    """Descriptor that makes ``Context.get`` work as both instance and classmethod.

    * ``ctx.get(ref)`` → calls :meth:`Context._get_instance` (returns the
      stored object / Path / URL for put-based contexts, or the DB row
      for directory-scan contexts).
    * ``Context.get(global_ref, session_id=..., db=...)`` → calls
      :meth:`Context._classmethod_get` (cross-session DB resolver;
      replaces the old ``Context.resolve``).
    """

    def __get__(self, obj: Any, cls: type) -> Any:
        if obj is None:
            resolver = cast(Any, cls)._classmethod_get

            def class_get(
                ref: str,
                *,
                session_id: str | None = None,
                db: Any = None,
            ) -> Any:
                return resolver(ref, default_session=session_id, db=db)

            class_get.__name__ = "get"
            class_get.__doc__ = (
                "Cross-session DB resolver. Parses ``<session_id>/<ref_id>`` "
                "(or accepts a bare ref + ``session_id=...``) and returns "
                "the ``files`` row dict from the mm DB, or ``None`` on miss. "
                "Use the instance form ``ctx.get(ref)`` when you already "
                "have a Context."
            )
            return class_get
        return obj._get_instance


class FileEntry:
    """Lightweight wrapper for a single file's metadata (directory-scan mode).

    Only used by the legacy ``Context(root)`` path. For the incremental
    API, use :meth:`Context.items` / :meth:`Context.get`.
    """

    def __init__(
        self,
        row: dict[str, Any],
        *,
        context: Context | None = None,
    ):
        self._data = row
        self._context = context

    @property
    def kind(self) -> str:
        return str(self._data["kind"])

    @property
    def path(self) -> str:
        return str(self._data["path"])

    @property
    def uri(self) -> str:
        """Absolute uri for this entry. Falls back to the relative path."""
        if self._context is not None and self._context.root is not None:
            return f"{self._context.root}/{self.path}"
        return str(self._data.get("uri") or self.path)

    @property
    def session_id(self) -> str | None:
        if self._context is None:
            return None
        return self._context.session_id

    @property
    def ref_id(self) -> str | None:
        """Per-session ref id, or ``None`` if the context has no session."""
        if self._context is None or self._context.session_id is None:
            return None
        return self._context._materialize_refs().get(self.path)

    @property
    def global_ref(self) -> str | None:
        """Canonical ``<session_id>/<ref_id>`` handle, or ``None``."""
        ref = self.ref_id
        sid = self.session_id
        return f"{sid}/{ref}" if ref and sid else None

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(f"FileEntry has no attribute '{name}'") from None

    def __repr__(self) -> str:
        return (
            f"FileEntry(path='{self._data.get('path', '')}', kind='{self._data.get('kind', '')}')"
        )


class Context:
    """Multimodal context backed by a Rust core.

    When constructed **without a** ``root`` (``Context()`` / ``Context(session_id=...)``)
    the context is *incremental*: use :meth:`put` to attach files, PIL
    images, bytes, or URLs, then :meth:`to_messages` to hand the whole
    context to a VLM.

    When constructed **with a** ``root`` (``Context("~/data")``) it scans
    the directory and exposes the Arrow-backed metadata table (legacy
    mode). Both modes share the same ``session_id`` / ``refs`` surface.

    Args:
        root: Directory to scan. If provided, switches to directory-scan mode.
        n_threads: Optional thread count for the Rust scanner (scan mode only).
        no_ignore: If True, ignore ``.gitignore`` exclusions (scan mode only).
        session_id: External session id. Auto-minted as a UUIDv7 when
            omitted *and* ``root`` is not provided. Stays ``None`` when
            ``root`` is provided without ``session_id`` (preserves the
            legacy default).
        llm_base_url, llm_api_key: Optional LLM overrides.

    Examples:
        Incremental (put-based)::

            ctx = Context()
            ref = ctx.put("photo.jpg", metadata={"note": "hero shot"})
            messages = ctx.to_messages(format="openai")

        Directory-scan (legacy)::

            ctx = Context("~/data", session_id="my-session")
            ctx.save()
            row = Context.get("my-session/" + ctx.ref_for("photo.jpg"))
    """

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        n_threads: int | None = None,
        no_ignore: bool = False,
        session_id: str | None = None,
        llm_base_url: str | None = None,
        llm_api_key: str | None = None,
    ):
        self._llm_base_url = llm_base_url
        self._llm_api_key = llm_api_key
        self._db: MmDatabase | None = None

        if root is None:
            # Incremental put-based mode.
            from mm._mm import PyContext

            sid = session_id if session_id is not None else uuid7()
            self._pyctx: Any = PyContext(session_id=sid)
            self.root: Path | None = None
            self._session_id = sid
            self._no_ignore = False
            self._scanner: Any = None
            self._table: Any = None
            self._refs_cache: dict[str, str] | None = None
        else:
            # Legacy directory-scan mode.
            from mm._mm import Scanner

            self.root = Path(root).resolve()
            self._no_ignore = no_ignore
            self._session_id = session_id
            self._pyctx = None
            self._scanner = Scanner(str(self.root), n_threads, no_ignore=no_ignore)
            self._scanner.scan()
            self._table = self._scanner.to_arrow()
            self._refs_cache: dict[str, str] | None = None

    # ── Shared properties ─────────────────────────────────────────────

    @classmethod
    def new_session(
        cls,
        root: str | Path | None = None,
        **kwargs: Any,
    ) -> Context:
        """Create a Context with a freshly minted session id.

        Convenience for callers who want refs but don't have a session
        id from an upstream system. Legacy signature uses UUIDv4 for
        compatibility; new incremental usage uses UUIDv7 via :func:`uuid7`.
        """
        if root is None:
            return cls(session_id=uuid7(), **kwargs)
        return cls(root, session_id=new_session_id(), **kwargs)

    @property
    def session_id(self) -> str | None:
        """External session id attached to this context, if any."""
        return self._session_id

    @property
    def db(self) -> MmDatabase:
        """Lazy-initialized global database connection."""
        if self._db is None:
            self._db = MmDatabase()
        return self._db

    @property
    def num_files(self) -> int:
        if self._pyctx is not None:
            return self._pyctx.num_items()
        return int(self._table.num_rows)

    # ── Incremental API (put-based) ───────────────────────────────────

    def put(
        self,
        obj: Any,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> Ref:
        """Attach an item to the context and return its kind-prefixed ref id.

        Accepts:
            - :class:`pathlib.Path` or ``str`` pointing to an existing file.
            - :class:`PIL.Image.Image` — held in-memory; recoverable via :meth:`get`.
            - ``bytes`` — MIME-sniffed, held in-memory.
            - URL string (``http://`` / ``https://``) — stored as a remote ref.

        Args:
            obj: Source object (see accepted types above).
            metadata: Optional JSON-serialisable ``dict`` of extra
                context for this item (e.g. ``{"note": "hero shot"}``,
                ``{"summary": "Attention is all you need", "tags":
                ["nlp"]}``). Stable key order is preserved. The
                metadata flows into :meth:`__repr__`, :meth:`to_md`,
                :meth:`print_tree`, and :meth:`to_messages` (emitted as
                a leading text block per item so the VLM sees it
                inline).

        Returns:
            The generated ref id (``<prefix>_<6 hex>``). The return type
            is :data:`mm.refs.Ref` — a typed alias over ``str``.

        Raises:
            RuntimeError: If called on a directory-scan Context.
            TypeError: If ``obj`` is of an unsupported type.
        """
        self._require_pyctx("put")
        kind, source_kind, source_value, byte_len, desc, py_obj = _classify_put_obj(obj)
        metadata_json = json.dumps(metadata) if metadata else None

        ref_id: str = self._pyctx.put(
            kind,
            source_kind,
            source_value,
            byte_len=byte_len,
            desc=desc,
            py_obj=py_obj,
            metadata_json=metadata_json,
        )
        return ref_id

    def items(self) -> list[dict[str, Any]]:
        """Return all items as dicts (insertion order).

        Each dict has keys ``ref_id``, ``kind``, ``source_kind``,
        ``source_value``, ``byte_len``, ``desc``, and ``metadata``.
        """
        self._require_pyctx("items")
        return list(self._pyctx.items())

    def ref_ids(self) -> list[Ref]:
        """All ref ids in insertion order."""
        self._require_pyctx("ref_ids")
        return list(self._pyctx.ref_ids())

    def to_messages(
        self,
        format: _FormatLiteral = "openai",
        *,
        encoders: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Encode every item into a single VLM message list.

        Args:
            format: Message shape. ``"openai"`` returns the
                ``chat.completions``-style ``[{"role": "user", "content":
                [...]}]`` list. ``"gemini"`` adapts image parts to the
                ``inline_data`` Part shape.
            encoders: Per-kind encoder overrides, e.g. ``{"image": "tile",
                "video": "mosaic"}``. Unspecified kinds fall back to
                sensible defaults (``image-resize``, ``video-frame-sample``,
                ``document-rasterize``).

        Returns:
            A list containing a single user turn; drop directly into
            ``client.chat.completions.create(messages=...)`` (OpenAI) or
            the Gemini ``generate_content`` call.

        Raises:
            ValueError: If ``format`` is not ``"openai"`` or ``"gemini"``.
            RuntimeError: If called on a directory-scan Context.
        """
        if format not in ("openai", "gemini"):
            raise ValueError(f"format must be 'openai' or 'gemini', got {format!r}")
        self._require_pyctx("to_messages")

        from mm.refs_messages import build_messages

        return build_messages(self, format=format, encoders=encoders or {})

    def to_md(self, mode: Literal["fast", "accurate"] = "fast") -> str:
        """Render a markdown table of every ref + source + content.

        Args:
            mode: ``"fast"`` populates each row with the metadata-tier content
                (``files.text_preview`` produced by ``extract_meta``; no LLM call).
                ``"accurate"`` runs the LLM-backed path (requires a
                configured profile; not wired yet — currently raises
                ``NotImplementedError``).

        Returns:
            Markdown table (headers: ref | kind | source | content).
        """
        self._require_pyctx("to_md")
        if mode == "accurate":
            raise NotImplementedError(
                "to_md(mode='accurate') is not implemented yet. "
                "Use mode='fast' for the metadata-tier content."
            )
        contents = self._collect_fast_contents()
        return self._pyctx.to_md_table(contents)

    def print_tree(self, layout: _TreeLayout = "insertion") -> None:
        """Print a rich.Tree view of the context.

        Args:
            layout: Visual layout. Default ``"insertion"``.

                - ``"insertion"``: insertion-order, metadata rendered beneath
                  each item (T4). [implemented]
                - ``"paths"``: directory hierarchy with refs on the right
                  (T1). [TODO]
                - ``"kind"``: grouped by kind: images / documents / videos /
                  … (T2). [TODO]
                - ``"flat"``: ref-first flat list (T3). [TODO — likely
                  better as ``ctx.print_table()``]
                - ``"hybrid"``: paths + per-item dim metadata line (T5).
                  [TODO]

        Raises:
            NotImplementedError: For any non-``"insertion"`` layout.
        """
        self._require_pyctx("print_tree")
        if layout != "insertion":
            raise NotImplementedError(
                f"print_tree(layout={layout!r}) is not implemented yet. "
                "Only layout='insertion' is available in this release."
            )
        from mm.display import output_console

        output_console.print(self._pyctx.render_tree_insertion())

    # ── Unified get (instance + classmethod hybrid) ───────────────────

    get = _HybridGet()  # type: ignore[assignment]  # descriptor assigned below

    def _get_instance(self, ref_id: str) -> Any:
        """Instance ``ctx.get(ref)`` — local lookup.

        - Incremental mode: returns the Path / PIL.Image / bytes / URL
          stored at ``ref_id``.
        - Directory-scan mode: returns the DB row for the global ref.

        Raises:
            RefNotFoundError: Bare ref id not found in the context.
            ValueError: Malformed global ref or mismatched session id.
        """
        bare = _strip_session_prefix(ref_id, self._session_id)
        if self._pyctx is not None:
            return self._pyctx.get(bare)
        return Context._classmethod_get(
            f"{self._session_id}/{bare}" if self._session_id else bare,
            default_session=self._session_id,
            db=self._db,
        )

    @classmethod
    def _classmethod_get(
        cls,
        ref: str,
        *,
        default_session: str | None = None,
        db: MmDatabase | None = None,
    ) -> dict[str, Any] | None:
        """Cross-session DB resolver for persisted contexts."""
        from mm.refs import GlobalRef

        if "/" in ref:
            parsed = GlobalRef.parse(ref)
            sid, rid = parsed.session_id, parsed.ref_id
        elif default_session is not None:
            sid, rid = default_session, ref
        else:
            raise ValueError(
                f"ambiguous ref {ref!r}: pass a global '<session_id>/<ref_id>' "
                "or supply session_id=..."
            )
        if db is None:
            db = MmDatabase()
        return db.get_file_by_ref(sid, rid)

    @staticmethod
    def resolve(
        global_ref: str,
        *,
        db: MmDatabase | None = None,
    ) -> dict[str, Any] | None:
        """Legacy DB resolver kept for backward compatibility.

        New code should prefer :meth:`get` (instance for local lookup,
        classmethod for cross-session DB lookup).
        """
        return Context._classmethod_get(global_ref, db=db)

    # ── Persistence (deferred for put-based) ──────────────────────────

    def save(self) -> None:
        """Persist the context.

        For directory-scan contexts, writes the Arrow table to the
        global mm DB (existing behaviour).

        For incremental put-based contexts, this is **not implemented
        yet**. Planned behaviour:

            - Write ``(session_id, ref_id, kind, uri, content_hash, metadata)``
              to the ``files`` table in ``~/.local/share/mm/mm.db``.
            - For in-memory objects, spool to a content-addressed cache
              dir (``~/.local/share/mm/blobs/<xxh3>.<ext>``) and record
              the blob URI.
            - Make ``Context.get("<session>/<ref>")`` resolve via the DB
              across processes.
            - Idempotent on repeat calls for the same
              ``(session_id, ref_id)``.

        Raises:
            NotImplementedError: For incremental (put-based) contexts.
        """
        if self._pyctx is not None:
            raise NotImplementedError(
                "Context.save() is not implemented for incremental (put-based) contexts yet. "
                "See Context.save docstring for the planned behaviour."
            )
        refs = self._materialize_refs() if self._session_id else None
        assert self.root is not None
        self.db.upsert_files(self._table, self.root, session_id=self._session_id, refs=refs)

    # ── Directory-scan API (preserved) ────────────────────────────────

    @property
    def files(self) -> list[FileEntry]:
        """List all files as :class:`FileEntry` (directory-scan mode)."""
        if self._pyctx is not None:
            raise RuntimeError(
                "Context.files is only available on directory-scan contexts. "
                "Use ctx.items() for incremental put-based contexts."
            )
        rows = self._table.to_pydict()
        result = []
        for i in range(self._table.num_rows):
            row = {col: rows[col][i] for col in rows}
            result.append(FileEntry(row, context=self))
        return result

    def _table_with_refs(self):
        """Return the Arrow table with ``session_id`` + ``ref_id`` appended."""
        import pyarrow as pa

        table = self._table
        if self._session_id is None:
            return table
        ref_map = self._materialize_refs()
        paths = table.column("path").to_pylist()
        ref_ids = [ref_map.get(p) for p in paths]
        sess_col = pa.array([self._session_id] * len(paths), type=pa.string())
        ref_col = pa.array(ref_ids, type=pa.string())
        return table.append_column("session_id", sess_col).append_column("ref_id", ref_col)

    def to_polars(self, *, refs: bool = False):
        """Convert to Polars DataFrame (directory-scan mode)."""
        self._require_table("to_polars")
        from mm.df import arrow_to_polars

        table = self._table_with_refs() if refs else self._table
        return arrow_to_polars(table)

    def to_pandas(self, *, refs: bool = False):
        """Convert to Pandas DataFrame (directory-scan mode)."""
        self._require_table("to_pandas")
        from mm.df import arrow_to_pandas

        table = self._table_with_refs() if refs else self._table
        return arrow_to_pandas(table)

    def to_arrow(self, *, refs: bool = False):
        """Return the underlying PyArrow Table (directory-scan mode)."""
        self._require_table("to_arrow")
        return self._table_with_refs() if refs else self._table

    def sql(self, query: str):
        """Run a SQL query against the directory-scan Arrow table."""
        self._require_table("sql")
        from mm.query import query_arrow_table

        return query_arrow_table(self._table, query)

    def filter(
        self,
        *,
        kind: str | None = None,
        ext: str | list[str] | None = None,
        min_size: str | int | None = None,
        max_size: str | int | None = None,
        modified_after: str | None = None,
    ) -> Context:
        """Return a new directory-scan Context with filtered rows."""
        self._require_table("filter")
        conditions: list[str] = []

        if kind:
            if "," in kind:
                kinds = ", ".join(f"'{k.strip()}'" for k in kind.split(","))
                conditions.append(f"kind IN ({kinds})")
            else:
                conditions.append(f"kind = '{kind}'")
        if ext:
            if isinstance(ext, str):
                ext = [e.strip() for e in ext.split(",")]
            ext_list = ", ".join(f"'{e}'" for e in ext)
            conditions.append(f"ext IN ({ext_list})")
        if min_size is not None:
            size_bytes = _parse_size(min_size) if isinstance(min_size, str) else min_size
            conditions.append(f"size >= {size_bytes}")
        if max_size is not None:
            size_bytes = _parse_size(max_size) if isinstance(max_size, str) else max_size
            conditions.append(f"size <= {size_bytes}")

        if not conditions:
            return self

        from mm.query import query_arrow_table

        where_clause = " AND ".join(conditions)
        filtered = query_arrow_table(self._table, f"SELECT * FROM files WHERE {where_clause}")

        new_ctx = object.__new__(Context)
        new_ctx.root = self.root
        new_ctx._llm_base_url = self._llm_base_url
        new_ctx._llm_api_key = self._llm_api_key
        new_ctx._scanner = self._scanner
        new_ctx._table = filtered
        new_ctx._db = self._db
        new_ctx._no_ignore = self._no_ignore
        new_ctx._session_id = self._session_id
        new_ctx._refs_cache = None

        new_ctx._pyctx = None
        return new_ctx

    def cat(self, path: str) -> str:
        """Read locally-extracted (metadata-tier) content of a file (directory-scan mode)."""
        self._require_table("cat")
        assert self.root is not None
        full_path = self.root / path
        from mm.cat_utils.extract_meta import extract_meta
        from mm.utils import file_kind

        kind = file_kind(full_path)
        if kind == "text":
            return full_path.read_text(errors="replace")
        return extract_meta(full_path, kind)

    def head(self, path: str, *, n: int = 10) -> str:
        content = self.cat(path)
        return "\n".join(content.splitlines()[:n])

    def tail(self, path: str, *, n: int = 10) -> str:
        content = self.cat(path)
        return "\n".join(content.splitlines()[-n:])

    def encode(
        self,
        path: str,
        *,
        strategy: str | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Encode a file into VLM-ready Message dicts (directory-scan)."""
        self._require_table("encode")
        from mm.encoders import get as get_encoder
        from mm.utils import file_kind

        assert self.root is not None
        full_path = self.root / path
        if not full_path.exists():
            raise FileNotFoundError(f"{path} not found in {self.root}")

        media_type = file_kind(full_path.name)
        if strategy is None:
            strategy = {
                "image": "image-resize",
                "video": "video-frame-sample",
                "document": "document-rasterize",
            }.get(media_type, "image-resize")

        strat = get_encoder(strategy)
        return list(strat.encode(full_path, **kwargs))

    def grep(self, pattern: str, *, kind: str | None = None) -> list[dict[str, Any]]:
        """Search for a pattern across scanned files."""
        self._require_table("grep")
        import re

        matches: list[dict[str, Any]] = []
        target = self.filter(kind=kind) if kind else self

        for f in target.files:
            try:
                content = self.cat(f.path)
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pattern, line):
                        matches.append({"path": f.path, "line_number": i, "line": line})
            except Exception:
                continue
        return matches

    def show(
        self,
        *,
        limit: int | None = 50,
        columns: list[str] | None = None,
        refs: bool = False,
    ) -> None:
        """Display the index as a Rich table (directory-scan mode)."""
        self._require_table("show")
        from mm.display import arrow_table_to_rich, output_console

        table = self._table_with_refs() if refs else self._table
        if refs and columns is None:
            columns = [c for c in table.column_names if c != "session_id"]
        rich_table = arrow_table_to_rich(table, columns=columns, limit=limit)
        output_console.print(rich_table)

    def info(self) -> None:
        """Display summary statistics as a Rich panel (directory-scan mode)."""
        self._require_table("info")
        import collections

        from mm.display import format_size, info_panel, output_console

        total_size = sum(r.as_py() for r in self._table.column("size"))
        kinds = collections.Counter(r.as_py() for r in self._table.column("kind"))
        exts = collections.Counter(r.as_py() for r in self._table.column("ext"))
        top_exts = exts.most_common(5)

        stats: dict[str, Any] = {
            "Files": self.num_files,
            "Total Size": format_size(total_size),
            "Root": str(self.root),
        }
        for k, count in sorted(kinds.items(), key=lambda x: -x[1]):
            stats[k.capitalize()] = count

        ext_str = ", ".join(f"{e} ({c})" for e, c in top_exts)
        stats["Top Extensions"] = ext_str

        assert self.root is not None
        panel = info_panel(stats, title=self.root.name)
        output_console.print(panel)

    # ── Legacy ref helpers (directory-scan) ──────────────────────────

    def _uri_for(self, path: str) -> str:
        assert self.root is not None
        return f"{self.root}/{path.lstrip('/')}"

    def _require_session(self) -> str:
        if self._session_id is None:
            raise ValueError(
                "Context has no session_id; pass session_id=... to Context() "
                "or use Context.new_session() to enable refs."
            )
        return self._session_id

    def _materialize_refs(self) -> dict[str, str]:
        """Build-or-return cached ``{path: ref_id}`` (directory-scan mode)."""
        if self._refs_cache is not None:
            return self._refs_cache
        session_id = self._require_session()
        from mm.refs import make_ref_id

        paths = self._table.column("path").to_pylist()
        kinds = self._table.column("kind").to_pylist()

        existing: dict[str, str] = {}
        if self._db is not None or MmDatabase.DB_PATH.exists():
            try:
                rows = self.db.list_session_files(session_id)
                assert self.root is not None
                root_s = f"{self.root}/"
                for r in rows:
                    uri = str(r.get("uri") or "")
                    ref = r.get("ref_id")
                    if ref and uri.startswith(root_s):
                        existing[uri[len(root_s) :]] = str(ref)
            except Exception:
                existing = {}

        out: dict[str, str] = {}
        for p, k in zip(paths, kinds):
            out[p] = existing.get(p) or make_ref_id(k or "other")
        self._refs_cache = out
        return out

    def ref_for(self, path: str) -> str:
        """Return the ref id for a scanned ``path`` (directory-scan mode)."""
        self._require_table("ref_for")
        refs = self._materialize_refs()
        if path not in refs:
            raise ValueError(f"{path!r} is not in this context")
        return refs[path]

    def global_ref(self, path: str) -> str:
        """Return ``<session_id>/<ref_id>`` for ``path`` (directory-scan)."""
        self._require_table("global_ref")
        return f"{self._require_session()}/{self.ref_for(path)}"

    @property
    def refs(self) -> dict[str, str]:
        """Mapping of ``path -> global_ref`` for every file (scan mode).

        For put-based contexts, returns ``{ref_id: <session>/<ref>}`` for
        every stored item.
        """
        if self._pyctx is not None:
            return {r: f"{self._session_id}/{r}" for r in self._pyctx.ref_ids()}
        if self._session_id is None:
            return {}
        local = self._materialize_refs()
        return {p: f"{self._session_id}/{r}" for p, r in local.items()}

    # ── Internals ────────────────────────────────────────────────────

    def _collect_fast_contents(self) -> dict[str, str]:
        """Extract ``cat``-like content for every put-based item (fast mode)."""
        from mm.cat_utils.extract_meta import extract_meta
        from mm.utils import file_kind

        out: dict[str, str] = {}
        for item in self._pyctx.items():
            ref_id = item["ref_id"]
            src_kind = item["source_kind"]
            src = item["source_value"]
            if src_kind == "path":
                p = Path(src)
                if not p.exists():
                    continue
                kind = file_kind(p)
                try:
                    if kind == "text":
                        out[ref_id] = p.read_text(errors="replace")
                    else:
                        out[ref_id] = extract_meta(p, kind)
                except Exception as exc:  # noqa: BLE001
                    out[ref_id] = f"[extract failed: {exc}]"
            # in-memory / url items fall through to the metadata fallback
            # handled by the Rust-side to_md_with_contents.
        return out

    def _require_pyctx(self, method: str) -> None:
        if self._pyctx is None:
            raise RuntimeError(
                f"Context.{method}() requires an incremental (put-based) context. "
                "Construct with Context() / Context(session_id=...) (no root)."
            )

    def _require_table(self, method: str) -> None:
        if self._table is None:
            raise RuntimeError(
                f"Context.{method}() requires a directory-scan context. "
                "Construct with Context(root=...)."
            )

    # ── Reprs ────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        if self._pyctx is not None:
            return self._pyctx.repr_markdown()
        sess = f", session='{self._session_id}'" if self._session_id else ""
        return f"Context(root='{self.root}', files={self.num_files}{sess})"

    def __len__(self) -> int:
        return self.num_files


# ── Helpers ──────────────────────────────────────────────────────────


def _parse_size(size_str: str) -> int:
    """Parse human-readable size string to bytes (e.g., '1MB', '500KB')."""
    size_str = size_str.strip().upper()
    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    for suffix, mult in sorted(multipliers.items(), key=lambda x: -len(x[0])):
        if size_str.endswith(suffix):
            num = size_str[: -len(suffix)].strip()
            return int(float(num) * mult)
    return int(size_str)


def _strip_session_prefix(ref: str, session_id: str | None) -> str:
    """If ``ref`` is a ``<sess>/<rid>`` string, strip the session prefix.

    Raises ``ValueError`` when the session segment doesn't match this
    context's own ``session_id`` (only when a context is bound).
    """
    if "/" not in ref:
        return ref
    sid, rid = ref.split("/", 1)
    if session_id is not None and sid != session_id:
        raise ValueError(
            f"global ref {ref!r} belongs to session {sid!r}, not this context ({session_id!r})"
        )
    return rid


def _classify_put_obj(
    obj: Any,
) -> tuple[str, str, str, int | None, str | None, Any]:
    """Inspect ``obj`` and return ``(kind, source_kind, source_value, byte_len, desc, py_obj)``.

    The tuple feeds directly into the Rust ``PyContext.put`` signature.
    """
    from mm._mm import kind_for_name

    try:
        from PIL import Image as _PILImageMod  # noqa: PLC0415

        _PILImage: Any = _PILImageMod
    except ImportError:  # pragma: no cover - PIL is a hard dep in mm
        _PILImage = None

    # PIL.Image
    if _PILImage is not None and isinstance(obj, _PILImage.Image):
        w, h = obj.size
        mode = obj.mode
        desc = f"PIL.Image({mode}, {w}×{h})"
        byte_len = _estimate_pil_bytes(obj, mode, w, h)
        return ("image", "in_memory", "image/pil", byte_len, desc, obj)

    # bytes
    if isinstance(obj, (bytes, bytearray, memoryview)):
        raw = bytes(obj)
        mime = _sniff_mime(raw)
        kind = _mime_to_kind(mime)
        desc = f"<bytes {len(raw)} {mime}>"
        return (kind, "in_memory", mime, len(raw), desc, raw)

    # str -> URL or path
    if isinstance(obj, str):
        if obj.startswith(("http://", "https://", "file://", "data:")):
            return (kind_for_name(obj), "url", obj, None, obj, None)
        p = Path(obj)
        if p.exists():
            return _classify_path(p)
        # Non-existing str: treat as URL / unresolved path — raise for clarity.
        raise FileNotFoundError(
            f"put({obj!r}): file does not exist. Pass a pathlib.Path for "
            "on-disk files, a PIL.Image / bytes for in-memory objects, or an "
            "http(s):// URL for remote references."
        )

    # pathlib.Path
    if isinstance(obj, Path):
        if not obj.exists():
            raise FileNotFoundError(f"put({obj!r}): file does not exist")
        return _classify_path(obj)

    # os.PathLike (covers most custom path types)
    if isinstance(obj, os.PathLike):
        return _classify_path(Path(obj))

    raise TypeError(
        f"put() does not accept {type(obj).__name__}. Supported types: "
        "pathlib.Path, str (file path or URL), bytes, PIL.Image.Image."
    )


def _classify_path(p: Path) -> tuple[str, str, str, int | None, str | None, Any]:
    from mm.utils import file_kind_with_code

    kind = file_kind_with_code(p)
    abs_path = str(p.resolve())
    return (kind, "path", abs_path, None, abs_path, None)


def _estimate_pil_bytes(img: "PILImage.Image", mode: str, w: int, h: int) -> int:
    """Cheap upper-bound on in-memory decoded byte length."""
    bpp = {"1": 1, "L": 1, "P": 1, "RGB": 3, "RGBA": 4, "CMYK": 4, "I": 4, "F": 4}.get(mode, 3)
    return int(w) * int(h) * bpp


def _sniff_mime(data: bytes) -> str:
    """Best-effort MIME detection for raw bytes.

    Uses the existing ``infer``-backed ``_mm.content_hash``-style path
    if available; else a handful of magic prefixes.
    """
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"ID3") or (len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "audio/mpeg"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video/mp4"
    return "application/octet-stream"


def _mime_to_kind(mime: str) -> str:
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    if mime in ("application/pdf",) or mime.startswith(("application/vnd.openxmlformats",)):
        return "document"
    return "other"
