"""Performance benchmarks for the put-based :class:`mm.Context` API.

These exercise the full PyO3 boundary (Python caller → Rust core →
Python return) and complement the pure-Rust Criterion suite at
``crates/mm-core/benches/refs.rs``.

All tests in this module are tagged **``slow``** — they're deselected
by the default ``pytest -m 'not integration and not slow'`` CI run and
only execute under ``make test-python-full`` / ``pytest -m slow``.

Budgets (wall-clock) are loose enough to survive noisy CI but tight
enough to catch accidental O(n²) regressions. Override via env vars:

- ``MM_TEST_REFS_PUT_10K_MAX_S`` (default 2.0s)
- ``MM_TEST_REFS_GET_HIT_MAX_US`` (default 25.0µs / op, 10k ctx)
- ``MM_TEST_REFS_TO_MSG_10K_MAX_S`` (default 2.5s for openai @ 10k paths)
- ``MM_TEST_REFS_TREE_10K_MAX_S`` (default 2.0s; Rich print dominates)
- ``MM_TEST_REFS_REPR_10K_MAX_S`` (default 0.5s)
- ``MM_TEST_REFS_MISS_10K_MAX_S`` (default 0.25s; Levenshtein search)
"""

from __future__ import annotations

import io
import os
import time
from pathlib import Path

import pytest
from PIL import Image

import mm
from mm.refs import RefNotFoundError

