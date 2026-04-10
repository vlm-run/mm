use criterion::{BenchmarkId, Criterion, criterion_group, criterion_main};
use std::fs;
use tempfile::TempDir;

/// Create a mixed-kind test tree: code, text, config, data files + some images/videos stubs.
fn create_mixed_tree(dir: &std::path::Path, count: usize) {
    let specs: Vec<(&str, &[u8])> = vec![
        // code/text files with realistic content for line counting
        ("src/main.py", b"import os\nimport sys\n\ndef main():\n    print('hello')\n\nif __name__ == '__main__':\n    main()\n"),
        ("src/lib.rs", b"pub fn add(a: i32, b: i32) -> i32 {\n    a + b\n}\n\n#[cfg(test)]\nmod tests {\n    use super::*;\n    #[test]\n    fn it_works() {\n        assert_eq!(add(2, 2), 4);\n    }\n}\n"),
        ("config/settings.toml", b"[database]\nhost = \"localhost\"\nport = 5432\nname = \"mydb\"\n"),
        ("README.md", b"# Project\n\nA sample project for benchmarking.\n\n## Usage\n\nRun `cargo bench`.\n"),
        ("data/output.csv", b"id,name,value\n1,alpha,100\n2,beta,200\n3,gamma,300\n4,delta,400\n"),
    ];

    for i in 0..count {
        let (base_path, content) = &specs[i % specs.len()];
        // Deduplicate paths by appending index
        let path = if count > specs.len() {
            let ext_pos = base_path.rfind('.').unwrap_or(base_path.len());
            format!("{}_{}{}", &base_path[..ext_pos], i, &base_path[ext_pos..])
        } else {
            base_path.to_string()
        };
        let full = dir.join(&path);
        if let Some(parent) = full.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        // Scale content by repeating lines
        let repeated: Vec<u8> = content.repeat(1 + i % 10);
        fs::write(full, &repeated).unwrap();
    }
}

fn bench_wc(c: &mut Criterion) {
    let mut group = c.benchmark_group("wc");

    for size in [100, 500] {
        let dir = TempDir::new().unwrap();
        create_mixed_tree(dir.path(), size);
        let entries = mm_core::scan_directory(dir.path(), None);
        let refs: Vec<&mm_core::FileEntry> = entries.iter().collect();

        // count_entries: parallel file reads + line/token counting
        group.bench_with_input(BenchmarkId::new("count_entries", size), &refs, |b, refs| {
            b.iter(|| {
                let result = mm_core::wc::count_entries(refs, dir.path());
                assert!(result.files > 0);
                assert!(result.lines > 0);
            });
        });

        // count_entries + JSON serialization (full pipeline)
        group.bench_with_input(
            BenchmarkId::new("count_and_serialize", size),
            &refs,
            |b, refs| {
                b.iter(|| {
                    let result = mm_core::wc::count_entries(refs, dir.path());
                    let json = mm_core::wc::wc_to_json(&result);
                    assert!(!json.is_empty());
                });
            },
        );
    }

    group.finish();
}

criterion_group!(benches, bench_wc);
criterion_main!(benches);
