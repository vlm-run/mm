# mm Python API

`mm.Context` is the main entry point for building a multimodal prompt
incrementally, then handing the whole thing to a VLM. This doc covers
the public Python surface; under the hood everything runs through the
Rust [`_mm.PyContext`](../crates/mm-python/src/refs.rs) core so memory
is compact and insert/lookup/render is sub-millisecond at 10K items.

> Looking for the directory-scan surface (`Context("~/data")` +
> `to_polars`/`sql`/`show`)? That mode is preserved unchanged — see
> [USER_GUIDE.md](USER_GUIDE.md). This doc is about the new
> **incremental put-based** mode.

## TL;DR

```python
import mm
from pathlib import Path
from PIL import Image

ctx = mm.Context(session_id=mm.uuid7())          # or omit; auto-mints a UUIDv7

img:  mm.Ref = ctx.put(Path("photo.jpg"))
img2: mm.Ref = ctx.put(Image.open("x.png"),
                       metadata={"note": "product hero shot"})
doc:  mm.Ref = ctx.put(Path("paper.pdf"),
                       metadata={"summary": "Attention is all you need",
                                 "tags": ["nlp", "transformer"]})
vid:  mm.Ref = ctx.put(Path("clip.mp4"),
                       metadata={"scene": 3, "actor": "A"})

from openai.types.chat import ChatCompletionMessageParam
from google.genai import types as genai_types

messages_openai: list[ChatCompletionMessageParam] = ctx.to_messages(format="openai")
messages_gemini: list[genai_types.ContentDict]    = ctx.to_messages(format="gemini")

obj = ctx.get(img)                               # Path | PIL.Image | bytes | str
row = mm.Context.get(f"{ctx.session_id}/{img}")  # cross-session DB lookup

ctx.print_tree()                                 # T4 tree with metadata
print(ctx.to_md(mode="fast"))                    # markdown table w/ cat content
print(repr(ctx))                                 # markdown __repr__
```

## Core types

### `mm.Ref`

A typed alias for ref id strings. Runtime is just `str`; IDEs and mypy
see a distinct type thanks to `typing.Annotated`.

```python
from typing import Annotated
Ref = Annotated[str, "mm.Ref"]   # e.g. "img_a1b2c3"
```

### `mm.uuid7() -> str`

Canonical UUIDv7 (time-ordered) in the hyphenated form
`xxxxxxxx-xxxx-7xxx-Nxxx-xxxxxxxxxxxx`. Python 3.12's stdlib `uuid`
doesn't ship `uuid7`, so `mm` provides its own — implemented in Rust
(see `crates/mm-core/src/refs.rs`). Preferred default for new session
ids because two uuids compared lexicographically sort in creation
order.

### `mm.RefNotFoundError`

`KeyError` subclass raised by `ctx.get(ref)` on miss. The message is
an agent-friendly markdown table: closest-match suggestion (Levenshtein
distance ≤ 4 within the same kind) followed by the full context's ref
listing.

## `mm.Context`

```python
Context(
    root: str | Path | None = None,
    *,
    session_id: str | None = None,
    # ...directory-scan-only kwargs (n_threads, no_ignore, …) elided
)
```

- **Incremental mode** (the one this doc covers): pass no `root`. A
  fresh `session_id` is minted via `mm.uuid7()` when omitted.
- **Directory-scan mode**: pass a `root` path to get the legacy
  Arrow-backed scan surface. Both modes share `session_id` + `refs`.

### `ctx.put(obj, *, metadata=None) -> mm.Ref`

Attach an item. Accepted types:

| Input                | Stored as       | `get()` returns               |
|----------------------|-----------------|-------------------------------|
| `pathlib.Path`       | `ItemSource::Path`      | new `pathlib.Path`      |
| `str` (file path)    | `ItemSource::Path`      | new `pathlib.Path`      |
| `str` (`http(s)://`) | `ItemSource::Url`       | the URL string          |
| `PIL.Image.Image`    | `ItemSource::InMemory`  | **the exact object**    |
| `bytes`              | `ItemSource::InMemory`  | the same `bytes`        |

`metadata` is a single optional JSON-serialisable `dict` holding any
extra context you want to ride along with the item. Common keys by
convention:

- `note` — short human-readable note.
- `summary` — longer summary / caption. Used as the "pre-extracted"
  content fallback in `to_md(mode="fast")`.
- `tags` — free-form list of strings.
- …plus anything else your pipeline needs (`{"scene": 3, "actor": "A"}`).

The dict is emitted as a leading text block per item in `to_messages`
so VLMs see it inline, and is also surfaced in `__repr__`, `to_md`,
and `print_tree`.

Returns the generated ref id (`<prefix>_<6 hex>`), typed as `mm.Ref`.

#### Example