pytestmark = pytest.mark.slow


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def ten_image_paths(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    """Ten tiny PNGs. Cycled by the bench to hit the `put(Path)` path
    without doing 10K disk writes in fixture setup."""
    root = tmp_path_factory.mktemp("ten_pngs")
    paths: list[Path] = []
    for i in range(10):
        p = root / f"img_{i:02}.png"
        Image.new("RGB", (16, 16), (i * 20 % 256, 0, 0)).save(p)
        paths.append(p)
    return paths


@pytest.fixture(scope="module")
def pil_image_pool() -> list[Image.Image]:
    """Ten small PIL images (kept alive for in-memory put benches)."""
    return [Image.new("RGB", (32, 32), (i * 20 % 256, 0, 0)) for i in range(10)]


@pytest.fixture(scope="module")
def bytes_pool() -> list[bytes]:
    """Ten small PNG byte blobs."""
    blobs: list[bytes] = []
    for i in range(10):
        buf = io.BytesIO()
        Image.new("RGB", (16, 16), (i * 25 % 256, 0, 0)).save(buf, format="PNG")
        blobs.append(buf.getvalue())
    return blobs


def _budget_s(name: str, default: float) -> float:
    return float(os.environ.get(name, str(default)))


def _build_ctx(paths: list[Path], n: int) -> mm.Context:
    ctx = mm.Context()
    for i in range(n):
        ctx.put(paths[i % len(paths)])
    return ctx


def _build_ctx_with_meta(paths: list[Path], n: int) -> mm.Context:
    ctx = mm.Context()
    for i in range(n):
        ctx.put(
            paths[i % len(paths)],
            metadata={
                "note": f"note {i}",
                "summary": f"pre-extracted summary for item {i}",
                "tags": ["a", "b", "c"],
            },
        )
    return ctx


# ── pytest-benchmark micro-benches (throughput / latency) ─────────────


class TestBenchPut:
    def test_put_path_1k(self, benchmark, ten_image_paths: list[Path]):
        """Throughput of ``ctx.put(Path)`` at 1K items."""
        result = benchmark(_build_ctx, ten_image_paths, 1_000)
        assert len(result.items()) == 1_000

    def test_put_path_10k(self, benchmark, ten_image_paths: list[Path]):
        result = benchmark(_build_ctx, ten_image_paths, 10_000)
        assert len(result.items()) == 10_000

    def test_put_path_with_metadata_1k(self, benchmark, ten_image_paths: list[Path]):
        """Metadata is JSON-serialised and reparsed in Rust — make sure
        adding ``note``/``summary``/``tags`` doesn't blow up throughput."""
        result = benchmark(_build_ctx_with_meta, ten_image_paths, 1_000)
        assert len(result.items()) == 1_000

    def test_put_pil_1k(self, benchmark, pil_image_pool: list[Image.Image]):
        """In-memory PIL path — stores a ``Py<PyAny>`` + mime/byte_len.
        Note: each put keeps a refcount on the pooled image — no copy."""

        def build() -> mm.Context:
            ctx = mm.Context()
            for i in range(1_000):
                ctx.put(pil_image_pool[i % len(pil_image_pool)])
            return ctx

        result = benchmark(build)
        assert len(result.items()) == 1_000

    def test_put_bytes_1k(self, benchmark, bytes_pool: list[bytes]):
        def build() -> mm.Context:
            ctx = mm.Context()
            for i in range(1_000):
                ctx.put(bytes_pool[i % len(bytes_pool)])
            return ctx

        result = benchmark(build)
        assert len(result.items()) == 1_000


class TestBenchGet:
    def test_get_hit_10k(self, benchmark, ten_image_paths: list[Path]):
        ctx = _build_ctx(ten_image_paths, 10_000)
        refs = ctx.ref_ids()
        state = {"i": 0}

        def one_get():
            r = refs[state["i"] % len(refs)]
            state["i"] += 1
            return ctx.get(r)

        result = benchmark(one_get)
        assert isinstance(result, Path)

    def test_get_miss_10k(self, benchmark, ten_image_paths: list[Path]):
        ctx = _build_ctx(ten_image_paths, 10_000)

        def one_miss():
            try:
                ctx.get("img_zzzzzz")
            except RefNotFoundError:
                return True
            return False

        result = benchmark(one_miss)
        assert result is True


class TestBenchRender:
    def test_print_tree_10k(self, benchmark, ten_image_paths: list[Path], capsys):
        ctx = _build_ctx(ten_image_paths, 10_000)
        benchmark(ctx.print_tree)
        capsys.readouterr()  # drain so later tests are clean

    def test_repr_10k(self, benchmark, ten_image_paths: list[Path]):
        ctx = _build_ctx(ten_image_paths, 10_000)
        result = benchmark(repr, ctx)
        assert "Context(session=" in result

    def test_to_md_fast_1k(self, benchmark, ten_image_paths: list[Path]):
        ctx = _build_ctx_with_meta(ten_image_paths, 1_000)
        result = benchmark(ctx.to_md)
        assert "| ref " in result


class TestBenchToMessages:
    """``to_messages`` lives in Python (it dispatches to encoders), so
    this catches regressions in the Python driver + round-trip cost for
    the encoded payload. We use a small size (100 items) because the
    encoders actually open images."""

    def test_openai_100_paths(self, benchmark, ten_image_paths: list[Path]):
        ctx = _build_ctx(ten_image_paths, 100)
        result = benchmark(ctx.to_messages, format="openai")
        assert isinstance(result, list) and len(result) == 1

    def test_gemini_100_paths(self, benchmark, ten_image_paths: list[Path]):
        ctx = _build_ctx(ten_image_paths, 100)
        result = benchmark(ctx.to_messages, format="gemini")
        assert isinstance(result, list) and len(result) == 1


class TestBenchIds:
    """Pure ID / uuid7 generation throughput (PyO3 boundary included)."""

    def test_uuid7(self, benchmark):
        uid = benchmark(mm.uuid7)
        assert len(uid) == 36 and uid[14] == "7"

    def test_new_session_id(self, benchmark):
        # ``new_session_id`` is the ergonomic alias most callers use.
        from mm.refs import new_session_id

        sid = benchmark(new_session_id)
        assert isinstance(sid, str) and len(sid) == 36


class TestBenchRefNotFound:
    """The error message includes Levenshtein search + a markdown table
    render. Budget explicitly so dropping the prefix-filter in
    ``closest_ref`` (O(n) today, would be O(n·kinds) without) gets
    caught."""

    def test_miss_message_10k(self, benchmark, ten_image_paths: list[Path]):
        ctx = _build_ctx(ten_image_paths, 10_000)
        # Perturb the last char of a real ref so the suggestion path fires.
        real = ctx.ref_ids()[5_000]
        typo = real[:-1] + ("a" if real[-1] != "a" else "z")

        def trigger() -> str:
            try:
                ctx.get(typo)
            except RefNotFoundError as e:
                return str(e)
            raise AssertionError("expected miss")

        msg = benchmark(trigger)
        assert "Did you mean" in msg


# ── Latency-budget regression guards (wall-clock, no benchmark fixture) ─


def test_put_10k_under_budget(ten_image_paths: list[Path]) -> None:
    budget = _budget_s("MM_TEST_REFS_PUT_10K_MAX_S", 2.0)
    t0 = time.perf_counter()
    ctx = _build_ctx(ten_image_paths, 10_000)
    elapsed = time.perf_counter() - t0
    assert len(ctx.items()) == 10_000
    assert elapsed < budget, f"put×10k took {elapsed:.3f}s (budget {budget}s)"


def test_get_hit_amortised_under_budget(ten_image_paths: list[Path]) -> None:
    # Amortised per-call budget over 10k get() hits against a 10k ctx.
    budget_us = float(os.environ.get("MM_TEST_REFS_GET_HIT_MAX_US", "25.0"))
    ctx = _build_ctx(ten_image_paths, 10_000)
    refs = ctx.ref_ids()
    t0 = time.perf_counter()
    for i in range(10_000):
        ctx.get(refs[i])
    elapsed = time.perf_counter() - t0
    per_op_us = (elapsed / 10_000) * 1e6
    assert per_op_us < budget_us, (
        f"get() amortised {per_op_us:.2f}µs/op (budget {budget_us}µs/op, total {elapsed:.3f}s)"
    )


def test_to_messages_10k_under_budget_openai(ten_image_paths: list[Path]) -> None:
    """Upper bound on encoder dispatch at 10k items. We use a *single*
    reused path so PIL I/O isn't the dominant term — the point is the
    Python/Rust boundary cost."""
    budget = _budget_s("MM_TEST_REFS_TO_MSG_10K_MAX_S", 2.5)
    ctx = mm.Context()
    only_path = ten_image_paths[0]
    for _ in range(10_000):
        ctx.put(only_path)
    t0 = time.perf_counter()
    msgs = ctx.to_messages(format="openai")
    elapsed = time.perf_counter() - t0
    assert msgs and msgs[0]["role"] == "user"
    assert elapsed < budget, f"to_messages(10k, openai) took {elapsed:.3f}s (budget {budget}s)"


def test_print_tree_10k_under_budget(
    ten_image_paths: list[Path], capsys: pytest.CaptureFixture
) -> None:
    # Generous budget: Rust renders the tree string in ~5ms, but Rich's
    # ANSI line printer then paints 10k lines to an in-memory capture
    # buffer which dominates. The budget here is really a regression
    # guard against accidentally making the Rust side O(n²).
    budget = _budget_s("MM_TEST_REFS_TREE_10K_MAX_S", 2.0)
    ctx = _build_ctx(ten_image_paths, 10_000)
    t0 = time.perf_counter()
    ctx.print_tree()
    elapsed = time.perf_counter() - t0
    capsys.readouterr()
    assert elapsed < budget, f"print_tree(10k) took {elapsed:.3f}s (budget {budget}s)"


def test_repr_10k_under_budget(ten_image_paths: list[Path]) -> None:
    budget = _budget_s("MM_TEST_REFS_REPR_10K_MAX_S", 0.5)
    ctx = _build_ctx(ten_image_paths, 10_000)
    t0 = time.perf_counter()
    s = repr(ctx)
    elapsed = time.perf_counter() - t0
    assert "items=10000" in s
    assert elapsed < budget, f"repr(10k) took {elapsed:.3f}s (budget {budget}s)"


def test_miss_message_10k_under_budget(ten_image_paths: list[Path]) -> None:
    """Levenshtein across 10k refs (filtered by prefix) must stay cheap
    enough that a typo-heavy agent loop isn't pathological."""
    budget = _budget_s("MM_TEST_REFS_MISS_10K_MAX_S", 0.25)
    ctx = _build_ctx(ten_image_paths, 10_000)
    real = ctx.ref_ids()[5_000]
    typo = real[:-1] + ("a" if real[-1] != "a" else "z")
    t0 = time.perf_counter()
    try:
        ctx.get(typo)
    except RefNotFoundError as e:
        msg = str(e)
    elapsed = time.perf_counter() - t0
    assert "Did you mean" in msg
    assert elapsed < budget, f"RefNotFoundError(10k) took {elapsed:.3f}s (budget {budget}s)"


# ── Memory-footprint sanity (Rust-side storage) ───────────────────────


def test_memory_footprint_10k_path_under_budget(ten_image_paths: list[Path]) -> None:
    """Sanity check: a 10K path-backed context should sit comfortably
    under 3 MB on the heap (CompactString-backed RefId + lean Item).
    Uses ``tracemalloc`` so we measure *Python-side* allocations; the
    Rust heap is tracked separately by Criterion."""
    import tracemalloc

    budget_bytes = int(os.environ.get("MM_TEST_REFS_MEM_10K_MAX_BYTES", str(3_000_000)))
    tracemalloc.start()
    snap_before = tracemalloc.take_snapshot()
    ctx = _build_ctx(ten_image_paths, 10_000)
    snap_after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    diff = snap_after.compare_to(snap_before, "filename")
    total = sum(stat.size_diff for stat in diff if stat.size_diff > 0)
    assert len(ctx.items()) == 10_000
    assert total < budget_bytes, (
        f"Python-side alloc for 10k put was {total:,}B (budget {budget_bytes:,}B)"
    )
