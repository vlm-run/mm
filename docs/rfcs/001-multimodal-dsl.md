# RFC 001: mm as a Polars Expression Library

**Status**: Draft v2
**Author**: Claude
**Date**: 2026-04-12

## The Core Insight

> `mm` is really just **a Rust scan function that produces a Polars DataFrame, plus a set of Polars expressions that transform file paths into content, descriptions, embeddings, and structured data.**

Everything else — `Context`, `cat`, `describe`, `embed`, `generate`, `search`, `grep`, `wc`, `find`, `sql` — is a thin wrapper around Polars primitives. There is no `Context.describe()` method because **that's not DataFrame semantics**. There is only `pl.col("path").mm.cat(level=2)` inside a `with_columns`.

This RFC reframes mm's Python API around that insight.

---

## The Primitive: `mm.scan(root) -> pl.DataFrame`

The Rust core already produces an Arrow table. Convert it directly to Polars and return it — no `Context` class, no `FileEntry` wrapper.

```python
import polars as pl
import mm  # registers expression + dataframe namespaces on import

df = mm.scan("~/data")
# pl.DataFrame with columns: path, name, stem, ext, size, modified, created,
#                            mime, kind, is_binary, depth, parent, width, height
```

That's it. `mm.scan()` is a one-shot function. The returned DataFrame *is* the context. Everything else is standard Polars.

```python
# Lazy variant for streaming huge directories
lf = mm.scan_lazy("~/data")  # pl.LazyFrame
```

---

## All Operations as Column Expressions

Every mm operation becomes a method on the `col.mm` namespace, registered via `pl.api.register_expr_namespace("mm")`. Under the hood each one uses `map_batches` with a ThreadPool for I/O-bound work and Rust for CPU-bound work.

```python
@pl.api.register_expr_namespace("mm")
class MmExpr:
    def __init__(self, expr: pl.Expr):
        self._expr = expr

    def hash(self) -> pl.Expr:
        """xxh3 content hash (Rust fast path, Rayon-parallel)."""
        return self._expr.map_batches(_batch_hash, return_dtype=pl.Utf8)

    def cat(self, *, level: int = 1, mode: str | None = None,
            concurrency: int = 8) -> pl.Expr:
        """Extract content at L0/L1/L2.

        - level=0: raw bytes as string
        - level=1: extracted content (PDF text, image metadata, etc.)
        - level=2: VLM description (auto-caches by content hash)
        """
        return self._expr.map_batches(
            lambda s: _batch_cat(s, level=level, mode=mode, concurrency=concurrency),
            return_dtype=pl.Utf8,
        )

    def encode(self, *, strategy: str | None = None, **kwargs) -> pl.Expr:
        """Encode for VLM consumption. Returns List(Struct) of messages."""
        ...

    def embed(self, *, concurrency: int = 4) -> pl.Expr:
        """Generate embedding vectors. Returns List(Float64)."""
        return self._expr.map_batches(
            lambda s: _batch_embed(s, concurrency=concurrency),
            return_dtype=pl.List(pl.Float64),
        )

    def extract(self, prompt: str, schema: dict[str, pl.DataType],
                *, mode: str = "fast", concurrency: int = 8) -> pl.Expr:
        """Structured VLM extraction. Returns Struct with `schema` fields.

        Use with .unnest() to spread fields into named columns.
        """
        return self._expr.map_batches(
            lambda s: _batch_extract(s, prompt, schema, mode, concurrency),
            return_dtype=pl.Struct(schema),
        )

    def tokens(self) -> pl.Expr:
        """Estimated token count (Rust)."""
        return self._expr.map_batches(_batch_tokens, return_dtype=pl.UInt64)

    def kind(self) -> pl.Expr:
        """File kind classification."""
        return self._expr.map_batches(_batch_kind, return_dtype=pl.Utf8)

    def mime(self) -> pl.Expr:
        return self._expr.map_batches(_batch_mime, return_dtype=pl.Utf8)
```

### The full rewrite example