```python
img = ctx.put(Path("photo.jpg"), metadata={"note": "hero shot"})
doc = ctx.put(Path("paper.pdf"),
              metadata={"summary": "Attention is all you need",
                        "tags": ["nlp", "transformer"]})
vid = ctx.put(Path("clip.mp4"), metadata={"scene": 3})
```

### `ctx.get(ref) -> Path | PIL.Image.Image | bytes | str`

Local lookup by ref. Accepts a bare ref (`"img_a1b2c3"`) or a global
ref (`"<session_id>/<ref_id>"`); the session segment must match this
context's `session_id`.

- Path-backed items return a freshly-constructed `pathlib.Path`.
- In-memory items return the **exact Python object** that was `put` (no
  copy, no rehydrate — identity is preserved).
- URL items return the URL string.

Raises `RefNotFoundError` on miss. The error message prints the full
ref table + a "did you mean" suggestion:

```text
RefNotFoundError: ref 'img_a1b2cZ' not found in session 019da4…. Did you mean: img_a1b2c3?

Available refs:
Context(session=019da4…, items=3)

| ref        | kind  | source                |
|------------|-------|-----------------------|
| img_a1b2c3 | image | /abs/path/photo.jpg   |
| doc_d4e5f6 | doc   | /abs/path/paper.pdf   |
| vid_7890ab | video | /abs/path/clip.mp4    |
```

### `Context.get(global_ref, *, session_id=None, db=None)` (classmethod)

Cross-session resolver. Parses a `"<session>/<ref>"` global ref (or
accepts a bare ref + `session_id=...`) and returns the `files` row dict
from the global `~/.local/share/mm/mm.db`, or `None` on miss.

Use this when you have a ref from a persisted context and no live
`Context` instance. Replaces the (still-supported) legacy
`Context.resolve()`.

### `ctx.to_messages(format="openai", *, encoders=None) -> list[dict]`

Encode every item into a single user-turn message list, ready to drop
into the respective SDK call. The returned shape is a plain Python
list of dicts, typed to match the target SDK:

```python
from openai.types.chat import ChatCompletionMessageParam
from google.genai import types as genai_types

messages_openai: list[ChatCompletionMessageParam] = ctx.to_messages(format="openai")
messages_gemini: list[genai_types.ContentDict]    = ctx.to_messages(format="gemini")
```

- `format="openai"` → `[{"role": "user", "content": [{"type": ...}, …]}]`
  — drop directly into `client.chat.completions.create(messages=...)`.
- `format="gemini"` → `[{"role": "user", "parts": [{"inline_data": …}, {"text": …}]}]`
  — drop into `model.generate_content(contents=...)`.

Per-kind encoder overrides:

```python
messages: list[ChatCompletionMessageParam] = ctx.to_messages(
    format="openai",
    encoders={"image": "tile", "video": "mosaic"},
)
```

Unspecified kinds use sensible defaults (`image-resize`,
`video-frame-sample`, `document-rasterize`). Encoder names come from
the `mm.encoders` registry — see `--list-encoders`.

User metadata is emitted as a leading text part per item
(`[ref=<id>] note: <text>`), so VLMs see your context inline.

### `ctx.to_md(mode="fast") -> str`

Markdown table with one row per ref: `ref | kind | source | content`.
`mode="fast"` populates each row with the metadata-tier content
(`files.text_preview` — produced by `extract_meta`; no LLM call) for
non-text kinds, and raw text for code/text files. (Equivalent to the
CLI's default `mm cat --mode metadata` for binary kinds — there is no
separate `mode="metadata"` overload here; `to_md` already returns the
metadata tier when called without arguments.)

`mode="accurate"` is reserved for the LLM-backed pipeline and currently
raises `NotImplementedError`.

```python
print(ctx.to_md())
# | ref        | kind  | source              | content                              |
# |------------|-------|---------------------|--------------------------------------|
# | img_a1b2c3 | image | /abs/path/photo.jpg | 3024×4032, jpeg, EXIF: Canon EOS…    |
# | doc_d4e5f6 | doc   | /abs/path/paper.pdf | # Title…\n## Abstract…               |
```

### `ctx.print_tree(layout="insertion") -> None`

