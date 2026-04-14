use compact_str::CompactString;
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::fmt;
use std::fs::Metadata;
use std::path::Path;
use std::time::SystemTime;

use crate::detect::{is_binary_extension, kind_from_extension, mime_from_extension};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum FileKind {
    Code,
    Image,
    Document,
    Video,
    Audio,
    Data,
    Config,
    Text,
    Other,
}

impl fmt::Display for FileKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            FileKind::Code => write!(f, "code"),
            FileKind::Image => write!(f, "image"),
            FileKind::Document => write!(f, "document"),
            FileKind::Video => write!(f, "video"),
            FileKind::Audio => write!(f, "audio"),
            FileKind::Data => write!(f, "data"),
            FileKind::Config => write!(f, "config"),
            FileKind::Text => write!(f, "text"),
            FileKind::Other => write!(f, "other"),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct FileEntry {
    pub path: CompactString,
    pub name: CompactString,
    pub stem: CompactString,
    pub ext: CompactString,
    pub size: u64,
    pub modified_epoch_us: i64,
    pub created_epoch_us: i64,
    pub mime: CompactString,
    pub kind: FileKind,
    pub is_binary: bool,
    pub depth: u16,
    pub parent: CompactString,
    pub width: Option<u32>,
    pub height: Option<u32>,
}

fn system_time_to_epoch_us(t: std::io::Result<SystemTime>) -> i64 {
    t.ok()
        .and_then(|t| t.duration_since(SystemTime::UNIX_EPOCH).ok())
        .map(|d| d.as_micros() as i64)
        .unwrap_or(0)
}

impl FileEntry {
    pub fn from_path(path: &Path, root: &Path, metadata: &Metadata) -> Self {
        let rel = path.strip_prefix(root).unwrap_or(path);
        let rel_str = rel.to_string_lossy();

        let name = path
            .file_name()
            .map(|n| n.to_string_lossy())
            .unwrap_or_default();

        let stem = path
            .file_stem()
            .map(|s| s.to_string_lossy())
            .unwrap_or_default();

        let ext = path
            .extension()
            .map(|e| format!(".{}", e.to_string_lossy()))
            .unwrap_or_default();

        let parent = rel
            .parent()
            .map(|p| p.to_string_lossy().to_string())
            .unwrap_or_default();

        let depth = rel.components().count().saturating_sub(1) as u16;
        let kind = kind_from_extension(&ext);
        let mime = mime_from_extension(&ext);
        let is_binary = is_binary_extension(&ext);

        FileEntry {
            path: CompactString::from(rel_str.as_ref()),
            name: CompactString::from(name.as_ref()),
            stem: CompactString::from(stem.as_ref()),
            ext: CompactString::from(ext.as_str()),
            size: metadata.len(),
            modified_epoch_us: system_time_to_epoch_us(metadata.modified()),
            created_epoch_us: system_time_to_epoch_us(metadata.created()),
            mime: CompactString::from(mime.as_str()),
            kind,
            is_binary,
            depth,
            parent: CompactString::from(parent.as_str()),
            width: None,
            height: None,
        }
    }
}

