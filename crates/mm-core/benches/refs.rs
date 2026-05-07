//! Criterion benches for the `refs` module.
//!
//! Run the whole suite:
//!
//! ```sh
//! cargo bench -p mm-core --bench refs
//! ```
//!
//! The benchmarks are grouped so you can target one area:
//!
//! ```sh
//! cargo bench -p mm-core --bench refs -- refs/add_path
//! cargo bench -p mm-core --bench refs -- refs/get
//! cargo bench -p mm-core --bench refs -- refs/render
//! cargo bench -p mm-core --bench refs -- refs/ref_not_found
//! cargo bench -p mm-core --bench refs -- refs/mixed
//! ```
//!
//! These benches measure the _pure Rust_ hot path; see
//! `tests/python/test_refs_api_perf.py` for Python-bound (PyO3 boundary
//! included) latency budgets that run under `pytest -m slow`.

use std::collections::HashMap;

use compact_str::CompactString;
use criterion::{BenchmarkId, Criterion, Throughput, black_box, criterion_group, criterion_main};
use mm_core::meta::FileKind;
use mm_core::refs::{Context, ItemSource, MetaValue, PromptRole, make_ref_id, uuid7};

// ── Helpers ─────────────────────────────────────────────────────────────

const KINDS: [FileKind; 5] = [
    FileKind::Image,
    FileKind::Video,
    FileKind::Document,
    FileKind::Audio,
    FileKind::Code,
];

fn build_ctx(n: usize) -> Context {
    let mut ctx = Context::new(uuid7());
    for i in 0..n {
        let kind = KINDS[i % KINDS.len()];
        ctx.add(
            PromptRole::User,
            kind,
            ItemSource::Path {
                path: CompactString::from(format!("/abs/path/f{:05}.bin", i)),
            },
            None,
        );
    }
    ctx
}

fn build_ctx_with_metadata(n: usize) -> Context {
    let mut ctx = Context::new(uuid7());
    for i in 0..n {
        let kind = KINDS[i % KINDS.len()];
        let meta = vec![
            (
                "note".into(),
                MetaValue::Str(CompactString::from(format!("note {i}"))),
            ),
            (
                "summary".into(),
                MetaValue::Str(CompactString::from(format!(
                    "pre-extracted summary for item {i}: lorem ipsum dolor sit amet"
                ))),
            ),
            (
                "tags".into(),
                MetaValue::StrList(vec!["a".into(), "b".into(), "c".into()]),
            ),
        ];
        ctx.add(
            PromptRole::User,
            kind,
            ItemSource::Path {
                path: CompactString::from(format!("/abs/path/f{:05}.bin", i)),
            },
            Some(meta),
        );
    }
    ctx
}

// ── ID / UUID micro-benches ─────────────────────────────────────────────

fn bench_make_ref_id(c: &mut Criterion) {
    let mut group = c.benchmark_group("refs/make_ref_id");
    group.throughput(Throughput::Elements(1));
    for kind in KINDS {
        group.bench_function(format!("{:?}", kind), |b| {
            b.iter(|| make_ref_id(black_box(kind)));
        });
    }
    group.finish();
}

fn bench_uuid7(c: &mut Criterion) {
    c.bench_function("refs/uuid7", |b| b.iter(uuid7));
}

// ── add(...) throughput across scales ───────────────────────────────────

fn bench_add_path(c: &mut Criterion) {
    let mut group = c.benchmark_group("refs/add_path");
    for n in [100usize, 1_000, 10_000, 100_000] {
        group.throughput(Throughput::Elements(n as u64));
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, &n| {
            b.iter(|| build_ctx(n));
        });
    }
    group.finish();
}

fn bench_add_inmem(c: &mut Criterion) {
    let mut group = c.benchmark_group("refs/add_inmem");
    for n in [1_000usize, 10_000] {
        group.throughput(Throughput::Elements(n as u64));
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, &n| {
            b.iter(|| {
                let mut ctx = Context::new("s");
                for i in 0..n {
                    ctx.add(
                        PromptRole::User,
                        FileKind::Image,
                        ItemSource::InMemory {
                            mime: "image/png".into(),
                            byte_len: 12_345,
                            desc: CompactString::from(format!("PIL.Image({})", i)),
                        },
                        None,
                    );
                }
            });
        });
    }
    group.finish();
}

fn bench_add_with_metadata(c: &mut Criterion) {
    let mut group = c.benchmark_group("refs/add_with_metadata");
    for n in [1_000usize, 10_000] {
        group.throughput(Throughput::Elements(n as u64));
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, &n| {
            b.iter(|| build_ctx_with_metadata(n));
        });
    }
    group.finish();
}

// ── get (hit / miss) latency ────────────────────────────────────────────

fn bench_get_hit(c: &mut Criterion) {
    let mut group = c.benchmark_group("refs/get_hit");
    for n in [1_000usize, 10_000, 100_000] {
        let ctx = build_ctx(n);
        let refs: Vec<String> = ctx.items.iter().map(|i| i.ref_id.to_string()).collect();
        group.throughput(Throughput::Elements(1));
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, _| {
            let mut i = 0usize;
            b.iter(|| {
                let r = &refs[i % refs.len()];
                i = i.wrapping_add(1);
                black_box(ctx.get_index(black_box(r)).unwrap())
            });
        });
    }
    group.finish();
}

fn bench_get_miss(c: &mut Criterion) {
    let mut group = c.benchmark_group("refs/get_miss");
    for n in [1_000usize, 10_000] {
        let ctx = build_ctx(n);
        group.throughput(Throughput::Elements(1));
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, _| {
            b.iter(|| black_box(ctx.get_index(black_box("img_zzzzzz"))));
        });
    }
    group.finish();
}