```python
import polars as pl
import mm

# Scan + filter + L1 + L2 + embed + sort + save, in one Polars chain:
result = (
    mm.scan("~/products")
    .filter(pl.col("kind") == "image")
    .filter(pl.col("size") > 100_000)
    .with_columns(
        pl.col("path").mm.hash().alias("content_hash"),
        pl.col("path").mm.cat(level=1).alias("l1_content"),
        pl.col("path").mm.tokens().alias("tok_est"),
    )
    .with_columns(
        pl.col("path").mm.cat(level=2, mode="fast").alias("description"),
    )
    .with_columns(
        pl.col("description").mm.embed().alias("embedding"),
    )
    .sort("tok_est", descending=True)
)
result.mm.save()           # persist to SQLite (via dataframe namespace)
result.write_parquet("out.parquet")  # or export to parquet
```

No `Context`, no `.describe()`, no `.generate()`, no custom chain methods. Just Polars.

---

## Structured Extraction via `Struct + unnest`

This is the elegant replacement for `Context.generate(schema=...)`. The VLM returns JSON, the UDF parses it into a Polars `Struct`, then `unnest` spreads it into columns. That's pure DataFrame semantics.

```python
schema = {
    "title": pl.Utf8,
    "objects": pl.List(pl.Utf8),
    "scene_type": pl.Utf8,
    "quality_score": pl.Float64,
}

df = (
    mm.scan("~/products")
    .filter(pl.col("kind") == "image")
    .with_columns(
        pl.col("path").mm.extract(
            prompt="Return JSON: {title, objects: [str], scene_type, quality_score: float}",
            schema=schema,
            mode="fast",
        ).alias("meta")
    )
    .unnest("meta")   # ← spreads meta.title → column "title", etc.
)
# df columns: path, name, size, kind, ..., title, objects, scene_type, quality_score

# Now it's just a regular DataFrame — filter, aggregate, join as usual:
hi_quality = df.filter(pl.col("quality_score") > 0.8)
by_scene = df.group_by("scene_type").agg(pl.len(), pl.col("quality_score").mean())
```

This is how Daft does it, and it's how mm should work.

---

## Search as a DataFrame Namespace

Vector search is a DataFrame-level operation (it joins across all rows), so it belongs in a DataFrame namespace, not an expression namespace. Register via `pl.api.register_dataframe_namespace("mm")`.

```python
@pl.api.register_dataframe_namespace("mm")
class MmDF:
    def __init__(self, df: pl.DataFrame):
        self._df = df

    def save(self, *, root: str | None = None) -> None:
        """Persist L0/L1/L2/embeddings to the global SQLite store."""
        from mm.store import MmDatabase
        MmDatabase().ingest(self._df, root=root)

    def search(self, query: str | bytes | Path, *,
               k: int = 10, column: str = "embedding") -> pl.DataFrame:
        """Cross-modal similarity search. `query` is text, image path, or bytes."""
        query_vec = _embed_query(query)
        return (
            self._df
            .with_columns(
                pl.col(column).mm.similarity(query_vec).alias("score")
            )
            .sort("score", descending=True)
            .head(k)
        )

    def show(self, *, limit: int = 50) -> None:
        """Rich table display."""
        ...

    def info(self) -> None:
        """Rich summary panel."""
        ...
```

Usage:

```python
# Embed everything, then search across the DataFrame
df = (
    mm.scan("~/photos")
    .filter(pl.col("kind") == "image")
    .with_columns(pl.col("path").mm.embed().alias("embedding"))
)

hits = df.mm.search("red sports car on mountain road", k=10)
hits = df.mm.search(Path("ref.jpg"), k=5)
```

`pl.col(...).mm.similarity(vec)` is an expression that computes cosine similarity row-by-row. Since embeddings are `List(Float64)`, this is a simple dot-product UDF (or a native Rust expression once we write one).

---

## Rewriting Every mm Command in Polars

Here is how each existing CLI command collapses to a Polars chain. The CLI becomes a very thin argparse shell over these chains.

### `mm find`

```python
def find_cmd(root, *, kind=None, ext=None, min_size=None, max_size=None,
             name=None, sort=None, limit=None, format="rich"):
    df = mm.scan(root)
    if kind:     df = df.filter(pl.col("kind") == kind)
    if ext:      df = df.filter(pl.col("ext").is_in(ext))
    if min_size: df = df.filter(pl.col("size") >= _parse_size(min_size))
    if max_size: df = df.filter(pl.col("size") <= _parse_size(max_size))
    if name:     df = df.filter(pl.col("name").str.contains(name))
    if sort:     df = df.sort(sort)
    if limit:    df = df.head(limit)
    _write(df, format)
```

