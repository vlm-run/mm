"""Context -- the main Python API for mm.

Two modes share the same class:

1. **Incremental role-aware context** (the primary, VLM-prompt-building API):

   .. code-block:: python

       import mm
       from pathlib import Path
       from PIL import Image

       ctx = mm.Context(session_id=mm.uuid7())
       sys  = ctx.add("You are a terse visual analyst.", role="system")
       text = ctx.add("Summarize the following assets.", role="user")
       img  = ctx.add(Path("photo.jpg"), role="user", metadata={"note": "hero shot"})
       doc  = ctx.add(Path("paper.pdf"), role="user",
                      metadata={"summary": "Attention is all you need"})
       img2 = ctx.add(Image.open("x.png"), role="user")

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
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from mm.refs import Ref, new_session_id, uuid7

if TYPE_CHECKING:
    import re

    from PIL import Image as PILImage

    from mm.cat_utils.base_utils import CatOpts
    from mm.peek import FileMetadata
    from mm.results import GrepResult, WcStats


_FormatLiteral = Literal["openai", "gemini"]
_RoleLiteral = Literal["system", "developer", "user"]
_TreeLayout = Literal["insertion", "paths", "kind", "flat", "hybrid"]


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
    the context is *incremental*: use :meth:`add` to attach free-form
    strings, ``pathlib.Path`` objects, or ``PIL.Image.Image`` instances
    under a chat role, then :meth:`to_messages` to hand the whole
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
        llm_base_url: Optional LLM overrides for base_url.
        llm_api_key: Optional LLM overrides for api_key.

    Examples:
        Incremental (role-aware)::

            ctx = Context()
            prompt = ctx.add("Describe this image.", role="user")
            ref = ctx.add(Path("photo.jpg"), role="user", metadata={"note": "hero shot"})
            messages = ctx.to_messages(format="openai")

        Directory-scan (legacy)::

            ctx = Context("~/data", session_id="my-session")
            # The library exports records; the caller owns persistence.
            from mm.store.db import MmDatabase
            db = MmDatabase()
            db.upsert_records(ctx.to_records(refs=True), root=ctx.root)
            row = db.resolve("my-session/" + ctx.ref_for("photo.jpg"))
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

        if root is None:
            # Incremental role-aware mode.
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
    def num_files(self) -> int:
        if self._pyctx is not None:
            return self._pyctx.num_items()
        return int(self._table.num_rows)

    # ── Incremental API (role-aware) ──────────────────────────────────

    def add(
        self,
        obj: str | Path | "PILImage.Image",
        *,
        role: _RoleLiteral = "user",
        metadata: dict[str, Any] | None = None,
    ) -> Ref:
        """Attach an item to the context and return its kind-prefixed ref id.

        Accepts:
            - ``str`` — free-form text, inlined under any supported role.
            - :class:`pathlib.Path` pointing to an existing file (``role="user"`` only).
            - :class:`PIL.Image.Image` — held in-memory (``role="user"`` only).

        Args:
            obj: Free-form text, a ``pathlib.Path``, or ``PIL.Image.Image``.
            role: Chat role for this item: ``"system"``, ``"developer"``, or ``"user"``.
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
            ValueError: If ``role`` is invalid or a media object is added
                to a non-user role.
            FileNotFoundError: If ``obj`` is a Path that doesn't exist.
            TypeError: If ``obj`` is not a str, Path, or PIL.Image.Image.
        """
        self._require_pyctx("add")
        role = _validate_role(role)
        kind, source_kind, source_value, byte_len, desc, py_obj = _classify_add_obj(obj)
        if role != "user" and kind != "text":
            raise ValueError("Only free-form string text can use role='system' or role='developer'")
        metadata_json = json.dumps(metadata) if metadata else None

        ref_id: str = self._pyctx.add(
            role,
            kind,
            source_kind,
            source_value,
            byte_len=byte_len,
            desc=desc,
            py_obj=py_obj,
            metadata_json=metadata_json,
        )
        return ref_id

    def remove(self, ref_id: str) -> None:
        """Remove an item from an incremental context by ref id.

        Args:
            ref_id: Bare ref id or a global ``<session_id>/<ref_id>`` whose
                session matches this context.

        Raises:
            RuntimeError: If called on a directory-scan Context.
            RefNotFoundError: If ``ref_id`` is not present.
            ValueError: If a global ref belongs to a different session.
        """
        self._require_pyctx("remove")
        bare = _strip_session_prefix(ref_id, self._session_id)
        self._pyctx.remove(bare)

    def items(self) -> list[dict[str, Any]]:
        """Return all items as dicts (insertion order).

        Each dict has keys ``ref_id``, ``role``, ``kind``, ``source_kind``,
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
        encoder_kwargs: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Encode every item into a role-aware VLM message list.

        Args:
            format: Message shape. ``"openai"`` returns one
                ``chat.completions``-style message per consecutive role
                run. ``"gemini"`` adapts image parts to the
                ``inline_data`` Part shape and folds non-user roles into
                labelled text parts.
            encoders: Per-kind encoder overrides, e.g. ``{"image": "tile",
                "video": "mosaic"}``. Unspecified kinds fall back to
                sensible defaults (``resize``, ``mosaic``, ``rasterize``, ``base64``).
            encoder_kwargs: Per-kind keyword arguments forwarded to the
                encoder's ``encode()`` method, e.g.
                ``{"document": {"pages_per_message": 8}}``.

        Returns:
            Message dicts for ``client.chat.completions.create`` (OpenAI)
            or the Gemini ``generate_content`` call.

        Raises:
            ValueError: If ``format`` is not ``"openai"`` or ``"gemini"``.
            RuntimeError: If called on a directory-scan Context.
        """
        if format not in ("openai", "gemini"):
            raise ValueError(f"format must be 'openai' or 'gemini', got {format!r}")
        self._require_pyctx("to_messages")

        from mm.refs_messages import build_messages

        return build_messages(
            self, format=format, encoders=encoders or {}, encoder_kwargs=encoder_kwargs or {}
        )

    def to_md(self, mode: Literal["metadata", "fast", "accurate"] = "metadata") -> str:
        """Render a markdown table of every ref + source + content.

        Args:
            mode: ``"metadata"`` populates each row with the metadata-tier content
                (``files.text_preview`` produced by ``extract_meta``; no LLM call).
                ``"fast"`` runs the light pipeline extraction and ``"accurate"``
                runs the LLM-backed pipeline (both require a configured
                profile). Both route through
                :func:`mm.cat_utils.extract.extract`.

        Returns:
            Markdown table (headers: ref | kind | source | content).
        """
        self._require_pyctx("to_md")
        if mode == "metadata":
            contents = self._collect_metadata_contents()
        else:
            contents = self._collect_pipeline_contents(mode)
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
            ValueError: If ``layout`` is not one of the supported layouts.
        """
        self._require_pyctx("print_tree")
        from mm.display import output_console

        if layout == "insertion":
            output_console.print(self._pyctx.render_tree_insertion())
            return
        if layout not in ("paths", "kind", "flat", "hybrid"):
            raise ValueError(
                f"print_tree(layout={layout!r}) is invalid. Choose from "
                "'insertion', 'paths', 'kind', 'flat', 'hybrid'."
            )
        output_console.print(self._build_tree_view(layout))

    def _build_tree_view(self, layout: _TreeLayout) -> Any:
        """Build a ``rich.Tree`` for the given non-insertion layout."""
        from rich.text import Text
        from rich.tree import Tree

        items = list(self._pyctx.items())
        root_label = Text()
        root_label.append("Context", style="bold")
        root_label.append(f"  {len(items)} items", style="dim")
        tree = Tree(root_label)

        def _leaf(item: dict[str, Any], *, with_meta: bool) -> Text:
            label = Text()
            src_kind = item["source_kind"]
            if src_kind == "path":
                label.append(Path(item["source_value"]).name)
            elif item["kind"] == "text":
                preview = (item.get("desc") or item.get("source_value") or "").strip()
                label.append((preview[:60] + "…") if len(preview) > 60 else preview or "(text)")
            else:
                label.append(str(item.get("source_value") or item["kind"]))
            label.append(f"  {item['ref_id']}", style="dim")
            if with_meta and item.get("metadata"):
                label.append(f"  {item['metadata']}", style="dim italic")
            return label

        if layout == "flat":
            for item in items:
                line = Text()
                line.append(f"{item['ref_id']}", style="bold")
                line.append(f"  [{item['kind']}] ", style="dim")
                src = (
                    Path(item["source_value"]).name
                    if item["source_kind"] == "path"
                    else str(item.get("desc") or item.get("source_value") or "")
                )
                line.append(src[:80])
                tree.add(line)
            return tree

        if layout == "kind":
            by_kind: dict[str, list[dict[str, Any]]] = {}
            for item in items:
                by_kind.setdefault(item["kind"], []).append(item)
            for kind in sorted(by_kind):
                branch = tree.add(Text(f"{kind} ({len(by_kind[kind])})", style="bold"))
                for item in by_kind[kind]:
                    branch.add(_leaf(item, with_meta=False))
            return tree

        # "paths" and "hybrid": directory hierarchy for path items.
        with_meta = layout == "hybrid"
        path_items = [it for it in items if it["source_kind"] == "path"]
        inline_items = [it for it in items if it["source_kind"] != "path"]

        import os.path as _osp

        try:
            common = (
                Path(_osp.commonpath([it["source_value"] for it in path_items]))
                if len(path_items) > 1
                else (Path(path_items[0]["source_value"]).parent if path_items else None)
            )
        except ValueError:
            # Paths share no common root (e.g. different Windows drives).
            common = None
        if common is not None and common.is_file():
            common = common.parent

        dir_nodes: dict[str, Any] = {}

        def _dir_branch(directory: Path) -> Any:
            key = str(directory)
            if key in dir_nodes:
                return dir_nodes[key]
            at_root = directory.parent == directory
            if at_root or (
                common is not None and (directory == common or common not in directory.parents)
            ):
                node = tree.add(Text(f"{directory}/", style="bold"))
            else:
                node = _dir_branch(directory.parent).add(Text(f"{directory.name}/", style="bold"))
            dir_nodes[key] = node
            return node

        for item in path_items:
            p = Path(item["source_value"])
            _dir_branch(p.parent).add(_leaf(item, with_meta=with_meta))
        if inline_items:
            inline = tree.add(Text("(inline)", style="dim"))
            for item in inline_items:
                inline.add(_leaf(item, with_meta=with_meta))
        return tree

    # ── Unified get (in-memory, role-aware) ───────────────────────────

    def get(self, ref_id: str) -> Any:
        """Look up an item by ref id (incremental role-aware mode).

        Returns the ``str``, ``Path``, or ``PIL.Image.Image`` stored at
        ``ref_id``. Accepts either a bare ref id or a
        ``<session_id>/<ref_id>`` global ref matching this context's
        session.

        Persistence and cross-session lookups are the caller's
        responsibility — the library never reads a database. Export with
        :meth:`to_records` and resolve through your own store (e.g.
        ``mm.store.db.MmDatabase().resolve(ref)``).

        Raises:
            RefNotFoundError: Ref id not found in the context.
            ValueError: Malformed global ref or mismatched session id.
            RuntimeError: Called on a directory-scan context.
        """
        if self._pyctx is None:
            raise RuntimeError(
                "Context.get() resolves in-memory role-aware refs only. "
                "Directory-scan persistence and cross-session lookups are the "
                "caller's responsibility: export with Context.to_records() and "
                "resolve via your own store (e.g. MmDatabase().resolve(ref))."
            )
        bare = _strip_session_prefix(ref_id, self._session_id)
        return self._pyctx.get(bare)

    # ── Persistence export (storage-agnostic) ─────────────────────────

    def to_records(self, *, refs: bool = False) -> list[dict[str, Any]]:
        """Export the context as plain dict records (storage-agnostic).

        This is the persistence-decoupling entry point: the library never
        writes to a database. ``to_records`` hands you the data so *you*
        decide the storage backend (SQLite, Postgres, object storage, a
        JSONL file, ...). Pair it with :meth:`items` blob access for any
        in-memory objects you need to spool out.

        Args:
            refs: Directory-scan only — append ``session_id``/``ref_id``
                columns to each record.

        Returns:
            One dict per file (directory-scan) or per ref (incremental,
            same fields as :meth:`items`).
        """
        if self._pyctx is not None:
            return [dict(item) for item in self._pyctx.items()]
        self._require_table("to_records")
        table = self._table_with_refs() if refs else self._table
        return table.to_pylist()

    # ── Directory-scan API (preserved) ────────────────────────────────

    @property
    def files(self) -> list[FileEntry]:
        """List all files as :class:`FileEntry` (directory-scan mode)."""
        if self._pyctx is not None:
            raise RuntimeError(
                "Context.files is only available on directory-scan contexts. "
                "Use ctx.items() for incremental role-aware contexts."
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
        name: str | None = None,
        ignore_case: bool = False,
        depth: int | None = None,
        sort: str | None = None,
        reverse: bool = False,
        limit: int | None = None,
    ) -> Context:
        """Return a new directory-scan Context with filtered/sorted rows.

        Source of truth for ``mm find``'s row selection. All predicates
        compose; an unfiltered call returns ``self`` unchanged.

        Args:
            kind: Kind filter (single or comma-separated, e.g. ``"image,document"``).
            ext: Extension filter — a comma-separated string or list (``".pdf"``).
            min_size: Minimum size; ``int`` bytes or human string (``"1mb"``).
            max_size: Maximum size; ``int`` bytes or human string.
            modified_after: Reserved for future mtime filtering.
            name: Filter by file name. Tried as a regex first, falling back
                to a case-(in)sensitive substring match.
            ignore_case: Case-insensitive ``name`` matching.
            depth: Maximum directory depth (0 = top-level).
            sort: Column to sort by (e.g. ``"size"``, ``"name"``).
            reverse: Sort descending when ``True``.
            limit: Keep at most this many rows (applied last).

        Returns:
            A new directory-scan :class:`Context` over the filtered table.
        """
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
        if depth is not None:
            conditions.append(f"depth <= {depth}")

        if not conditions and name is None and not sort and limit is None:
            return self

        from mm.query import query_arrow_table

        filtered = self._table
        if conditions:
            where_clause = " AND ".join(conditions)
            filtered = query_arrow_table(filtered, f"SELECT * FROM files WHERE {where_clause}")

        if name is not None:
            filtered = self._filter_by_name(filtered, name, ignore_case)

        if sort:
            order = "DESC" if reverse else "ASC"
            filtered = query_arrow_table(filtered, f"SELECT * FROM files ORDER BY {sort} {order}")

        if limit is not None and limit < filtered.num_rows:
            filtered = filtered.slice(0, limit)

        new_ctx = object.__new__(Context)
        new_ctx.root = self.root
        new_ctx._llm_base_url = self._llm_base_url
        new_ctx._llm_api_key = self._llm_api_key
        new_ctx._scanner = self._scanner
        new_ctx._table = filtered
        new_ctx._no_ignore = self._no_ignore
        new_ctx._session_id = self._session_id
        new_ctx._refs_cache = None

        new_ctx._pyctx = None
        return new_ctx

    def cat(
        self,
        path: str,
        *,
        mode: Literal["metadata", "fast", "accurate"] = "metadata",
        no_cache: bool = False,
        no_generate: bool = False,
        opts: "CatOpts | None" = None,
    ) -> str:
        """Extract a file's content (directory-scan mode).

        Source of truth for ``mm cat``. The ``metadata`` mode returns the
        locally-extracted (no-LLM) content; ``fast`` and ``accurate`` run
        the full pipeline-driven extraction via
        :func:`mm.cat_utils.extract.extract`.

        Args:
            path: Relative path within the context root (or absolute).
            mode: ``"metadata"`` (default, no LLM), ``"fast"``, or
                ``"accurate"``.
            no_cache: Bypass the extraction cache and recompute.
            no_generate: Skip the LLM ``generate`` step (encode-only).
            opts: Pre-built :class:`~mm.cat_utils.base_utils.CatOpts` to use
                verbatim (dependency injection from the CLI fast path). When
                ``None``, a default is constructed from the other arguments.

        Returns:
            The extracted content as a string.
        """
        self._require_table("cat")
        full_path = Path(path)
        if not full_path.is_absolute() and self.root is not None:
            full_path = self.root / path

        if mode == "metadata" and opts is None:
            from mm.cat_utils.extract_meta import extract_meta
            from mm.utils import file_kind

            kind = file_kind(full_path)
            if kind == "text":
                return full_path.read_text(errors="replace")
            return extract_meta(full_path, kind, no_cache=no_cache)

        from mm.cat_utils.extract import extract as _extract

        if opts is None:
            opts = self._default_cat_opts(mode=mode, no_cache=no_cache, no_generate=no_generate)
        return _extract(full_path, opts).content

    @staticmethod
    def _default_cat_opts(
        *,
        mode: str = "fast",
        no_cache: bool = False,
        no_generate: bool = False,
    ) -> "CatOpts":
        """Build a default :class:`CatOpts` for library-driven extraction."""
        from mm.cat_utils.base_utils import CatOpts

        return CatOpts(
            n=None,
            output_dir=None,
            mode=mode,
            no_cache=no_cache,
            no_generate=no_generate,
            format="rich",
            encode_overrides={},
            generate_overrides={},
            pipelines={},
            verbose=False,
            dry_run=False,
            stream=False,
        )

    @staticmethod
    def _filter_by_name(table: Any, name: str, ignore_case: bool) -> Any:
        """Filter an Arrow table by file name (regex first, substring fallback)."""
        import re as re_mod

        flags = re_mod.IGNORECASE if ignore_case else 0
        names = table.column("name").to_pylist()
        try:
            pattern = re_mod.compile(name, flags)
            mask = [bool(pattern.search(str(n))) for n in names]
        except re_mod.error:
            needle = name.lower()
            mask = [needle in str(n).lower() for n in names]
        return table.filter(mask)

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
        """Encode a file into VLM-ready Message dicts (directory-scan).

        Args:
            path: Relative path within the context root.
            strategy: Registered encoder name (e.g. ``"resize"``).
                If ``None``, defaults to ``resize`` for images,
                ``mosaic`` for video, ``rasterize`` for documents,
                and ``base64`` for audio.
            **kwargs: Forwarded to ``encoder.encode()``.

        Returns:
            List of OpenAI-compatible Message dicts.
        """
        self._require_table("encode")
        from mm.encoders import get as get_encoder
        from mm.refs_messages import OPENAI_DEFAULT_ENCODERS
        from mm.utils import file_kind

        assert self.root is not None
        full_path = self.root / path
        if not full_path.exists():
            raise FileNotFoundError(f"{path} not found in {self.root}")

        kind = file_kind(full_path.name)
        if strategy is None:
            strategy = OPENAI_DEFAULT_ENCODERS.get(kind, "resize")

        strat = get_encoder(strategy, kind)
        return list(strat.encode(full_path, **kwargs))

    def grep(
        self,
        pattern: str,
        *,
        kind: str | None = None,
        ext: str | None = None,
        ignore_case: bool = False,
        context_lines: int = 0,
        count: bool = False,
        semantic: bool = False,
        pre_index: bool = False,
        files: "list[FileEntry] | None" = None,
        regex: "re.Pattern[str] | None" = None,
        stdin_paths: list[str] | None = None,
        quiet: bool = True,
    ) -> "GrepResult":
        """Search file contents (text, document, FTS, and semantic).

        Source of truth for ``mm grep``. Scans text/document files line by
        line and merges full-text and (optionally) semantic chunk hits.

        Args:
            pattern: Regular expression source.
            kind: Optional kind filter (single or comma-separated).
            ext: Optional extension filter.
            ignore_case: Force case-insensitive matching (otherwise
                smart-case applies).
            context_lines: Lines of context around each match (``grep -C``).
            count: Produce per-file counts only (no line matches).
            semantic: Also run a semantic (vector) search over chunks.
            pre_index: Index unindexed files before semantic search.
            files: Pre-collected files to scan (dependency injection from the
                CLI, which dedupes directory + piped paths). When ``None``,
                this context's files are used, filtered by ``kind``/``ext``.
            regex: Pre-compiled pattern (DI from the CLI fast path).
            stdin_paths: Raw piped paths forwarded to semantic search.
            quiet: Suppress semantic-search progress messages.

        Returns:
            A :class:`~mm.results.GrepResult`.
        """
        self._require_table("grep")
        assert self.root is not None
        from mm.search import search_content

        if files is None:
            target = self
            if kind:
                target = target.filter(kind=kind)
            if ext:
                target = target.filter(ext=ext)
            files = [f for f in target.files if not f.path.startswith(".")]

        return search_content(
            pattern,
            files=files,
            root=self.root,
            regex=regex,
            ignore_case=ignore_case,
            context_lines=context_lines,
            count=count,
            kind=kind,
            ext=ext,
            semantic=semantic,
            pre_index=pre_index,
            no_ignore=self._no_ignore,
            stdin_paths=stdin_paths,
            quiet=quiet,
        )

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

    def wc(self, *, kind: str | None = None) -> "WcStats":
        """Compute file/line/token/size aggregates (directory-scan mode).

        Source of truth for ``mm wc``. Reuses this context's already-built
        Rust scanner so no extra scan is performed.

        Args:
            kind: Optional kind filter (single or comma-separated, e.g.
                ``"image,document"``).

        Returns:
            A :class:`~mm.results.WcStats` with totals and a ``by_kind``
            breakdown.
        """
        self._require_table("wc")
        from mm.stats import compute_wc

        assert self.root is not None
        return compute_wc(self.root, kind=kind, scanner=self._scanner)

    def peek(self, path: str | Path) -> "FileMetadata":
        """Return locally-extracted file metadata for a single file.

        Source of truth for ``mm peek``. Reads dimensions / EXIF / codec /
        duration / mime / hash directly from the file without touching the
        SQLite store. In directory-scan mode a relative ``path`` is resolved
        against the context root; absolute paths are used as-is.

        Args:
            path: File to inspect. Relative paths resolve against
                ``self.root`` when this is a directory-scan context.

        Returns:
            A :class:`~mm.peek.FileMetadata` dataclass with all
            kind-specific fields (unset fields are ``None``).

        Raises:
            FileNotFoundError: If the resolved file does not exist.
        """
        from mm.peek import FileMetadata

        p = Path(path)
        if not p.is_absolute() and self.root is not None:
            p = self.root / p
        if not p.exists():
            raise FileNotFoundError(f"{path} not found")
        return FileMetadata.from_path(p)

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
        """Build-or-return cached ``{path: ref_id}`` (directory-scan mode).

        Ref ids are minted in-memory and cached for the lifetime of this
        context; the library never reads a database. Cross-run/cross-process
        ref stability is the persistence layer's concern — mm's SQLite store,
        for example, preserves a row's ``ref_id`` on re-upsert.
        """
        if self._refs_cache is not None:
            return self._refs_cache
        self._require_session()
        from mm.refs import make_ref_id

        paths = self._table.column("path").to_pylist()
        kinds = self._table.column("kind").to_pylist()
        out: dict[str, str] = {p: make_ref_id(k or "other") for p, k in zip(paths, kinds)}
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

        For role-aware contexts, returns ``{ref_id: <session>/<ref>}`` for
        every stored item.
        """
        if self._pyctx is not None:
            return {r: f"{self._session_id}/{r}" for r in self._pyctx.ref_ids()}
        if self._session_id is None:
            return {}
        local = self._materialize_refs()
        return {p: f"{self._session_id}/{r}" for p, r in local.items()}

    # ── Internals ────────────────────────────────────────────────────

    def _collect_metadata_contents(self) -> dict[str, str]:
        """Extract ``cat``-like content for every role-aware item - mode=metadata"""
        from mm.cat_utils.extract_meta import extract_meta
        from mm.utils import file_kind

        out: dict[str, str] = {}
        for item in self._pyctx.items():
            ref_id = item["ref_id"]
            src_kind = item["source_kind"]
            src = item["source_value"]
            if src_kind == "in_memory" and item["kind"] == "text":
                out[ref_id] = item.get("desc") or ""
                continue
            if src_kind == "path":
                p = Path(src)
                if not p.exists():
                    continue
                kind = file_kind(p)
                try:
                    out[ref_id] = extract_meta(p, kind)
                except Exception as exc:  # noqa: BLE001
                    out[ref_id] = f"[extract failed: {exc}]"
            # in-memory / url items fall through to the metadata fallback
            # handled by the Rust-side to_md_with_contents.
        return out

    def _collect_pipeline_contents(self, mode: str) -> dict[str, str]:
        """Extract pipeline-driven (fast/accurate) content for every item."""
        from mm.cat_utils.extract import extract

        opts = self._default_cat_opts(mode=mode)
        out: dict[str, str] = {}
        for item in self._pyctx.items():
            ref_id = item["ref_id"]
            if item["source_kind"] == "in_memory" and item["kind"] == "text":
                out[ref_id] = item.get("desc") or ""
                continue
            if item["source_kind"] == "path":
                p = Path(item["source_value"])
                if not p.exists():
                    continue
                try:
                    out[ref_id] = extract(p, opts).content
                except Exception as exc:  # noqa: BLE001
                    out[ref_id] = f"[extract failed: {exc}]"
        return out

    def _require_pyctx(self, method: str) -> None:
        if self._pyctx is None:
            raise RuntimeError(
                f"Context.{method}() requires an incremental role-aware context. "
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

    def render_html(
        self,
        *,
        max_image_width: int = 320,
        title: str | None = None,
        encoders: dict[str, str] | None = None,
        encoder_kwargs: dict[str, dict[str, Any]] | None = None,
    ) -> str:
        """Render the context as rich, self-contained HTML.

        Each item is rendered with its native media view (image, video
        player, audio player, document pages), user-supplied metadata
        dict, and a collapsible section showing the encoded VLM
        representation. Suitable for ``IPython.display.HTML()`` or
        direct embedding.

        Args:
            max_image_width: Maximum rendered image width in pixels.
            title: Optional title bar text. Defaults to an auto-generated
                summary.
            encoders: Per-kind encoder overrides, e.g.
                ``{"image": "tile", "video": "mosaic"}``.
            encoder_kwargs: Per-kind kwargs forwarded to the encoder's
                ``encode()`` method.

        Returns:
            Self-contained HTML string.

        Raises:
            RuntimeError: If called on a directory-scan Context.
        """
        self._require_pyctx("render_html")
        from mm.notebook import render_context

        return render_context(
            self,
            max_image_width=max_image_width,
            title=title,
            encoders=encoders,
            encoder_kwargs=encoder_kwargs,
        )

    def __enter__(self) -> "Context":
        return self

    def __exit__(self, *_: Any) -> None:
        pass

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


def _validate_role(role: str) -> _RoleLiteral:
    """Validate and narrow a chat role string."""
    if role not in ("system", "developer", "user"):
        raise ValueError(f"role must be 'system', 'developer', or 'user', got {role!r}")
    return cast(_RoleLiteral, role)


def _classify_add_obj(
    obj: Any,
) -> tuple[str, str, str, int | None, str | None, Any]:
    """Inspect ``obj`` and return ``(kind, source_kind, source_value, byte_len, desc, py_obj)``.

    Only ``str``, ``pathlib.Path``, and ``PIL.Image.Image`` are accepted.
    The tuple feeds directly into the Rust ``PyContext.add`` signature.
    """
    from PIL import Image as _PILImage

    # PIL.Image
    if _PILImage is not None and isinstance(obj, _PILImage.Image):
        w, h = obj.size
        mode = obj.mode
        desc = f"PIL.Image({mode}, {w}×{h})"
        byte_len = _estimate_pil_bytes(obj, mode, w, h)
        return ("image", "in_memory", "image/pil", byte_len, desc, obj)

    # free-form text
    if isinstance(obj, str):
        byte_len = len(obj.encode("utf-8"))
        return ("text", "in_memory", "text/plain", byte_len, obj, obj)

    # pathlib.Path
    if isinstance(obj, Path):
        if not obj.exists():
            raise FileNotFoundError(f"add({obj!r}): file does not exist")
        return _classify_path(obj)

    raise TypeError(
        f"add() does not accept {type(obj).__name__}. Supported types: "
        "str, pathlib.Path, PIL.Image.Image."
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