// ── Rendering scale-up ──────────────────────────────────────────────────

fn bench_render_tree(c: &mut Criterion) {
    let mut group = c.benchmark_group("refs/render_tree_insertion");
    for n in [100usize, 1_000, 10_000] {
        let ctx = build_ctx(n);
        group.throughput(Throughput::Elements(n as u64));
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, _| {
            b.iter(|| black_box(ctx.render_tree_insertion()));
        });
    }
    group.finish();
}

fn bench_render_tree_with_meta(c: &mut Criterion) {
    let ctx = build_ctx_with_metadata(1_000);
    let mut group = c.benchmark_group("refs/render_tree_insertion_with_meta");
    group.throughput(Throughput::Elements(1_000));
    group.bench_function("1000", |b| {
        b.iter(|| black_box(ctx.render_tree_insertion()));
    });
    group.finish();
}

fn bench_repr_markdown(c: &mut Criterion) {
    let mut group = c.benchmark_group("refs/repr_markdown");
    for n in [100usize, 1_000, 10_000] {
        let ctx = build_ctx(n);
        group.throughput(Throughput::Elements(n as u64));
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, _| {
            b.iter(|| black_box(ctx.to_repr_markdown()));
        });
    }
    group.finish();
}

fn bench_to_md_with_contents(c: &mut Criterion) {
    let ctx = build_ctx_with_metadata(1_000);
    // Half the items have extracted content, the other half fall back to
    // the `summary` metadata fallback path — exercises both branches of
    // the renderer.
    let mut contents: HashMap<String, String> = HashMap::new();
    for (idx, item) in ctx.items.iter().enumerate() {
        if idx % 2 == 0 {
            contents.insert(
                item.ref_id.to_string(),
                format!(
                    "# fast-path extract for {}\npara {}: lorem ipsum dolor sit amet consectetur",
                    item.ref_id, idx
                ),
            );
        }
    }
    let mut group = c.benchmark_group("refs/to_md_with_contents");
    group.throughput(Throughput::Elements(1_000));
    group.bench_function("1000", |b| {
        b.iter(|| black_box(ctx.to_md_with_contents(black_box(&contents))));
    });
    group.finish();
}

// ── RefNotFoundError message (Levenshtein across the context) ───────────

fn bench_ref_not_found_message(c: &mut Criterion) {
    let mut group = c.benchmark_group("refs/ref_not_found_message");
    for n in [100usize, 1_000, 10_000] {
        let ctx = build_ctx(n);
        // Take a real ref and perturb one character so the suggestion
        // actually kicks in — this is the realistic miss shape (typo).
        let real = ctx.items[n / 2].ref_id.to_string();
        let mut chars: Vec<char> = real.chars().collect();
        if let Some(last) = chars.last_mut() {
            *last = if *last == 'z' { 'a' } else { 'z' };
        }
        let typo: String = chars.into_iter().collect();
        group.throughput(Throughput::Elements(1));
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, _| {
            b.iter(|| black_box(ctx.ref_not_found_message(black_box(&typo))));
        });
    }
    group.finish();
}

// ── Realistic mixed workload: add + get + render ────────────────────────
//
// Simulates an agent that incrementally builds a context, reads items
// back, and occasionally renders the tree. This is the shape we actually
// care about when serving an agent-loop, not isolated micro-benches.

fn bench_mixed_workload(c: &mut Criterion) {
    let mut group = c.benchmark_group("refs/mixed_add_get_render");
    for n in [1_000usize, 10_000] {
        group.throughput(Throughput::Elements(n as u64));
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, &n| {
            b.iter(|| {
                let mut ctx = Context::new(uuid7());
                let mut last_ref: Option<CompactString> = None;
                for i in 0..n {
                    let kind = KINDS[i % KINDS.len()];
                    let ref_id = ctx.add(
                        PromptRole::User,
                        kind,
                        ItemSource::Path {
                            path: CompactString::from(format!("/x/{}", i)),
                        },
                        if i % 8 == 0 {
                            Some(vec![(
                                "note".into(),
                                MetaValue::Str(CompactString::from(format!("n{i}"))),
                            )])
                        } else {
                            None
                        },
                    );
                    // Realistically, agents read back ~every 4th item.
                    if i % 4 == 0 {
                        let _ = ctx.get_index(black_box(&ref_id));
                    }
                    // And render / repr a couple of times per session.
                    if i > 0 && i % (n / 4).max(1) == 0 {
                        black_box(ctx.to_repr_markdown());
                    }
                    last_ref = Some(ref_id);
                }
                black_box(last_ref);
                black_box(ctx.render_tree_insertion());
            });
        });
    }
    group.finish();
}

// ── Levenshtein stress (closest_ref is O(n) × levenshtein) ──────────────
//
// `closest_ref` is only called on a miss; budget it explicitly so we
// catch accidental algorithmic regressions (e.g. dropping the prefix
// filter).

fn bench_levenshtein_suggestion(c: &mut Criterion) {
    let ctx = build_ctx(10_000);
    // Build a 100% miss that still matches the `img_` prefix filter so
    // every single image ref must be scored.
    let target = "img_zzzzzz";
    c.bench_function("refs/closest_ref_10k", |b| {
        b.iter(|| black_box(ctx.ref_not_found_message(black_box(target))));
    });
}

criterion_group!(
    benches,
    bench_make_ref_id,
    bench_uuid7,
    bench_add_path,
    bench_add_inmem,
    bench_add_with_metadata,
    bench_get_hit,
    bench_get_miss,
    bench_render_tree,
    bench_render_tree_with_meta,
    bench_repr_markdown,
    bench_to_md_with_contents,
    bench_ref_not_found_message,
    bench_levenshtein_suggestion,
    bench_mixed_workload,
);
criterion_main!(benches);
