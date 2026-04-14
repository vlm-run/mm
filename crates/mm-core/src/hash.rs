use std::fs::File;
use std::io::{Cursor, Read};
use std::path::Path;

const PARTIAL_BLOCK: usize = 64 * 1024; // 64 KB
const PHASH_SIZE: u32 = 32; // Resize to 32x32 before DCT
const DCT_LOW: usize = 8; // Use top-left 8x8 DCT coefficients → 64-bit hash

/// Fast content fingerprint: hash first 64KB + last 64KB + file size.
/// For files <= 128KB, hashes the entire content.
/// ~500x faster than full-file hash on large files (0.2ms vs 100ms for 206MB).
pub fn fast_fingerprint(path: &Path, size: u64) -> Option<u64> {
    let file = File::open(path).ok()?;

    if size <= (PARTIAL_BLOCK * 2) as u64 {
        // Small file: mmap and hash the whole thing
        let mmap = unsafe { memmap2::Mmap::map(&file) }.ok()?;
        return Some(xxhash_rust::xxh3::xxh3_64(&mmap));
    }

    // Large file: read head + tail blocks, mix in size
    let mmap = unsafe { memmap2::Mmap::map(&file) }.ok()?;
    let head = &mmap[..PARTIAL_BLOCK];
    let tail = &mmap[mmap.len() - PARTIAL_BLOCK..];

    let mut hasher = xxhash_rust::xxh3::Xxh3::new();
    hasher.update(head);
    hasher.update(tail);
    hasher.update(&size.to_le_bytes());
    Some(hasher.digest())
}

/// Full-content xxh3 hash via mmap. Zero-copy, no heap allocation for file data.
pub fn full_hash_mmap(path: &Path) -> Option<u64> {
    let file = File::open(path).ok()?;
    let mmap = unsafe { memmap2::Mmap::map(&file) }.ok()?;
    Some(xxhash_rust::xxh3::xxh3_64(&mmap))
}

/// Full-content xxh3 hash via streaming read (fallback for special files).
pub fn full_hash_read(path: &Path) -> Option<u64> {
    let mut file = File::open(path).ok()?;
    let mut buf = Vec::new();
    file.read_to_end(&mut buf).ok()?;
    Some(xxhash_rust::xxh3::xxh3_64(&buf))
}

/// Hash a directory listing: sorted(name:mtime_ns:size) for each entry.
/// Deterministic — same files with same mtimes produce the same hash.
/// Uses gitignore-aware walking (same as scan_directory).
pub fn directory_hash(path: &Path) -> Option<u64> {
    use ignore::WalkBuilder;

    let mut entries: Vec<String> = Vec::new();
    let walker = WalkBuilder::new(path)
        .hidden(true)
        .git_ignore(true)
        .git_global(true)
        .git_exclude(true)
        .build();

    for entry in walker.flatten() {
        if !entry.file_type().is_some_and(|ft| ft.is_file()) {
            continue;
        }
        let Ok(meta) = entry.metadata() else {
            continue;
        };
        let name = entry.path().to_string_lossy();
        let size = meta.len();
        let mtime = meta
            .modified()
            .ok()
            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
            .map_or(0, |d| d.as_nanos());
        entries.push(format!("{name}:{mtime}:{size}"));
    }

    entries.sort();
    let mut hasher = xxhash_rust::xxh3::Xxh3::new();
    for e in &entries {
        hasher.update(e.as_bytes());
    }
    Some(hasher.digest())
}

/// Perceptual hash (pHash) of an image file.
/// Produces a 64-bit hash invariant to resize and mild compression.
/// Algorithm: resize to 32x32 grayscale → 2D DCT (via rustdct) → top-left 8x8 → median threshold.
pub fn phash(data: &[u8]) -> Option<u64> {
    use rustdct::DctPlanner;

    let img = image::ImageReader::new(Cursor::new(data))
        .with_guessed_format()
        .ok()?
        .decode()
        .ok()?;

    let n = PHASH_SIZE as usize;

    // Resize to 32x32 and convert to grayscale
    let gray = img
        .resize_exact(
            PHASH_SIZE,
            PHASH_SIZE,
            image::imageops::FilterType::Lanczos3,
        )
        .to_luma8();

    // Flatten to row-major f64 matrix
    let mut matrix: Vec<f64> = gray.pixels().map(|p| p.0[0] as f64).collect();

    // 2D DCT via rustdct: DCT-II on rows, then on columns
    let mut planner = DctPlanner::new();
    let dct = planner.plan_dct2(n);
    let mut scratch = vec![0.0f64; dct.get_scratch_len()];

    // DCT on each row
    for row in matrix.chunks_exact_mut(n) {
        dct.process_dct2_with_scratch(row, &mut scratch);
    }

    // Transpose and DCT on columns
    let mut transposed = vec![0.0f64; n * n];
    for r in 0..n {
        for c in 0..n {
            transposed[c * n + r] = matrix[r * n + c];
        }
    }
    for row in transposed.chunks_exact_mut(n) {
        dct.process_dct2_with_scratch(row, &mut scratch);
    }

    // Extract top-left 8x8 coefficients directly from transposed layout
    let mut coeffs = Vec::with_capacity(DCT_LOW * DCT_LOW);
    for v in 0..DCT_LOW {
        for u in 0..DCT_LOW {
            coeffs.push(transposed[u * n + v]);
        }
    }

    // Median of AC coefficients only (skip DC at index 0)
    let mut ac_sorted: Vec<f64> = coeffs[1..].to_vec();
    ac_sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let median = ac_sorted[ac_sorted.len() / 2];

    // Threshold all 64 coefficients against AC median → true 64-bit hash
    let mut hash: u64 = 0;
    for (i, &c) in coeffs.iter().enumerate() {
        if c > median {
            hash |= 1 << i;
        }
    }

    Some(hash)
}

