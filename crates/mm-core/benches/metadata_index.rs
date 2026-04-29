use criterion::{BenchmarkId, Criterion, criterion_group, criterion_main};
use std::fs;
use tempfile::TempDir;

fn create_test_tree(dir: &std::path::Path, count: usize) {
    let extensions = [
        ".py", ".rs", ".js", ".md", ".toml", ".json", ".txt", ".yaml",
    ];
    for i in 0..count {
        let depth = i % 5;
        let mut path = dir.to_path_buf();
        for d in 0..depth {
            path = path.join(format!("dir_{}", d));
        }
        fs::create_dir_all(&path).unwrap();
        let ext = extensions[i % extensions.len()];
        fs::write(
            path.join(format!("file_{}{}", i, ext)),
            format!("content {}", i),
        )
        .unwrap();
    }
}

fn bench_metadata_full_pipeline(c: &mut Criterion) {
    let mut group = c.benchmark_group("metadata_index");

    for size in [1_000, 10_000] {
        let dir = TempDir::new().unwrap();
        create_test_tree(dir.path(), size);

        group.bench_with_input(BenchmarkId::from_parameter(size), &size, |b, _| {
            b.iter(|| {
                let entries = mm_core::scan_directory(dir.path(), None, false);
                let batch = mm_core::build_metadata_batch(&entries).unwrap();
                assert!(batch.num_rows() > 0);
            });
        });
    }

    group.finish();
}

criterion_group!(benches, bench_metadata_full_pipeline);
criterion_main!(benches);