### `mm cat`

```python
def cat_cmd(path, *, level=1, mode=None):
    df = (
        mm.scan(Path(path).parent)
        .filter(pl.col("name") == Path(path).name)
        .with_columns(pl.col("path").mm.cat(level=level, mode=mode).alias("content"))
    )
    print(df["content"][0])
```

### `mm grep`

```python
def grep_cmd(pattern, root, *, kind=None, context=0):
    df = (
        mm.scan(root)
        .filter(pl.col("kind") == kind) if kind else mm.scan(root)
    )
    return (
        df
        .with_columns(pl.col("path").mm.cat(level=1).alias("content"))
        .filter(pl.col("content").str.contains(pattern))
        .select("path", "content")
    )
```

No custom grep implementation needed. `str.contains` is a Polars native.

### `mm wc`

```python
def wc_cmd(root, *, by_kind=False):
    df = mm.scan(root)
    if by_kind:
        return df.group_by("kind").agg(
            pl.len().alias("files"),
            pl.col("size").sum().alias("bytes"),
            pl.col("path").mm.tokens().sum().alias("tokens"),
        )
    return df.select(
        pl.len().alias("files"),
        pl.col("size").sum().alias("bytes"),
        pl.col("path").mm.tokens().sum().alias("tokens"),
    )
```

`wc` is one `group_by().agg()` away. The "estimated tokens" column comes from `col.mm.tokens()` which is a Rust fast-path.

### `mm sql`

```python
def sql_cmd(query, root):
    df = mm.scan(root)
    return pl.SQLContext(files=df).execute(query).collect()
```

Polars has **native SQL support** via `pl.SQLContext`. Drop `python/mm/query.py` entirely (the in-memory SQLite hack). SQL now composes with expressions: you can write SQL that *uses* `mm.cat()` via registered Polars UDFs.

### `mm cat video.mp4 -l 2` (the hot path)

```python
# Equivalent Polars chain:
(
    mm.scan(Path("video.mp4").parent)
    .filter(pl.col("name") == "video.mp4")
    .with_columns(pl.col("path").mm.cat(level=2, mode="fast").alias("desc"))
    ["desc"][0]
)
```

The L2 cache is still keyed by content hash — `mm.cat(level=2)` internally calls `content_hash → lookup → hit/miss → LLM`. The caching is invisible to the user but still O(1).

---

## What Goes Away

| Deleted | Replaced By |
|---|---|
| `python/mm/context.py` (360 LOC) | `mm.scan()` + Polars namespaces |
| `python/mm/query.py` (64 LOC) | `pl.SQLContext` |
| `python/mm/df.py` (23 LOC) | `mm.scan` returns `pl.DataFrame` directly |
| `FileEntry` class | Polars `row(i, named=True)` |
| `Context.filter()` | `pl.DataFrame.filter()` |
| `Context.map()` | `pl.DataFrame.with_columns(pl.col.map_batches(...))` |
| `Context.describe()` | `.with_columns(pl.col("path").mm.cat(level=2))` |
| `Context.embed()` | `.with_columns(pl.col("path").mm.embed())` |
| `Context.generate()` | `.with_columns(pl.col("path").mm.extract(...)).unnest(...)` |
| `Context.grep()` | `.filter(pl.col("content").str.contains(...))` |
| `Context.show()` / `.info()` | `df.mm.show()` / `df.mm.info()` |
| `Context.save()` | `df.mm.save()` |

Net deletion: ~500+ LOC of Python, replaced by a much smaller namespace module and two registration calls.

---

## Concurrency Model

The tricky part is making `map_batches` parallel for I/O-bound operations (LLM calls) without breaking Polars' semantics. The rule:

- **CPU-bound ops** (hash, tokens, kind, mime, L1 extraction): implemented in Rust, parallelized via Rayon inside `map_batches`. Zero Python overhead.
- **I/O-bound ops** (L2 cat, embed, extract): use a ThreadPool inside `map_batches`. The UDF receives a Series, spawns N workers, and returns a Series of the same length.

