use std::fs::File;
use std::io::Read;
use std::path::Path;

const PARTIAL_BLOCK: usize = 64 * 1024; // 64 KB

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