/// Hamming distance between two perceptual hashes.
/// Returns the number of differing bits (0 = identical, <8 = near-duplicate).
pub fn hamming_distance(a: u64, b: u64) -> u32 {
    (a ^ b).count_ones()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    #[test]
    fn test_fast_fingerprint_small_file() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("small.txt");
        fs::write(&path, "hello world").unwrap();
        let fp = fast_fingerprint(&path, 11);
        assert!(fp.is_some());
        // Small files get full hash, should match full_hash_mmap
        assert_eq!(fp, full_hash_mmap(&path));
    }

    #[test]
    fn test_fast_fingerprint_deterministic() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("det.txt");
        fs::write(&path, "deterministic content").unwrap();
        let size = fs::metadata(&path).unwrap().len();
        let a = fast_fingerprint(&path, size);
        let b = fast_fingerprint(&path, size);
        assert_eq!(a, b);
    }

    #[test]
    fn test_full_hash_mmap_matches_read() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("match.txt");
        fs::write(&path, "compare mmap vs read").unwrap();
        assert_eq!(full_hash_mmap(&path), full_hash_read(&path));
    }

    #[test]
    fn test_nonexistent_file() {
        assert!(fast_fingerprint(Path::new("/nonexistent"), 0).is_none());
        assert!(full_hash_mmap(Path::new("/nonexistent")).is_none());
        assert!(full_hash_read(Path::new("/nonexistent")).is_none());
    }

    #[test]
    fn test_phash_deterministic() {
        let img = image::RgbImage::from_fn(100, 100, |x, y| {
            image::Rgb([(x * 2 + y) as u8, (x + y * 3) as u8, (x ^ y) as u8])
        });
        let mut buf = Vec::new();
        img.write_to(&mut Cursor::new(&mut buf), image::ImageFormat::Png)
            .unwrap();
        let h1 = phash(&buf).unwrap();
        let h2 = phash(&buf).unwrap();
        assert_eq!(h1, h2);
    }

    #[test]
    fn test_phash_similar_after_resize() {
        // Create a 400x400 image with a complex pattern (checkerboard + gradient)
        let img = image::RgbImage::from_fn(400, 400, |x, y| {
            let checker = if (x / 40 + y / 40) % 2 == 0 {
                200u8
            } else {
                50u8
            };
            let gx = (x * 255 / 400) as u8;
            let gy = (y * 255 / 400) as u8;
            image::Rgb([checker, gx, gy])
        });

        let mut buf_large = Vec::new();
        img.write_to(&mut Cursor::new(&mut buf_large), image::ImageFormat::Png)
            .unwrap();

        // Resize to 100x100 (4x downscale — typical real-world scenario)
        let small = image::DynamicImage::ImageRgb8(img).resize_exact(
            100,
            100,
            image::imageops::FilterType::Lanczos3,
        );
        let mut buf_small = Vec::new();
        small
            .write_to(&mut Cursor::new(&mut buf_small), image::ImageFormat::Png)
            .unwrap();

        let h_large = phash(&buf_large).unwrap();
        let h_small = phash(&buf_small).unwrap();
        let dist = hamming_distance(h_large, h_small);
        // Resized version should be perceptually similar (distance < 10)
        assert!(dist < 10, "Expected similar hashes, got distance {dist}");
    }

    #[test]
    fn test_phash_different_images() {
        // Bright image
        let img1 = image::RgbImage::from_pixel(100, 100, image::Rgb([255, 255, 255]));
        let mut buf1 = Vec::new();
        img1.write_to(&mut Cursor::new(&mut buf1), image::ImageFormat::Png)
            .unwrap();

        // Dark image with pattern
        let img2 = image::RgbImage::from_fn(100, 100, |x, y| {
            image::Rgb([((x * 7 + y * 13) % 256) as u8, 0, 0])
        });
        let mut buf2 = Vec::new();
        img2.write_to(&mut Cursor::new(&mut buf2), image::ImageFormat::Png)
            .unwrap();

        let h1 = phash(&buf1).unwrap();
        let h2 = phash(&buf2).unwrap();
        let dist = hamming_distance(h1, h2);
        assert!(dist > 8, "Expected different hashes, got distance {dist}");
    }

    #[test]
    fn test_hamming_distance() {
        assert_eq!(hamming_distance(0, 0), 0);
        assert_eq!(hamming_distance(0xFF, 0x00), 8);
        assert_eq!(hamming_distance(0b1010, 0b0101), 4);
        assert_eq!(hamming_distance(u64::MAX, 0), 64);
    }

    #[test]
    fn test_large_file_partial_vs_full() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("large.bin");
        let data: Vec<u8> = (0..200_000u32).flat_map(|i| i.to_le_bytes()).collect();
        fs::write(&path, &data).unwrap();
        let size = data.len() as u64;

        let partial = fast_fingerprint(&path, size);
        let full = full_hash_mmap(&path);
        assert!(partial.is_some());
        assert!(full.is_some());
        // Partial and full should differ for large files
        assert_ne!(partial, full);
    }
}
