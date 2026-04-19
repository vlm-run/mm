use criterion::{BenchmarkId, Criterion, criterion_group, criterion_main};
use std::fs;
use std::io::Cursor;
use tempfile::TempDir;

/// Benchmark directory_hash on directories of varying sizes.
fn bench_directory_hash(c: &mut Criterion) {
    let mut group = c.benchmark_group("directory_hash");
    // 1000-file directory_hash takes ~18ms/iter; need headroom for 100 samples
    group.measurement_time(std::time::Duration::from_secs(10));

    let sizes: Vec<(&str, usize)> =
        vec![("100_files", 100), ("500_files", 500), ("1000_files", 1000)];

    for (label, count) in &sizes {
        let dir = TempDir::new().unwrap();
        // Create nested structure
        for i in 0..*count {
            let subdir = dir.path().join(format!("d{}", i % 10));
            fs::create_dir_all(&subdir).unwrap();
            let data: Vec<u8> = (0..((i % 50 + 1) * 1024))
                .map(|j| ((i + j) % 256) as u8)
                .collect();
            fs::write(subdir.join(format!("file_{i}.bin")), &data).unwrap();
        }

        group.bench_with_input(
            BenchmarkId::new("directory_hash", label),
            dir.path(),
            |b, path| {
                b.iter(|| mm_core::directory_hash(path));
            },
        );
    }

    group.finish();
}

/// Benchmark phash on synthetic images of varying sizes.
fn bench_phash(c: &mut Criterion) {
    let mut group = c.benchmark_group("phash");
    // 2048x2048 takes ~300ms/iter; need enough time for 100 samples
    group.measurement_time(std::time::Duration::from_secs(30));

    let sizes: Vec<(&str, u32)> = vec![
        ("64x64", 64),
        ("256x256", 256),
        ("1024x1024", 1024),
        ("2048x2048", 2048),
    ];

    for (label, dim) in &sizes {
        // Generate a synthetic image with a complex pattern
        let img = image::RgbImage::from_fn(*dim, *dim, |x, y| {
            image::Rgb([
                ((x * 7 + y * 13) % 256) as u8,
                ((x * 3 + y * 11) % 256) as u8,
                ((x * 5 + y * 17) % 256) as u8,
            ])
        });
        let mut buf = Vec::new();
        img.write_to(&mut Cursor::new(&mut buf), image::ImageFormat::Png)
            .unwrap();

        group.bench_with_input(BenchmarkId::new("phash", label), &buf, |b, data| {
            b.iter(|| mm_core::phash(data));
        });
    }

    // Also benchmark hamming_distance (should be trivial but included for completeness)
    group.bench_function("hamming_distance", |b| {
        let h1: u64 = 0xDEADBEEFCAFE1234;
        let h2: u64 = 0xDEADBEEFCAFE5678;
        b.iter(|| mm_core::hamming_distance(h1, h2));
    });

    group.finish();
}

/// Benchmark content hashing on large files (100MB+).
fn bench_hash_large_files(c: &mut Criterion) {
    let mut group = c.benchmark_group("hash_large_files");
    group.sample_size(10);
    // full_hash_mmap on 200MB takes ~160ms; need enough time for 10 samples
    group.measurement_time(std::time::Duration::from_secs(10));

    let dir = TempDir::new().unwrap();

    let sizes: Vec<(&str, usize)> = vec![
        ("50MB", 50 * 1024 * 1024),
        ("100MB", 100 * 1024 * 1024),
        ("200MB", 200 * 1024 * 1024),
    ];

    for (label, size) in &sizes {
        let path = dir.path().join(format!("large_{label}.bin"));
        // Write random-ish data
        let data: Vec<u8> = (0..*size).map(|i| (i % 251) as u8).collect();
        fs::write(&path, &data).unwrap();

        group.bench_with_input(
            BenchmarkId::new("fast_fingerprint", label),
            &(&path, *size as u64),
            |b, (path, sz)| {
                b.iter(|| mm_core::fast_fingerprint(path, *sz));
            },
        );

        group.bench_with_input(
            BenchmarkId::new("full_hash_mmap", label),
            &path,
            |b, path| {
                b.iter(|| mm_core::full_hash_mmap(path));
            },
        );
    }

    group.finish();
}

criterion_group!(
    benches,
    bench_directory_hash,
    bench_phash,
    bench_hash_large_files
);
criterion_main!(benches);