```python
def _batch_cat_l2(paths: pl.Series, *, mode: str, concurrency: int) -> pl.Series:
    from concurrent.futures import ThreadPoolExecutor
    from mm.store import MmDatabase
    db = MmDatabase()

    def _one(p: str) -> str:
        # Hash → cache lookup → LLM → cache write
        h = _content_hash(p)
        cached = db.get_l2_by_hash(h, mode=mode)
        if cached is not None:
            return cached
        parts = _encode(p, mode=mode)
        result = _llm_generate(parts, mode=mode)
        db.put_l2(p, h, result, mode=mode)
        return result

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        return pl.Series(list(pool.map(_one, paths.to_list())), dtype=pl.Utf8)
```

Polars sees this as a single batch operation — query optimization still works across other expressions. Cache hits skip the LLM entirely, so re-running the chain is idempotent and fast.

### Why not `pl.col().map_elements()` row-at-a-time?

`map_elements` runs the function per row with GIL overhead. `map_batches` gets the whole Series at once, so we control batching, concurrency, and pooling ourselves. 100 files through `map_elements` = 100 GIL trips + 100 sequential LLM calls. Through `map_batches` = 1 GIL trip + N concurrent LLM calls.

---

## Lazy Evaluation

Because every operation is a Polars expression, the whole pipeline becomes lazy via `mm.scan_lazy`:

```python
lf = (
    mm.scan_lazy("~/big-dataset")
    .filter(pl.col("kind") == "image")
    .filter(pl.col("size") > 100_000)
    .with_columns(pl.col("path").mm.cat(level=2).alias("desc"))
    .with_columns(pl.col("desc").mm.embed().alias("emb"))
)

# Nothing runs until .collect() or .sink_parquet()
lf.sink_parquet("index.parquet")  # streams results to disk
```

`map_batches` works in LazyFrames. Polars can push the size filter through the scan, so we never run L2 on files filtered out upstream. That's free optimization we get for zero design effort.

---

## `mm pipe` — the CLI shape

Unix-composable batch processing becomes a single command that applies a Polars expression chain to stdin:

```bash
# Describe every image
mm find ~/data --kind image \
  | mm pipe 'with_columns(col.path.mm.cat(level=2).alias("desc"))'

# Structured extraction
mm find ~/data --kind image \
  | mm pipe 'with_columns(col.path.mm.extract("Return JSON: {title, mood}",
               {"title": Utf8, "mood": Utf8}).alias("meta")).unnest("meta")' \
  --format csv > catalog.csv

# Embed + export
mm find ~/data --kind document \
  | mm pipe 'with_columns(col.path.mm.embed().alias("emb"))' \
  --format parquet > index.parquet
```

