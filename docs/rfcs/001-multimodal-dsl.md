# RFC 001: Multimodal DSL Extension

**Status**: Draft
**Author**: Claude
**Date**: 2026-04-12

## Motivation

`mm` today is excellent at single-file operations: scan a directory (L0), extract content from one file (L1), generate a description for one file (L2). But real-world multimodal workflows operate on **collections**: "describe all images in this directory", "embed every PDF and find similar ones", "extract structured metadata from 500 product photos".

The gap is a **DataFrame-native batch processing API** — something that lets you express multimodal pipelines as column transforms on a table of files, with the same ultrafast + devex philosophy mm already has.

### Current pain

```python
ctx = Context("~/data")
images = ctx.filter(kind="image")

# To describe all images today, you must loop:
for f in images.files:
    desc = ctx.cat(f.path, level=2, mode="fast")  # sequential, one LLM call at a time
    print(f.path, desc)
```

No batching, no parallelism, no DataFrame integration for L2 results.

### Inspiration

- **Daft** (getdaft.io): Distributed DataFrame with native multimodal types (Image, Embedding, URL). Expression namespaces like `.image.resize()`, `.url.download()`. UDFs that operate on typed columns. The vlm-run/vlm-lab Daft pipelines (PR #1525) demonstrate batch VLM processing where each DataFrame row is a file flowing through encode → VLM → structured output.
- **Polars expressions**: Composable, lazy, zero-copy. mm already depends on Polars and Arrow.

### Design principle

**Don't add Daft as a dependency.** Build the multimodal DSL as a Polars plugin namespace + a thin batch API on `Context`. This keeps the dependency tree lean and leverages mm's existing Arrow foundation.

---

## Proposed Changes

### 1. `Context.map()` — Batch multimodal processing

The core primitive. Apply a function to every file in the context, with concurrency control, caching, and DataFrame output.

```python
ctx = Context("~/products")
images = ctx.filter(kind="image")

# Batch L2 — describe every image, 8 concurrent LLM calls
results = images.map(
    lambda f: f.cat(level=2, mode="fast"),
    column="description",
    concurrency=8,
)
# results: polars.DataFrame with columns [...L0 columns..., "description"]

# Batch encode — generate VLM-ready messages for every file
messages = images.map(
    lambda f: f.encode(strategy="resize", max_width=512),
    column="messages",
)

# Batch with structured output (JSON mode)
metadata = images.map(
    lambda f: f.generate(
        prompt="Return JSON: {title, objects: [str], dominant_color}",
        json_mode=True,
    ),
    column="metadata",
    concurrency=4,
)
```

**Implementation sketch:**

```python
class Context:
    def map(
        self,
        fn: Callable[[FileEntry], Any],
        *,
        column: str = "result",
        concurrency: int = 4,
        cache: bool = True,
        progress: bool = True,
    ) -> pl.DataFrame:
        """Apply fn to every file in parallel, return DataFrame with new column."""
        import concurrent.futures
        from rich.progress import Progress

        df = self.to_polars()
        results = [None] * len(df)

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {}
            for i, f in enumerate(self.files):
                futures[pool.submit(fn, f)] = i

            with Progress(disable=not progress) as prog:
                task = prog.add_task("Processing", total=len(futures))
                for future in concurrent.futures.as_completed(futures):
                    idx = futures[future]
                    results[idx] = future.result()
                    prog.advance(task)

        return df.with_columns(pl.Series(column, results))
```

Key properties:
- **Concurrency-safe**: ThreadPool for I/O-bound LLM calls (not CPU — Rust handles that)
- **Progress bar**: Rich progress by default (disable with `progress=False`)
- **Cache-aware**: L2 calls reuse mm's existing content-hash cache
- **Returns Polars**: Zero-copy DataFrame, ready for further transforms

### 2. `FileEntry` gains `.cat()`, `.encode()`, `.generate()`

Currently `FileEntry` is a thin dict wrapper. Upgrade it to support content operations:

```python
class FileEntry:
    def cat(self, *, level=1, mode=None) -> str:
        """Read content at the given level."""
        return self._ctx.cat(self.path, level=level, mode=mode)

    def encode(self, *, strategy=None, **kwargs) -> list[dict]:
        """Encode for VLM consumption."""
        return self._ctx.encode(self.path, strategy=strategy, **kwargs)

    def generate(self, *, prompt, json_mode=False, mode="fast", **kwargs) -> str:
        """One-shot VLM generation with a custom prompt."""
        ...
```

This makes `FileEntry` a self-contained handle for single-file operations within `map()`.

### 3. `Context.describe()` / `Context.embed()` — High-level batch operations

Sugar for the most common batch workflows:

```python
# Describe all files — returns DataFrame with "description" column
df = ctx.filter(kind="image").describe(mode="fast", concurrency=8)

# Embed all files — returns DataFrame with "embedding" column
df = ctx.filter(kind="image").embed(concurrency=4)

# Describe + embed in one pass (avoids double-encoding)
df = ctx.filter(kind="image").describe(mode="fast", embed=True)
```

**`describe()`** is `map(lambda f: f.cat(level=2, mode=mode), column="description")` with smart defaults.

**`embed()`** calls the Gemini embedding API (existing `store/embed.py`) in batch, returning vectors as a list column.

### 4. Polars Expression Namespace: `col.mm.*`

Register a Polars plugin namespace so multimodal operations compose with standard Polars expressions:

```python
import polars as pl
import mm.expr  # registers the namespace

df = ctx.to_polars()

# Use mm expressions in standard Polars chains
result = (
    df
    .filter(pl.col("kind") == "image")
    .filter(pl.col("size") > 100_000)
    .with_columns(
        pl.col("path").mm.cat(level=1).alias("content"),
        pl.col("path").mm.tokens().alias("est_tokens"),
    )
    .with_columns(
        pl.col("content").str.extract(r"(\d+x\d+)").alias("dimensions"),
    )
    .sort("est_tokens", descending=True)
)
```

The `mm` namespace maps to:

| Expression | Returns | Description |
|-----------|---------|-------------|
| `col.mm.cat(level=1)` | `Utf8` | Content extraction (L0/L1) |
| `col.mm.describe(mode="fast")` | `Utf8` | L2 VLM description |
| `col.mm.encode(strategy="resize")` | `List(Struct)` | VLM-ready messages |
| `col.mm.embed()` | `List(Float64)` | Embedding vector |
| `col.mm.tokens()` | `UInt64` | Estimated token count |
| `col.mm.mime()` | `Utf8` | MIME type |
| `col.mm.kind()` | `Utf8` | File kind |
| `col.mm.hash()` | `Utf8` | Content hash (xxh3) |

**Implementation**: Polars custom namespaces via `pl.api.register_expr_namespace("mm")`. The namespace methods call into mm's Rust core (L0/L1) or Python (L2) under the hood.

```python
@pl.api.register_expr_namespace("mm")
class MmExpr:
    def __init__(self, expr: pl.Expr):
        self._expr = expr

    def cat(self, *, level: int = 1, root: str = ".") -> pl.Expr:
        return self._expr.map_elements(
            lambda path: _cat_single(path, level=level, root=root),
            return_dtype=pl.Utf8,
        )

    def tokens(self) -> pl.Expr:
        """Estimate tokens from file content (chars / 4)."""
        return self._expr.mm.cat(level=1).str.len_chars() // 4

    def embed(self) -> pl.Expr:
        # This is better as a batch operation, see §6
        ...
```

### 5. Structured VLM Output → DataFrame Columns

The killer feature for data workflows: VLM calls that return structured JSON, automatically unpacked into typed DataFrame columns.

```python
# Define output schema
schema = {
    "title": str,
    "objects": list[str],
    "scene_type": str,
    "quality_score": float,
}

# Batch structured extraction
df = (
    ctx.filter(kind="image")
    .generate(
        prompt="Analyze this product image. Return JSON with: title, objects (list), scene_type, quality_score (0-1).",
        schema=schema,
        mode="fast",
        concurrency=8,
    )
)
# df has columns: path, name, size, kind, ..., title, objects, scene_type, quality_score
```

**How it works:**
1. Pipeline runs with `json_mode=True`
2. JSON response is parsed per-row
3. Schema dict maps keys → Polars dtypes
4. Result is unpacked into named columns

This is what makes Daft pipelines powerful: VLM outputs become first-class DataFrame columns you can filter, join, and aggregate on.

### 6. Batch Embedding with Vector Search

Extend the existing `store/embed.py` to work as a DataFrame operation:

```python
# Embed all images, store vectors
df = ctx.filter(kind="image").embed(concurrency=4)
# df now has an "embedding" column (list[float64], dim=768)

# Similarity search from text
results = ctx.search("red sports car on mountain road", limit=10)
# Returns DataFrame sorted by cosine similarity

# Cross-modal: find images similar to a specific image
results = ctx.search(reference="photo_001.jpg", limit=5)

# Cluster by embedding
from sklearn.cluster import KMeans
embeddings = df["embedding"].to_list()
df = df.with_columns(pl.Series("cluster", KMeans(n_clusters=5).fit_predict(embeddings)))
```

### 7. Pipeline Composition (Declarative YAML)

Extend the existing YAML pipeline system to support multi-step DAGs, not just single encode→generate:

```yaml
# pipelines/product-catalog.yaml
kind: image
mode: custom

steps:
  - name: resize
    type: encode
    strategy: resize
    max_width: 1024

  - name: describe
    type: generate
    prompt: "Describe this product image in one sentence."
    max_tokens: 128
    output: description

  - name: extract_metadata
    type: generate
    prompt: "Extract: {title, category, color, material}. Return JSON."
    json_mode: true
    max_tokens: 256
    output:
      title: str
      category: str
      color: str
      material: str

  - name: embed
    type: embed
    input: description  # embed the description, not the image
    output: embedding
```

```python
# Run the multi-step pipeline
df = ctx.filter(kind="image").run_pipeline("product-catalog", concurrency=8)
# df has: ...L0..., description, title, category, color, material, embedding
```

### 8. `mm pipe` CLI Command — Streaming Batch Processing

A new CLI command for batch operations, composable with Unix pipes:

```bash
# Describe all images in a directory
mm find ~/products --kind image | mm pipe describe --mode fast --concurrency 8

# Structured extraction to CSV
mm find ~/products --kind image | mm pipe generate \
  --prompt "Return JSON: {title, category, price_range}" \
  --json --format csv > catalog.csv

# Embed and export
mm find ~/docs --kind document | mm pipe embed --format parquet > embeddings.parquet

# Chain: describe, then embed the descriptions
mm find ~/photos --kind image \
  | mm pipe describe --mode fast \
  | mm pipe embed --input description \
  --format json > photo_index.json
```

`mm pipe` reads a TSV file list from stdin (output of `mm find`), processes each file through the specified operation, and outputs a table with the new column(s).

---

## Prioritized Implementation Plan

### Phase 1: Core batch primitives (highest impact, smallest surface)

1. **Upgrade `FileEntry`** — add `.cat()`, `.encode()`, `.generate()` methods with back-reference to Context
2. **`Context.map()`** — ThreadPool-based parallel map with Rich progress
3. **`Context.describe()`** — sugar for batch L2
4. **`mm pipe describe`** CLI command — batch descriptions from stdin

### Phase 2: Structured output + Polars namespace

5. **`Context.generate()`** — structured JSON output → DataFrame columns
6. **`mm.expr` Polars namespace** — `col.mm.cat()`, `col.mm.tokens()`, `col.mm.kind()`
7. **`mm pipe generate --json`** — structured extraction CLI

### Phase 3: Embeddings + search

8. **`Context.embed()`** — batch embedding with vector column
9. **`Context.search()`** — text-to-file and file-to-file similarity
10. **`mm pipe embed`** CLI command

### Phase 4: Pipeline composition

11. **Multi-step YAML pipelines** — extend `PipelineSpec` with `steps` array
12. **`Context.run_pipeline()`** — execute named multi-step pipeline
13. **`mm pipe run <pipeline-name>`** — CLI entry point

---

## Design Decisions

### Why Polars, not Daft?

| | Polars | Daft |
|---|---|---|
| Already a dependency | Yes | No |
| Arrow-native | Yes | Yes |
| Custom expression namespace | `register_expr_namespace` | Custom UDFs |
| Distribution | Single-machine (fine for mm's use case) | Ray/distributed |
| Startup time | ~10ms | ~200ms+ |
| Multimodal types | No (but we add via namespace) | Native Image/Embedding types |

mm is a **local CLI tool**, not a distributed pipeline. Polars is already in the dep tree, starts fast, and supports custom namespaces. Daft's distributed scheduler is overkill here.

If mm ever needs distributed processing (100K+ files), Daft could be an optional backend behind the same API:

```python
# Future: optional Daft backend
ctx.describe(mode="fast", backend="daft")  # uses Daft Ray cluster
ctx.describe(mode="fast", backend="polars")  # default, local ThreadPool
```

### Why ThreadPool, not asyncio?

- LLM calls are HTTP I/O bound → threads are fine
- `openai` SDK is synchronous by default
- ThreadPool is simpler, debuggable, no colored-function problem
- Rust core stays in threads via `rayon` anyway

### Why not just add columns to the Arrow table?

The L0 Arrow table from Rust is immutable and columnar. L2 results are inherently per-file and require I/O. The cleanest design is:

1. L0 scan → Arrow (Rust, fast, immutable)
2. `map()`/`describe()` → Polars DataFrame (Python, mutable, new columns)
3. `save()` → SQLite (persistence, vector search)

This keeps the Rust core focused on what it's fast at (scanning, hashing, extraction) and Python focused on orchestration.

---

## API Summary

```python
from mm import Context

ctx = Context("~/data")

# ── Batch operations ──
df = ctx.filter(kind="image").describe(mode="fast", concurrency=8)
df = ctx.filter(kind="video").describe(mode="accurate", concurrency=2)
df = ctx.filter(kind="document").embed(concurrency=4)

# ── Structured extraction ──
df = ctx.filter(kind="image").generate(
    prompt="Return JSON: {title, objects: [str], mood}",
    schema={"title": str, "objects": list, "mood": str},
    concurrency=8,
)

# ── Custom map ──
df = ctx.map(lambda f: len(f.cat(level=1).split()), column="word_count")

# ── Polars integration ──
import mm.expr
df = (
    ctx.to_polars()
    .filter(pl.col("kind") == "image")
    .with_columns(pl.col("path").mm.tokens().alias("est_tokens"))
    .sort("est_tokens", descending=True)
)

# ── Search ──
results = ctx.search("sunset over ocean", limit=10)

# ── Pipeline ──
df = ctx.filter(kind="image").run_pipeline("product-catalog", concurrency=8)

# ── Persistence ──
df.write_parquet("output.parquet")
ctx.save()  # upsert to SQLite
```

```bash
# ── CLI ──
mm find ~/data --kind image | mm pipe describe --mode fast -j 8 --format csv
mm find ~/data --kind image | mm pipe generate --prompt "..." --json --format tsv
mm find ~/data --kind document | mm pipe embed --format parquet
```

---

## Open Questions

1. **Should `map()` return a new `Context` or a plain `pl.DataFrame`?** Returning Context enables chaining (`ctx.filter().describe().embed()`), but a DataFrame is more interoperable. Proposed: return DataFrame by default, with `as_context=True` option.

2. **How to handle VLM rate limits?** Options: (a) simple semaphore in ThreadPool, (b) token-bucket rate limiter, (c) configurable `requests_per_second` param. Start with (a), add (b) if needed.

3. **Should embeddings live in the Polars DataFrame or only in SQLite?** Proposed: both. `embed()` returns a DataFrame with a `List(Float64)` column. `save()` persists to SQLite for `search()`.

4. **Parquet output for embeddings?** Polars can write `List(Float64)` to Parquet natively. This enables: `ctx.filter(kind="image").embed().write_parquet("index.parquet")` — a one-liner to build a vector index file.

5. **Should `mm pipe` be a new top-level command or a subcommand of `cat`?** Proposed: new command. `cat` is single-file; `pipe` is batch. Different mental models.
