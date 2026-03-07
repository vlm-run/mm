use criterion::{BenchmarkId, Criterion, criterion_group, criterion_main};
use std::fs;
use tempfile::TempDir;

fn bench_hash_strategies(c: &mut Criterion) {
    let mut group = c.benchmark_group("hash_strategies");

    let dir = TempDir::new().unwrap();

    // Create files of different sizes
    let sizes: Vec<(&str, usize)> = vec![
        ("1KB", 1024),
        ("64KB", 64 * 1024),
        ("1MB", 1024 * 1024),
        ("10MB", 10 * 1024 * 1024),
    ];

    for (label, size) in &sizes {
        let path = dir.path().join(format!("file_{label}.bin"));
        let data: Vec<u8> = (0..*size).map(|i| (i % 256) as u8).collect();
        fs::write(&path, &data).unwrap();

        group.bench_with_input(
            BenchmarkId::new("fast_fingerprint", label),
            &path,
            |b, path| {
                b.iter(|| vlmctx_core::fast_fingerprint(path, *size as u64));
            },
        );

        group.bench_with_input(
            BenchmarkId::new("full_hash_mmap", label),
            &path,
            |b, path| {
                b.iter(|| vlmctx_core::full_hash_mmap(path));
            },
        );

        group.bench_with_input(
            BenchmarkId::new("full_hash_read", label),
            &path,
            |b, path| {
                b.iter(|| vlmctx_core::hash::full_hash_read(path));
            },
        );
    }

    group.finish();
}

criterion_group!(benches, bench_hash_strategies);
criterion_main!(benches);
