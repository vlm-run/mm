use criterion::{BenchmarkId, Criterion, criterion_group, criterion_main};
use std::fs;
use tempfile::TempDir;

fn create_test_tree(dir: &std::path::Path, count: usize) {
    let extensions = [
        ".py", ".rs", ".js", ".md", ".toml", ".json", ".txt", ".yaml",
    ];
    let prefixes = ["test_", "main_", "config_", "util_", "README", "setup_", "lib_", "mod_"];
    for i in 0..count {
        let depth = i % 5;
        let mut path = dir.to_path_buf();
        for d in 0..depth {
            path = path.join(format!("dir_{}", d));
        }
        fs::create_dir_all(&path).unwrap();
        let ext = extensions[i % extensions.len()];
        let prefix = prefixes[i % prefixes.len()];
        let filename = format!("{}{}{}", prefix, i, ext);
        fs::write(path.join(filename), format!("content {}", i)).unwrap();
    }
}

fn bench_find_filter(c: &mut Criterion) {
    let mut group = c.benchmark_group("find_filter");

    for size in [1_000, 10_000] {
        let dir = TempDir::new().unwrap();
        create_test_tree(dir.path(), size);
        let entries = mm_core::scan_directory(dir.path(), None);

        // Baseline: no filters
        group.bench_with_input(
            BenchmarkId::new("no_filter", size),
            &entries,
            |b, entries| {
                b.iter(|| {
                    let json = mm_core::entries_to_json_filtered(
                        entries, None, None, None, None, None, None, None, false,
                    );
                    assert!(!json.is_empty());
                });
            },
        );

        // Substring match (non-regex)
        group.bench_with_input(
            BenchmarkId::new("name_substring", size),
            &entries,
            |b, entries| {
                b.iter(|| {
                    let json = mm_core::entries_to_json_filtered(
                        entries,
                        None,
                        None,
                        None,
                        None,
                        Some("test_"),
                        None,
                        None,
                        false,
                    );
                    assert!(!json.is_empty());
                });
            },
        );

        // Regex match
        group.bench_with_input(
            BenchmarkId::new("name_regex", size),
            &entries,
            |b, entries| {
                b.iter(|| {
                    let json = mm_core::entries_to_json_filtered(
                        entries,
                        None,
                        None,
                        None,
                        None,
                        Some(r"test_\d+\.py$"),
                        None,
                        None,
                        false,
                    );
                    assert!(!json.is_empty());
                });
            },
        );

        // Combined: kind + name
        group.bench_with_input(
            BenchmarkId::new("kind_and_name", size),
            &entries,
            |b, entries| {
                b.iter(|| {
                    let json = mm_core::entries_to_json_filtered(
                        entries,
                        Some("code"),
                        None,
                        None,
                        None,
                        Some("config"),
                        None,
                        None,
                        false,
                    );
                    assert!(!json.is_empty());
                });
            },
        );
    }

    group.finish();
}

criterion_group!(benches, bench_find_filter);
criterion_main!(benches);