/// Parallel enrichment pass: reads image file headers to populate width/height.
/// Only touches Image entries; other kinds are skipped. Operates in-place.
pub fn enrich_image_dimensions(entries: &mut [FileEntry], root: &Path) {
    entries
        .par_iter_mut()
        .filter(|e| e.kind == FileKind::Image)
        .for_each(|entry| {
            let full_path = root.join(entry.path.as_str());
            if let Ok(reader) = image::ImageReader::open(&full_path)
                && let Ok((w, h)) = reader.into_dimensions()
            {
                entry.width = Some(w);
                entry.height = Some(h);
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::walk::scan_directory;
    use std::fs;
    use tempfile::TempDir;

    fn create_png(path: &std::path::Path, w: u32, h: u32) {
        let img = image::RgbImage::new(w, h);
        img.save(path).unwrap();
    }

    #[test]
    fn test_file_entry_defaults() {
        let dir = TempDir::new().unwrap();
        fs::write(dir.path().join("test.py"), "x = 1").unwrap();
        let entries = scan_directory(dir.path(), None, false);
        assert_eq!(entries.len(), 1);
        assert!(entries[0].width.is_none());
        assert!(entries[0].height.is_none());
    }

    #[test]
    fn test_enrich_populates_images() {
        let dir = TempDir::new().unwrap();
        create_png(&dir.path().join("a.png"), 100, 50);
        create_png(&dir.path().join("b.png"), 200, 150);
        fs::write(dir.path().join("c.py"), "x = 1").unwrap();

        let mut entries = scan_directory(dir.path(), None, false);
        enrich_image_dimensions(&mut entries, dir.path());

        let img_a = entries.iter().find(|e| e.name.as_str() == "a.png").unwrap();
        assert_eq!(img_a.width, Some(100));
        assert_eq!(img_a.height, Some(50));

        let img_b = entries.iter().find(|e| e.name.as_str() == "b.png").unwrap();
        assert_eq!(img_b.width, Some(200));
        assert_eq!(img_b.height, Some(150));

        let code = entries.iter().find(|e| e.name.as_str() == "c.py").unwrap();
        assert!(code.width.is_none());
        assert!(code.height.is_none());
    }

    #[test]
    fn test_enrich_handles_corrupt_image() {
        let dir = TempDir::new().unwrap();
        fs::write(dir.path().join("bad.png"), b"not a real png").unwrap();

        let mut entries = scan_directory(dir.path(), None, false);
        enrich_image_dimensions(&mut entries, dir.path());

        let bad = entries
            .iter()
            .find(|e| e.name.as_str() == "bad.png")
            .unwrap();
        assert!(bad.width.is_none());
        assert!(bad.height.is_none());
    }

    #[test]
    fn test_enrich_skips_video_kind() {
        let dir = TempDir::new().unwrap();
        fs::write(dir.path().join("clip.mp4"), b"\x00\x00").unwrap();

        let mut entries = scan_directory(dir.path(), None, false);
        enrich_image_dimensions(&mut entries, dir.path());

        let video = entries
            .iter()
            .find(|e| e.name.as_str() == "clip.mp4")
            .unwrap();
        assert_eq!(video.kind, FileKind::Video);
        assert!(video.width.is_none());
    }

    #[test]
    fn test_enrich_nested_images() {
        let dir = TempDir::new().unwrap();
        let sub = dir.path().join("sub");
        fs::create_dir(&sub).unwrap();
        create_png(&sub.join("deep.png"), 64, 32);

        let mut entries = scan_directory(dir.path(), None, false);
        enrich_image_dimensions(&mut entries, dir.path());

        let deep = entries
            .iter()
            .find(|e| e.name.as_str() == "deep.png")
            .unwrap();
        assert_eq!(deep.width, Some(64));
        assert_eq!(deep.height, Some(32));
    }

    #[test]
    fn test_file_kind_variants() {
        let dir = TempDir::new().unwrap();
        fs::write(dir.path().join("a.py"), "").unwrap();
        fs::write(dir.path().join("b.png"), b"").unwrap();
        fs::write(dir.path().join("c.mp4"), b"").unwrap();
        fs::write(dir.path().join("d.mp3"), b"").unwrap();
        fs::write(dir.path().join("e.csv"), "").unwrap();
        fs::write(dir.path().join("f.toml"), "").unwrap();
        fs::write(dir.path().join("g.md"), "").unwrap();
        fs::write(dir.path().join("h.pdf"), b"").unwrap();

        let entries = scan_directory(dir.path(), None, false);
        let kinds: Vec<FileKind> = entries.iter().map(|e| e.kind).collect();
        assert!(kinds.contains(&FileKind::Code));
        assert!(kinds.contains(&FileKind::Image));
        assert!(kinds.contains(&FileKind::Video));
        assert!(kinds.contains(&FileKind::Audio));
        assert!(kinds.contains(&FileKind::Data));
        assert!(kinds.contains(&FileKind::Config));
        assert!(kinds.contains(&FileKind::Text));
        assert!(kinds.contains(&FileKind::Document));
    }

    #[test]
    fn test_timestamps_nonzero() {
        let dir = TempDir::new().unwrap();
        fs::write(dir.path().join("test.py"), "x = 1").unwrap();
        let entries = scan_directory(dir.path(), None, false);
        assert!(entries[0].modified_epoch_us > 0);
        // created_epoch_us (birth time) is not available on all
        // filesystems / kernels (e.g. ext4 without statx), so we
        // only assert it is non-negative rather than strictly positive.
        assert!(entries[0].created_epoch_us >= 0);
    }

    #[test]
    fn test_size_matches_content() {
        let dir = TempDir::new().unwrap();
        let content = "hello world\n";
        fs::write(dir.path().join("test.txt"), content).unwrap();
        let entries = scan_directory(dir.path(), None, false);
        assert_eq!(entries[0].size, content.len() as u64);
    }

    #[test]
    fn test_stem_name_ext() {
        let dir = TempDir::new().unwrap();
        fs::write(dir.path().join("myfile.py"), "").unwrap();
        let entries = scan_directory(dir.path(), None, false);
        assert_eq!(entries[0].name.as_str(), "myfile.py");
        assert_eq!(entries[0].stem.as_str(), "myfile");
        assert_eq!(entries[0].ext.as_str(), ".py");
    }
}
