use std::collections::HashMap;
use std::path::Path;

use rayon::prelude::*;

use crate::meta::{FileEntry, FileKind};

#[derive(Debug, Default)]
pub struct KindStats {
    pub files: u32,
    pub bytes: u64,
    pub lines: u64,
    pub tokens: u64,
}

#[derive(Debug, Default)]
pub struct WcResult {
    pub files: u32,
    pub bytes: u64,
    pub lines: u64,
    pub estimated_tokens: u64,
    pub by_kind: HashMap<String, KindStats>,
}

/// Count files, bytes, lines, and estimated tokens for a set of entries.
/// Documents are skipped (Python handles via pypdfium2).
pub fn count_entries(entries: &[&FileEntry], root: &Path) -> WcResult {
    // Per-file stats computed in parallel for text-readable kinds
    let per_file: Vec<(&FileEntry, u64, u64)> = entries
        .par_iter()
        .map(|entry| {
            let (lines, tokens) = match entry.kind {
                FileKind::Image => {
                    let tokens = estimate_image_tokens(entry.width, entry.height);
                    (0u64, tokens)
                }
                FileKind::Video | FileKind::Audio => (0, 85),
                FileKind::Code | FileKind::Text | FileKind::Config | FileKind::Data => {
                    let path = if entry.path.is_empty() {
                        root.to_path_buf()
                    } else {
                        root.join(entry.path.as_str())
                    };
                    match std::fs::read(&path) {
                        Ok(bytes) => {
                            let content = String::from_utf8_lossy(&bytes);
                            let lines = content.lines().count() as u64;
                            let tokens = (bytes.len() as u64) / 4;
                            (lines, tokens)
                        }
                        Err(_) => (0, 0),
                    }
                }
                FileKind::Document => (0, 0), // Python handles documents
                FileKind::Other => (0, entry.size / 4),
            };
            (*entry, lines, tokens)
        })
        .collect();

    // Aggregate
    let mut result = WcResult::default();
    for (entry, lines, tokens) in per_file {
        let kind_name = entry.kind.to_string();
        result.files += 1;
        result.bytes += entry.size;
        result.lines += lines;
        result.estimated_tokens += tokens;

        let stats = result.by_kind.entry(kind_name).or_default();
        stats.files += 1;
        stats.bytes += entry.size;
        stats.lines += lines;
        stats.tokens += tokens;
    }

    result
}

fn estimate_image_tokens(width: Option<u32>, height: Option<u32>) -> u64 {
    match (width, height) {
        (Some(w), Some(h)) if w > 0 && h > 0 => {
            let tiles = w.div_ceil(512) * h.div_ceil(512);
            85 + (tiles as u64) * 170
        }
        _ => 85,
    }
}

/// Serialize WcResult to JSON matching the Python wc output format.
pub fn wc_to_json(result: &WcResult) -> String {
    let mut map = serde_json::Map::new();
    map.insert("files".into(), serde_json::json!(result.files));
    map.insert("bytes".into(), serde_json::json!(result.bytes));
    map.insert("lines".into(), serde_json::json!(result.lines));
    map.insert(
        "estimated_tokens".into(),
        serde_json::json!(result.estimated_tokens),
    );

    // tok_per_mb
    let total_mb = result.bytes as f64 / (1024.0 * 1024.0);
    if total_mb > 0.0 {
        map.insert(
            "tok_per_mb".into(),
            serde_json::json!((result.estimated_tokens as f64 / total_mb).round() as u64),
        );
    }

    // by_kind
    let mut by_kind = serde_json::Map::new();
    for (kind, stats) in &result.by_kind {
        let mut s = serde_json::Map::new();
        s.insert("files".into(), serde_json::json!(stats.files));
        s.insert("bytes".into(), serde_json::json!(stats.bytes));
        s.insert("lines".into(), serde_json::json!(stats.lines));
        s.insert("tokens".into(), serde_json::json!(stats.tokens));
        let mb = stats.bytes as f64 / (1024.0 * 1024.0);
        if mb > 0.0 {
            s.insert(
                "tok_per_mb".into(),
                serde_json::json!((stats.tokens as f64 / mb).round() as u64),
            );
        }
        if kind == "image" && stats.files > 0 {
            s.insert(
                "tok_per_img".into(),
                serde_json::json!((stats.tokens as f64 / stats.files as f64).round() as u64),
            );
        }
        by_kind.insert(kind.clone(), serde_json::Value::Object(s));
    }
    map.insert("by_kind".into(), serde_json::Value::Object(by_kind));

    serde_json::to_string_pretty(&serde_json::Value::Object(map))
        .unwrap_or_else(|_| "{}".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use compact_str::CompactString;
    use std::fs;
    use tempfile::TempDir;

    fn entry(path: &str, kind: FileKind, size: u64) -> FileEntry {
        let name = path.rsplit('/').next().unwrap_or(path);
        FileEntry {
            path: CompactString::new(path),
            name: CompactString::new(name),
            stem: CompactString::new(""),
            ext: CompactString::new(""),
            size,
            modified_epoch_us: 0,
            created_epoch_us: 0,
            mime: CompactString::new(""),
            kind,
            is_binary: false,
            depth: 0,
            parent: CompactString::new(""),
            width: None,
            height: None,
        }
    }

    #[test]
    fn test_image_token_estimation() {
        assert_eq!(estimate_image_tokens(Some(1024), Some(1024)), 85 + 4 * 170);
        assert_eq!(estimate_image_tokens(None, None), 85);
    }

    #[test]
    fn test_count_entries_text_files() {
        let dir = TempDir::new().unwrap();
        fs::write(dir.path().join("hello.txt"), "line1\nline2\nline3\n").unwrap();

        let e = FileEntry {
            path: CompactString::new("hello.txt"),
            name: CompactString::new("hello.txt"),
            stem: CompactString::new("hello"),
            ext: CompactString::new(".txt"),
            size: 18,
            kind: FileKind::Text,
            is_binary: false,
            modified_epoch_us: 0,
            created_epoch_us: 0,
            mime: CompactString::new("text/plain"),
            depth: 0,
            parent: CompactString::new(""),
            width: None,
            height: None,
        };
        let refs = vec![&e];
        let result = count_entries(&refs, dir.path());

        assert_eq!(result.files, 1);
        assert_eq!(result.lines, 3);
        assert_eq!(result.estimated_tokens, 18 / 4);
    }
}
