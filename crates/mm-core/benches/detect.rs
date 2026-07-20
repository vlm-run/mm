use criterion::{criterion_group, criterion_main, Criterion};
use std::path::Path;

use mm_core::detect::kind_from_extension;
use mm_core::meta::FileKind;

fn kind_from_path_lossy(path: &Path) -> FileKind {
    path.extension()
        .map(|e| kind_from_extension(&e.to_string_lossy()))
        .unwrap_or(FileKind::Other)
}

fn kind_from_path_to_str(path: &Path) -> FileKind {
    path.extension()
        .and_then(|e| e.to_str())
        .map(kind_from_extension)
        .unwrap_or(FileKind::Other)
}

fn bench_kind_from_path(c: &mut Criterion) {
    let paths: Vec<std::path::PathBuf> = [
        "src/main.py",
        "crates/mm-core/src/lib.rs",
        "docs/readme.md",
        "config/settings.toml",
        "data/records.json",
        "images/photo.png",
        "video/clip.mp4",
        "audio/track.mp3",
        "docs/paper.pdf",
        "no_extension_file",
    ]
    .iter()
    .map(std::path::PathBuf::from)
    .collect();

    let mut group = c.benchmark_group("kind_from_path");

    group.bench_function("to_string_lossy", |b| {
        b.iter(|| {
            let mut last = FileKind::Other;
            for p in &paths {
                last = kind_from_path_lossy(p);
            }
            last
        })
    });

    group.bench_function("to_str", |b| {
        b.iter(|| {
            let mut last = FileKind::Other;
            for p in &paths {
                last = kind_from_path_to_str(p);
            }
            last
        })
    });

    group.bench_function("current (kind_from_path)", |b| {
        b.iter(|| {
            let mut last = FileKind::Other;
            for p in &paths {
                last = kind_from_path_lossy(p);
            }
            last
        })
    });

    group.finish();
}

criterion_group!(benches, bench_kind_from_path);
criterion_main!(benches);
