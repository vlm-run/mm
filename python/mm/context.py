"""Context -- the main Python API for mm."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mm.store import MmDatabase


class FileEntry:
    """Lightweight wrapper for a single file's metadata."""

    def __init__(self, row: dict[str, Any]):
        self._data = row

    @property
    def kind(self) -> str:
        return str(self._data["kind"])

    @property
    def path(self) -> str:
        return str(self._data["path"])

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
    """Multi-modal context for a directory.

    Scanning (L0) is performed on construction. L1 extraction is on-demand.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        n_threads: int | None = None,
        llm_base_url: str | None = None,
        llm_api_key: str | None = None,
    ):
        self.root = Path(root).resolve()
        self._llm_base_url = llm_base_url
        self._llm_api_key = llm_api_key

        from mm._mm import Scanner

        self._scanner = Scanner(str(self.root), n_threads)
        self._scanner.scan()

        self._table = self._scanner.to_arrow()  # pa.Table
        self._db: MmDatabase | None = None

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
            result.append(FileEntry(row))
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
        return new_ctx

    # --- Content access ---

    def cat(
        self,
        path: str,
        *,
        level: int = 1,
        mode: str | None = None,
        no_cache: bool = False,
    ) -> str:
        """Read semantic content of a file.

        Level 0: raw content (for text files)
        Level 1: extracted content (text from PDF, image metadata)
        Level 2: LLM-generated description (requires LLM config)

        Args:
            path: Relative path within the context root.
            level: Processing level (0=raw, 1=extracted, 2=semantic).
            mode: Extraction mode for L2: "fast" or "accurate". None uses default L2.
            no_cache: Skip L2 cache lookup and force a fresh LLM call.
        """
        full_path = self.root / path

        if level == 0:
            from mm.commands.cat import _file_kind

            kind = _file_kind(full_path)
            if kind != "text":
                from mm.commands.cat import _run_l1

                return _run_l1(full_path, kind, no_cache=no_cache)
            return full_path.read_text(errors="replace")

        if level >= 2 and mode is not None:
            # Use the CLI's modal extraction pipeline
            from mm.commands.cat import _CatOpts, _extract

            opts = _CatOpts(
                level=level,
                n=None,
                detail=False,
                output_dir=None,
                max_pages=None,
                mosaic_tile="4x4",
                mosaic_image_width=160,
                video_mosaic_count=1,
                video_mosaic_strategy="uniform",
                audio_speed=2.0,
                audio_sample_rate=16000,
                mode=mode,
                no_cache=no_cache,
                format="rich",
            )
            return _extract(full_path, opts)

        if level >= 1:
            result = self._scanner.extract_l1(path)
            parts: list[str] = []
            if result.text_preview:
                parts.append(result.text_preview)
            if result.dimensions:
                parts.append(f"Dimensions: {result.dimensions}")
            if result.line_count is not None:
                parts.append(f"Lines: {result.line_count}")
            if result.language:
                parts.append(f"Language: {result.language}")
            return "\n".join(parts) if parts else full_path.read_text(errors="replace")

        return ""

    def head(self, path: str, *, n: int = 10) -> str:
        """First N lines/pages of a file."""
        content = self.cat(path, level=1)
        lines = content.splitlines()
        return "\n".join(lines[:n])

    def tail(self, path: str, *, n: int = 10) -> str:
        """Last N lines/pages of a file."""
        content = self.cat(path, level=1)
        lines = content.splitlines()
        return "\n".join(lines[-n:])

    def encode(
        self,
        path: str,
        *,
        strategy: str | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Encode a file for VLM consumption using a serde strategy.

        Args:
            path: Relative path within the context root.
            strategy: Strategy name, .py file path, or inline code.
                      If None, defaults to "resize" for images,
                      "frame_sample" for video, "rasterize" for documents.
            **kwargs: Strategy-specific parameters (max_width, fps, etc.)

        Returns:
            List of OpenAI-compatible Message dicts.
        """
        from mm.constants import file_kind
        from mm.serde import resolve_strategy

        full_path = self._root / path
        if not full_path.exists():
            raise FileNotFoundError(f"{path} not found in {self._root}")

        media_type = file_kind(full_path.name)

        if strategy is None:
            strategy = {"image": "resize", "video": "frame_sample",
                        "document": "rasterize"}.get(media_type, "resize")

        strat = resolve_strategy(strategy, media_type)
        return list(strat.encode(full_path, **kwargs))

    def grep(self, pattern: str, *, kind: str | None = None) -> list[dict[str, Any]]:
        """Search for a pattern across files."""
        import re

        matches: list[dict[str, Any]] = []
        target = self.filter(kind=kind) if kind else self

        for f in target.files:
            try:
                content = self.cat(f.path, level=1)
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

    # --- Persistence ---

    def save(self) -> None:
        """Write the index to the database."""
        self.db.upsert_files(self._table, self.root)

    def __repr__(self) -> str:
        return f"Context(root='{self.root}', files={self.num_files})"

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
