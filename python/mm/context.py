"""Context -- the main Python API for mm."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mm.store import MmDatabase


class FileEntry:
    """Lightweight wrapper for a single file's metadata.

    When the entry was produced by a :class:`Context` with a ``session_id``,
    :attr:`ref_id` is the deterministic per-session reference id and
    :attr:`global_ref` is the canonical ``<session_id>/<ref_id>`` string.
    """

    def __init__(
        self,
        row: dict[str, Any],
        *,
        session_id: str | None = None,
        root: Path | None = None,
    ):
        self._data = row
        self._session_id = session_id
        self._root = root

    @property
    def kind(self) -> str:
        return str(self._data["kind"])

    @property
    def path(self) -> str:
        return str(self._data["path"])

    @property
    def uri(self) -> str:
        """Absolute uri for this entry. Falls back to the relative path."""
        if self._root is not None:
            return f"{self._root}/{self.path}"
        return str(self._data.get("uri") or self.path)

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def ref_id(self) -> str | None:
        """Per-session ref id, or ``None`` if this entry has no session."""
        if self._session_id is None:
            return None
        from mm.refs import make_ref_id

        return make_ref_id(self.kind, seed=f"{self._session_id}:{self.uri}")

    @property
    def global_ref(self) -> str | None:
        """Canonical ``<session_id>/<ref_id>`` handle, or ``None``."""
        ref = self.ref_id
        return f"{self._session_id}/{ref}" if ref else None

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(f"FileEntry has no attribute '{name}'") from None

    def __repr__(self) -> str:
        ref = self.global_ref
        ref_part = f", ref='{ref}'" if ref else ""
        return (
            f"FileEntry(path='{self._data.get('path', '')}', "
            f"kind='{self._data.get('kind', '')}'{ref_part})"
        )


class Context:
    """Multimodal context for a directory.

    Scanning (L0) is performed on construction. L1 extraction is on-demand.

    Args:
        root: Directory to scan.
        n_threads: Optional thread count for the Rust scanner.
        no_ignore: If True, ignore ``.gitignore`` exclusions.
        session_id: Optional external session UUID. When supplied, files
            saved through :meth:`save` are tagged with this session and
            assigned a deterministic ``ref_id`` (kind-prefixed, 6-char
            base-36) derived from ``(session_id, uri)``. Multiple
            ``Context`` instances may share the same ``session_id`` to
            collect files from multiple roots under one logical session.
        llm_base_url, llm_api_key: Optional LLM overrides.

    Examples:
        >>> ctx = Context("~/data", session_id="my-session-uuid")
        >>> ctx.save()
        >>> ref = ctx.global_ref("photo.jpg")          # 'my-session-uuid/img_a1b2c3'
        >>> Context.resolve(ref)                        # files row dict
    """

    def __init__(
        self,
        root: str | Path,
        *,
        n_threads: int | None = None,
        no_ignore: bool = False,
        session_id: str | None = None,
        llm_base_url: str | None = None,
        llm_api_key: str | None = None,
    ):
        self.root = Path(root).resolve()
        self._no_ignore = no_ignore
        self._llm_base_url = llm_base_url
        self._llm_api_key = llm_api_key
        self._session_id = session_id

        from mm._mm import Scanner

        self._scanner = Scanner(str(self.root), n_threads, no_ignore=no_ignore)
        self._scanner.scan()

        self._table = self._scanner.to_arrow()
        self._db: MmDatabase | None = None

    @classmethod
    def new_session(
        cls,
        root: str | Path,
        **kwargs: Any,
    ) -> Context:
        """Create a Context with a freshly minted UUIDv4 session id.

        Convenience for callers who want global refs but don't already have
        a session id from an upstream system.
        """
        from mm.refs import new_session_id

        return cls(root, session_id=new_session_id(), **kwargs)

    @property
    def session_id(self) -> str | None:
        """External session id attached to this context, if any."""
        return self._session_id

    @property
    def db(self) -> MmDatabase:
        """Lazy-initialized global database connection."""
        if self._db is None:
            from mm.store import MmDatabase

            self._db = MmDatabase()
        return self._db

    @property
    def num_files(self) -> int:
        return int(self._table.num_rows)

    @property
    def files(self) -> list[FileEntry]:
        """Iterate over files as FileEntry objects."""
        rows = self._table.to_pydict()
        result = []
        for i in range(self._table.num_rows):
            row = {col: rows[col][i] for col in rows}
            result.append(FileEntry(row, session_id=self._session_id, root=self.root))
        return result

    # --- DataFrame export ---

    def to_polars(self):
        """Convert to Polars DataFrame (zero-copy via Arrow)."""
        from mm.df import arrow_to_polars

        return arrow_to_polars(self._table)

    def to_pandas(self):
        """Convert to Pandas DataFrame (zero-copy for numeric columns)."""
        from mm.df import arrow_to_pandas

        return arrow_to_pandas(self._table)

    def to_arrow(self):
        """Return the underlying PyArrow Table."""
        return self._table

    # --- SQL ---

    def sql(self, query: str):
        """Run a SQL query against the file index.

        The table is available as 'files' in the query.
        """
        from mm.query import query_arrow_table

        return query_arrow_table(self._table, query)

    # --- Filtering ---

    def filter(
        self,
        *,
        kind: str | None = None,
        ext: str | list[str] | None = None,
        min_size: str | int | None = None,
        max_size: str | int | None = None,
        modified_after: str | None = None,
    ) -> Context:
        """Return a new Context with filtered files. Chainable."""
        conditions: list[str] = []

        if kind:
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
        return new_ctx

    # --- Content access ---

    def cat(self, path: str, *, no_cache: bool = False) -> str:
        """Read the fast-mode content of a file.

        Mirrors ``mm cat <file>`` (fast mode) — metadata/text extraction
        without an LLM call. For accurate-mode LLM descriptions, use
        the ``mm cat -m accurate`` CLI or ``mm.llm.LlmBackend`` directly.
        """
        full_path = self.root / path
        from mm.commands.cat import _run_l1
        from mm.utils import file_kind

        kind = file_kind(full_path)
        if kind == "text":
            return full_path.read_text(errors="replace")
        return _run_l1(full_path, kind, no_cache=no_cache)

    def head(self, path: str, *, n: int = 10) -> str:
        """First N lines/pages of a file."""
        content = self.cat(path)
        lines = content.splitlines()
        return "\n".join(lines[:n])

    def tail(self, path: str, *, n: int = 10) -> str:
        """Last N lines/pages of a file."""
        content = self.cat(path)
        lines = content.splitlines()
        return "\n".join(lines[-n:])

    def encode(
        self,
        path: str,
        *,
        strategy: str | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Encode a file into VLM-ready Message dicts.

        Args:
            path: Relative path within the context root.
            strategy: Registered encoder name (e.g. ``"image-resize"``).
                If ``None``, defaults to ``image-resize`` for images,
                ``video-frame-sample`` for video, ``document-rasterize``
                for documents.
            **kwargs: Forwarded to ``encoder.encode()``.

        Returns:
            List of OpenAI-compatible Message dicts.
        """
        from mm.constants import file_kind
        from mm.encoders import get

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

        strat = get(strategy)
        return list(strat.encode(full_path, **kwargs))

    def grep(self, pattern: str, *, kind: str | None = None) -> list[dict[str, Any]]:
        """Search for a pattern across files."""
        import re

        matches: list[dict[str, Any]] = []
        target = self.filter(kind=kind) if kind else self

        for f in target.files:
            try:
                content = self.cat(f.path)
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pattern, line):
                        matches.append(
                            {
                                "path": f.path,
                                "line_number": i,
                                "line": line,
                            }
                        )
            except Exception:
                continue

        return matches

    # --- Display ---

    def show(self, *, limit: int | None = 50, columns: list[str] | None = None) -> None:
        """Display the index as a Rich table."""
        from mm.display import arrow_table_to_rich, output_console

        rich_table = arrow_table_to_rich(self._table, columns=columns, limit=limit)
        output_console.print(rich_table)

    def info(self) -> None:
        """Display summary statistics as a Rich panel."""
        import collections

        from mm.display import format_size, info_panel, output_console

        total_size = sum(r.as_py() for r in self._table.column("size"))
        kinds = collections.Counter(r.as_py() for r in self._table.column("kind"))
        exts = collections.Counter(r.as_py() for r in self._table.column("ext"))
        top_exts = exts.most_common(5)

        stats = {
            "Files": self.num_files,
            "Total Size": format_size(total_size),
            "Root": str(self.root),
        }
        for k, count in sorted(kinds.items(), key=lambda x: -x[1]):
            stats[k.capitalize()] = count

        ext_str = ", ".join(f"{e} ({c})" for e, c in top_exts)
        stats["Top Extensions"] = ext_str

        panel = info_panel(stats, title=self.root.name)
        output_console.print(panel)

    # --- Refs (global addressing) ---

    def _uri_for(self, path: str) -> str:
        """Build the canonical absolute uri for a relative ``path``."""
        return f"{self.root}/{path.lstrip('/')}"

    def _kind_of(self, path: str) -> str:
        """Best-effort kind lookup: in-memory table first, fall back to extension."""
        from mm.utils import file_kind_with_code

        if "path" in self._table.column_names and "kind" in self._table.column_names:
            paths = self._table.column("path").to_pylist()
            kinds = self._table.column("kind").to_pylist()
            for n, k in zip(paths, kinds):
                if n == path:
                    return str(k)
        return file_kind_with_code(Path(path))

    def ref_for(self, path: str) -> str:
        """Return the ref id for ``path`` within this context.

        Requires :attr:`session_id` to be set. The id is deterministic given
        ``(session_id, uri)``, so calling :meth:`save` is not required to
        compute it.

        Raises:
            ValueError: If the context has no ``session_id``.
        """
        if self._session_id is None:
            raise ValueError(
                "Context has no session_id; pass session_id=... to Context() "
                "or use Context.new_session() to enable refs."
            )
        from mm.refs import make_ref_id

        return make_ref_id(self._kind_of(path), seed=f"{self._session_id}:{self._uri_for(path)}")

    def global_ref(self, path: str) -> str:
        """Return ``<session_id>/<ref_id>`` for ``path``.

        Raises:
            ValueError: If the context has no ``session_id``.
        """
        return f"{self._session_id}/{self.ref_for(path)}"

    @property
    def refs(self) -> dict[str, str]:
        """Mapping of ``path -> global_ref`` for every file in the context.

        Returns an empty dict when no ``session_id`` is set.
        """
        if self._session_id is None:
            return {}
        from mm.refs import make_ref_id

        out: dict[str, str] = {}
        paths = self._table.column("path").to_pylist()
        kinds = self._table.column("kind").to_pylist()
        sess = self._session_id
        for p, k in zip(paths, kinds):
            uri = self._uri_for(p)
            out[p] = f"{sess}/{make_ref_id(k or 'other', seed=f'{sess}:{uri}')}"
        return out

    @staticmethod
    def resolve(global_ref: str, *, db: MmDatabase | None = None) -> dict[str, Any] | None:
        """Look up a file row by its ``<session_id>/<ref_id>`` handle.

        Args:
            global_ref: Canonical handle string.
            db: Optional database instance (defaults to the global mm DB).

        Returns:
            The ``files`` row dict, or ``None`` if no such ref exists.

        Raises:
            ValueError: If ``global_ref`` is malformed.
        """
        from mm.refs import GlobalRef

        ref = GlobalRef.parse(global_ref)
        if db is None:
            from mm.store import MmDatabase

            db = MmDatabase()
        return db.get_file_by_ref(ref.session_id, ref.ref_id)

    # --- Persistence ---

    def save(self) -> None:
        """Write the index to the database.

        When :attr:`session_id` is set, every row is tagged with the
        session and gets a deterministic ``ref_id``. Calling ``save``
        again with the same session is a no-op for refs (idempotent).
        """
        self.db.upsert_files(self._table, self.root, session_id=self._session_id)

    def __repr__(self) -> str:
        sess = f", session='{self._session_id}'" if self._session_id else ""
        return f"Context(root='{self.root}', files={self.num_files}{sess})"

    def __len__(self) -> int:
        return self.num_files


def _parse_size(size_str: str) -> int:
    """Parse human-readable size string to bytes (e.g., '1MB', '500KB')."""
    size_str = size_str.strip().upper()
    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    for suffix, mult in sorted(multipliers.items(), key=lambda x: -len(x[0])):
        if size_str.endswith(suffix):
            num = size_str[: -len(suffix)].strip()
            return int(float(num) * mult)
    return int(size_str)
