use criterion::{BenchmarkId, Criterion, criterion_group, criterion_main};
use std::fs;
use tempfile::TempDir;
use mm_core::extract::ContentExtractor;
use mm_core::extractors::{CodeExtractor, ImageExtractor};

fn create_code_tree(dir: &std::path::Path, count: usize) {
    for i in 0..count {
        let content = format!(
            "// File {i}\nfn func_{i}() {{\n    let x = {i};\n    println!(\"{{x}}\");\n}}\n"
        );
        fs::write(dir.join(format!("file_{i}.rs")), content).unwrap();
    }
}

fn create_image_tree(dir: &std::path::Path, count: usize) {
    for i in 0..count {
        let w = 100 + (i as u32 % 200);
        let h = 80 + (i as u32 % 150);
        let img = image::RgbImage::new(w, h);
        img.save(dir.join(format!("img_{i}.png"))).unwrap();
    }
}

fn bench_l1_code(c: &mut Criterion) {
    let mut group = c.benchmark_group("l1_code_extract");

    for count in [10, 100] {
        let dir = TempDir::new().unwrap();
        create_code_tree(dir.path(), count);

        let paths: Vec<_> = (0..count)
            .map(|i| dir.path().join(format!("file_{i}.rs")))
            .collect();

        group.bench_with_input(BenchmarkId::from_parameter(count), &paths, |b, paths| {
            b.iter(|| {
                let extractor = CodeExtractor;
                for path in paths {
                    let _ = extractor.extract(path);
                }
            });
        });
    }

    group.finish();
}

fn bench_l1_image(c: &mut Criterion) {
    let mut group = c.benchmark_group("l1_image_extract");

    for count in [10, 50] {
        let dir = TempDir::new().unwrap();
        create_image_tree(dir.path(), count);

        let paths: Vec<_> = (0..count)
            .map(|i| dir.path().join(format!("img_{i}.png")))
            .collect();

        group.bench_with_input(BenchmarkId::from_parameter(count), &paths, |b, paths| {
            b.iter(|| {
                let extractor = ImageExtractor;
                for path in paths {
                    let _ = extractor.extract(path);
                }
            });
        });
    }

    group.finish();
}

criterion_group!(benches, bench_l1_code, bench_l1_image);
criterion_main!(benches);
