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

/// Perceptual hash (pHash) of an image file.
/// Produces a 64-bit hash invariant to resize and mild compression.
/// Algorithm: resize to 32x32 grayscale → DCT → top-left 8x8 → median threshold.
#[allow(clippy::needless_range_loop)]
pub fn phash(data: &[u8]) -> Option<u64> {
    let img = image::ImageReader::new(Cursor::new(data))
        .with_guessed_format()
        .ok()?
        .decode()
        .ok()?;

    // Resize to 32x32 and convert to grayscale
    let gray = img
        .resize_exact(PHASH_SIZE, PHASH_SIZE, image::imageops::FilterType::Lanczos3)
        .to_luma8();

    // Convert to f64 matrix
    let mut pixels = [[0.0f64; PHASH_SIZE as usize]; PHASH_SIZE as usize];
    for y in 0..PHASH_SIZE as usize {
        for x in 0..PHASH_SIZE as usize {
            pixels[y][x] = gray.get_pixel(x as u32, y as u32).0[0] as f64;
        }
    }

    // Apply 2D DCT (rows then columns)
    let mut dct = [[0.0f64; PHASH_SIZE as usize]; PHASH_SIZE as usize];

    // DCT on rows
    for y in 0..PHASH_SIZE as usize {
        for u in 0..PHASH_SIZE as usize {
            let mut sum = 0.0;
            for x in 0..PHASH_SIZE as usize {
                sum += pixels[y][x]
                    * ((std::f64::consts::PI * (2.0 * x as f64 + 1.0) * u as f64)
                        / (2.0 * PHASH_SIZE as f64))
                        .cos();
            }
            dct[y][u] = sum;
        }
    }

    // DCT on columns (in-place, only need first DCT_LOW columns)
    let mut dct2 = [[0.0f64; PHASH_SIZE as usize]; PHASH_SIZE as usize];
    for x in 0..DCT_LOW {
        for v in 0..PHASH_SIZE as usize {
            let mut sum = 0.0;
            for y in 0..PHASH_SIZE as usize {
                sum += dct[y][x]
                    * ((std::f64::consts::PI * (2.0 * y as f64 + 1.0) * v as f64)
                        / (2.0 * PHASH_SIZE as f64))
                        .cos();
            }
            dct2[v][x] = sum;
        }
    }

    // Extract top-left 8x8 (excluding DC component at [0][0])
    let mut coeffs = Vec::with_capacity(DCT_LOW * DCT_LOW - 1);
    for v in 0..DCT_LOW {
        for u in 0..DCT_LOW {
            if v == 0 && u == 0 {
                continue; // skip DC
            }
            coeffs.push(dct2[v][u]);
        }
    }

    // Median threshold → 64-bit hash
    let mut sorted = coeffs.clone();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let median = sorted[sorted.len() / 2];

    let mut hash: u64 = 0;
    for (i, &c) in coeffs.iter().take(64).enumerate() {
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
            let checker = if (x / 40 + y / 40) % 2 == 0 { 200u8 } else { 50u8 };
            let gx = (x * 255 / 400) as u8;
            let gy = (y * 255 / 400) as u8;
            image::Rgb([checker, gx, gy])
        });

        let mut buf_large = Vec::new();
        img.write_to(&mut Cursor::new(&mut buf_large), image::ImageFormat::Png)
            .unwrap();

        // Resize to 100x100 (4x downscale — typical real-world scenario)
        let small = image::DynamicImage::ImageRgb8(img)
            .resize_exact(100, 100, image::imageops::FilterType::Lanczos3);
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