The argument to `mm pipe` is a restricted Polars expression string (parsed and validated, not `eval`'d). This is powerful enough to replace `mm describe`, `mm embed`, `mm extract`, etc., without adding N new CLI commands.

For convenience, common chains get aliases:

```bash
mm pipe describe     # = mm pipe 'with_columns(col.path.mm.cat(level=2).alias("desc"))'
mm pipe embed        # = mm pipe 'with_columns(col.path.mm.embed().alias("embedding"))'
mm pipe extract ...  # = mm pipe 'with_columns(col.path.mm.extract(...)).unnest(...)'
```

---

## Migration Path

### Stage 1 — Add without breaking

1. Add `mm.scan()` that returns a `pl.DataFrame` (wraps the existing Rust `Scanner`).
2. Register `col.mm.*` and `df.mm.*` namespaces on `import mm`.
3. Implement the expression namespace (`cat`, `hash`, `tokens`, `kind`, `mime`, `embed`, `extract`, `encode`).
4. Implement the DataFrame namespace (`save`, `search`, `show`, `info`).
5. Keep `Context` as a compatibility shim that internally calls the new API.

### Stage 2 — Delete

1. Mark `Context` deprecated, re-route its methods to the new API.
2. Delete `query.py`, `df.py`, most of `context.py`.
3. Rewrite CLI commands as thin wrappers over Polars chains (`find_cmd`, `cat_cmd`, `grep_cmd`, `wc_cmd`, `sql_cmd` ~5 lines each).
4. Drop `FileEntry`.

### Stage 3 — Polish

1. Move the hot L1 paths (hash, tokens, kind) to Rust-native Polars expressions via `pyo3-polars` for zero-copy, no-GIL batch execution. These currently use `map_batches` with a Python loop around a Rust call; a native plugin eliminates the Python trip entirely.
2. Add `mm.scan_lazy()` for streaming over huge trees.
3. Ship `mm pipe` with restricted expression parsing.

---

## Why This Is Actually Elegant

1. **Zero new concepts.** If you know Polars, you know mm. If you know mm, you know Polars. There is no separate mm API to learn.
2. **Composability is free.** Filter → extract → embed → sort → group_by all compose because they're all Polars operations.
3. **Lazy evaluation is free.** `mm.scan_lazy()` works for the full pipeline because everything is an expression.
4. **SQL is free.** `pl.SQLContext` already executes SQL over DataFrames, and mm expressions become UDFs inside SQL.
5. **Parquet/Arrow export is free.** `df.write_parquet()` just works. The L2 + embedding columns round-trip losslessly.
6. **Interop is free.** Anything that consumes Polars (Ibis, DuckDB, pandas, XGBoost, datasets) now consumes mm output.
7. **Tests are trivial.** Every operation is a pure function over a Series. No mocking `Context`, no fixture plumbing — just `assert expected == pl.Series([...]).mm.cat(level=1)`.
8. **Deletes more than it adds.** `~500 LOC out, ~300 LOC in` is the right direction.

---

## API Summary (the whole surface)

```python
# Module level
mm.scan(root) -> pl.DataFrame
mm.scan_lazy(root) -> pl.LazyFrame
mm.embed_text(text) -> list[float]              # used by df.mm.search

# Expression namespace (on any path-typed column)
col.mm.hash() -> pl.Utf8
col.mm.kind() -> pl.Utf8
col.mm.mime() -> pl.Utf8
col.mm.tokens() -> pl.UInt64
col.mm.cat(level, mode, concurrency) -> pl.Utf8
col.mm.encode(strategy, **kwargs) -> pl.List(pl.Struct)
col.mm.embed(concurrency) -> pl.List(pl.Float64)
col.mm.extract(prompt, schema, mode, concurrency) -> pl.Struct
col.mm.similarity(query_vec) -> pl.Float64   # for embedding columns

# DataFrame namespace
df.mm.save(root)
df.mm.search(query, k, column)
df.mm.show(limit)
df.mm.info()
```

That is the *entire* Python API. `Context`, `FileEntry`, `process_image`, `process_video`, `process_document`, `Context.cat/filter/map/describe/embed/generate/grep/sql/show/info/save` all collapse into these ~14 callables.

---

## Open Questions

1. **Should `mm.scan` resolve to absolute paths in the `path` column?** Current Rust scanner returns relative paths. Expressions that call `col.path.mm.cat()` need to know the root. Options: (a) scanner returns absolute paths, (b) `mm.scan` stores root in DataFrame metadata and expressions read it, (c) pass root explicitly as `col.mm.cat(level=2, root=...)`. Proposed: (a) for simplicity.

2. **Native Polars plugin via `pyo3-polars`?** Would eliminate the Python trip for L1 ops (hash, kind, tokens) and give zero-copy batch execution. Significant win for large scans. Candidate for Stage 3.

3. **How to express "fail fast" vs "continue on error" in batch UDFs?** A single bad file currently poisons a Polars chain. Proposed: all batch UDFs accept `errors="null"|"raise"` and default to `"null"` (failed rows become null, pipeline continues).

4. **Rate limiting for LLM calls.** Concurrency is per-`map_batches` call, but an HTTP server may need a global budget. Proposed: module-level `mm.config.llm_concurrency = 8` as a default ceiling, overridden by the `concurrency` kwarg.

5. **Should `extract` support Pydantic models instead of dict schemas?** `col.mm.extract(prompt, MyPydanticModel)` is nicer ergonomically, and we already depend on Pydantic. Dict stays as an escape hatch.

6. **Should `mm pipe`'s expression argument be Polars SQL or Polars expressions?** SQL is more familiar but can't express `unnest`. Expressions are more powerful. Proposed: both — `mm pipe --sql '...'` and `mm pipe --expr '...'`.