Print a [`rich.Tree`](https://rich.readthedocs.io/en/stable/tree.html)
rendering of the context. The default `"insertion"` layout (T4) shows
items in insertion order with metadata on sub-branches — best for the
"build a prompt incrementally" workflow where metadata is the whole
point.

```
Context(session=019da4…, items=5)
├── [1] img_a1b2c3  image  /abs/path/photo.jpg
├── [2] img_9f0e12  image  PIL.Image(RGB, 1024×768)
│        └─ note: "product hero shot"
├── [3] doc_d4e5f6  document  /abs/path/paper.pdf
│        ├─ summary: "Attention is all you need"
│        └─ tags: [nlp, transformer]
├── [4] vid_7890ab  video  /abs/path/clip.mp4
│        └─ metadata: {"scene": 3, "actor": "A"}
└── [5] img_111222  image  https://cdn.example.com/x.jpg
```

Other layouts are declared in the docstring so they're discoverable,
but raise `NotImplementedError` for now:

- `"paths"` — directory hierarchy with refs on the right. [TODO]
- `"kind"` — grouped by kind (images, documents, videos, …). [TODO]
- `"flat"` — ref-first flat list. [TODO; likely ships as
  `print_table()` instead of a tree]
- `"hybrid"` — paths + per-item dim metadata line. [TODO]

### `__repr__` → markdown

`repr(ctx)` returns a markdown summary: `session_id`, item count, and
the `ref | kind | source` table. Works well in Jupyter / doc snippets
and doubles as the body of `RefNotFoundError`.

### `ctx.save()` (deferred)

Not implemented for put-based contexts. Planned behaviour:

- Write `(session_id, ref_id, kind, uri, content_hash, metadata)` to
  the `files` table in `~/.local/share/mm/mm.db`.
- For in-memory objects, spool to a content-addressed cache directory
  `~/.local/share/mm/blobs/<xxh3>.<ext>` and record the blob URI.
- Make `Context.get("<session>/<ref>")` resolve via the DB across
  processes.
- Idempotent on repeat calls for the same `(session_id, ref_id)`.

Directory-scan `Context(root)` retains its existing `save()` (writes
the Arrow table to the global DB).

## Performance architecture

The hot path is Rust. Python is a thin façade.

- **`crates/mm-core/src/refs.rs`** owns `RefId`, `Kind`, `Item`,
  `ItemSource`, `Context` (Rust struct), `make_ref_id`, `uuid7`.
  - `RefId` = `CompactString` — the canonical `<prefix>_<6 hex>`
    shape fits inside the 24-byte inline SSO buffer, so refs never
    heap-allocate on the hot path.
  - `Item` = `{ ref_id, kind, source, metadata: Option<Box<MetaMap>> }`.
    Items without user metadata pay only one pointer's worth of memory
    and zero allocations.
  - `by_ref: HashMap<RefId, u32>` gives O(1) ref→index lookup.
- **`crates/mm-python/src/refs.rs`** exposes `PyContext` and keeps
  in-memory Python objects alive in a parallel `Vec<Option<Py<PyAny>>>`
  indexed by item position. That's why `ctx.get(ref)` returns the
  exact object the caller passed to `ctx.put` — no copy, no rehydrate.
- **Rendering** (`__repr__`, `print_tree`, `to_md` table assembly,
  `RefNotFoundError` message, "did you mean" Levenshtein search) all
  happen in Rust, so Python only pays one FFI boundary crossing to get
  a ready-to-print string.

### Memory budget

Per item, excluding the user's stored object:

- path-backed: ~56 bytes;
- in-memory: ~64 bytes + one `Py<PyAny>` refcount bump;
- URL-backed: ~56 bytes.

A 10K-item context without metadata fits in < 1 MB on the Rust side.

## Benchmarks

Two complementary suites keep the hot path honest:

### Rust / Criterion — `crates/mm-core/benches/refs.rs`

Pure-Rust, no PyO3 boundary. Targets the `mm_core::refs::Context`
primitives.

```sh
cargo bench -p mm-core --bench refs
# Or target a group:
cargo bench -p mm-core --bench refs -- refs/put_path
cargo bench -p mm-core --bench refs -- refs/get
cargo bench -p mm-core --bench refs -- refs/render
cargo bench -p mm-core --bench refs -- refs/ref_not_found
cargo bench -p mm-core --bench refs -- refs/mixed
```

Coverage:

| Group                              | Scales            | What it measures                              |
|------------------------------------|-------------------|-----------------------------------------------|
| `refs/make_ref_id/{kind}`          | per-kind          | ID generation (`OsRng` + base36 encode)       |
| `refs/uuid7`                       | —                 | `mm.uuid7()` generation latency               |
| `refs/put_path`                    | 100 / 1K / 10K / 100K | Path-backed `put` throughput              |
| `refs/put_inmem`                   | 1K / 10K          | In-memory (PIL / bytes) `put` throughput      |
| `refs/put_with_metadata`           | 1K / 10K          | Same, with `note`+`summary`+`tags` populated  |
| `refs/get_hit`                     | 1K / 10K / 100K   | `by_ref: HashMap` lookup (realistic hit)      |
| `refs/get_miss`                    | 1K / 10K          | Miss — short-circuits before suggestion       |
| `refs/render_tree_insertion`       | 100 / 1K / 10K    | Rust tree rendering (excludes Rich)           |
| `refs/render_tree_insertion_with_meta` | 1K            | Same, with 3 metadata branches per item       |
| `refs/repr_markdown`               | 100 / 1K / 10K    | `repr(ctx)` table generation                  |
| `refs/to_md_with_contents`         | 1K                | `to_md()` rendering given pre-extracted text  |
| `refs/ref_not_found_message`       | 100 / 1K / 10K    | Full `RefNotFoundError` body (typo shape)     |
| `refs/closest_ref_10k`             | 10K               | Levenshtein-across-all-prefix-matching-refs   |
| `refs/mixed_put_get_render`        | 1K / 10K          | Agent-loop shape (put→get→repr→tree)          |

### Python / pytest-benchmark — `tests/python/test_refs_api_perf.py`

Full PyO3 round-trip (Python → Rust → Python). Marked
`pytest.mark.slow` so the default `make test-python` stays fast; run
via `make test-python-full` or:

```sh
pytest tests/python/test_refs_api_perf.py -m slow
pytest tests/python/test_refs_api_perf.py -m slow --benchmark-only
pytest tests/python/test_refs_api_perf.py -m slow --benchmark-disable  # budgets only
```

Two classes of tests live here:

1. `TestBench*` — `pytest-benchmark` micro-benches for
   `put` (path / PIL / bytes / + metadata), `get` (hit / miss),
   `print_tree`, `repr`, `to_md`, `to_messages` (openai + gemini),
   `uuid7`, and `RefNotFoundError` construction.
2. Latency-budget regression guards (`test_*_under_budget`) that fail
   fast if a change pushes the Python-bound path past its budget. Each
   budget is overridable via an env var (see docstring at the top of
   the file).

### Indicative numbers (Apple M-series, release build)

| Operation                            | Median    | Throughput      |
|--------------------------------------|-----------|-----------------|
| `ctx.get(ref)` hit, 10K-item context | **~800ns**| ~1.2 M ops/s    |
| `mm.uuid7()`                         | ~1.3 µs   | ~770 K ops/s    |
| `new_session_id()`                   | ~1.3 µs   | ~770 K ops/s    |
| `ctx.put(Path)`, amortised           | ~32 µs    | ~31 K puts/s    |
| `ctx.put(bytes)`, amortised          | ~7 µs     | ~140 K puts/s   |
| `ctx.put(PIL.Image)`, amortised      | ~7 µs     | ~140 K puts/s   |
| `repr(ctx)` @ 10K items              | ~3 ms     | —               |
| `ctx.print_tree()` @ 10K items       | ~930 ms\* | —               |
| `RefNotFoundError` msg @ 10K items   | ~11 ms    | —               |

\* `print_tree` is dominated by Rich's ANSI line printer — the Rust
tree-string generation itself is ~5ms at 10K. Strip to raw output with
`print(ctx._pyctx.render_tree_insertion())` if you need the faster
path.

The `ctx.put(Path)` amortised cost includes `Path.resolve()` + a stat
to sniff the MIME; `ctx.put(bytes)` / `ctx.put(PIL.Image)` skip those
and land inside the ~7µs PyO3-boundary budget dominated by the
`Py<PyAny>` clone + one JSON metadata roundtrip.

## Error types

- **`mm.RefNotFoundError`** — `KeyError` subclass. Raised by
  `ctx.get(ref)` on miss; message is a markdown table + suggestion.
- **`ValueError`** — malformed global ref, mismatched session id, or
  `metadata=` containing non-JSON-serialisable keys.
- **`TypeError`** — `put()` received an unsupported object type.
- **`FileNotFoundError`** — `put()` received a path that doesn't exist.
- **`NotImplementedError`** — `print_tree(layout="paths"|"kind"|…)`,
  `to_md(mode="accurate")`, or `save()` on an incremental context.

## Recipe: OpenAI chat completion

```python
import mm
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from pathlib import Path

ctx = mm.Context()
ctx.put(Path("whiteboard.jpg"), metadata={"note": "meeting notes"})
ctx.put(Path("slides.pdf"), metadata={"summary": "Q3 plan"})

ctx_messages: list[ChatCompletionMessageParam] = ctx.to_messages(format="openai")

client = OpenAI()
resp = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "Summarise the attached context."},
        *ctx_messages,
    ],
)
print(resp.choices[0].message.content)
```

## Recipe: Gemini generate_content

```python
import mm
import google.generativeai as genai
from google.genai import types as genai_types
from pathlib import Path

ctx = mm.Context()
ctx.put(Path("clip.mp4"), metadata={"summary": "lecture on attention"})

contents: list[genai_types.ContentDict] = ctx.to_messages(format="gemini")

model = genai.GenerativeModel("gemini-2.0-pro")
resp = model.generate_content(contents=contents)
print(resp.text)
```
