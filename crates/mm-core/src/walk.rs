use std::path::{Path, PathBuf};
use std::sync::Mutex;

use ignore::WalkBuilder;

use crate::meta::FileEntry;

struct ThreadBatch {
    local: Vec<FileEntry>,
    root: PathBuf,
    sink: *const Mutex<Vec<Vec<FileEntry>>>,
}

// SAFETY: ThreadBatch is only accessed from the thread that created it.
// The *const pointer to the Mutex is valid for the duration of scan_directory.
unsafe impl Send for ThreadBatch {}

impl Drop for ThreadBatch {
    fn drop(&mut self) {
        if !self.local.is_empty() {
            let batch = std::mem::take(&mut self.local);
            // SAFETY: the Mutex outlives all ThreadBatch instances because
            // build_parallel().run() joins all threads before returning.
            unsafe { &*self.sink }.lock().unwrap().push(batch);
        }
    }
}

/// Parallel directory scan with per-thread collection (no lock contention on hot path), and optional gitignore bypass.
pub fn scan_directory(root: &Path, n_threads: Option<usize>, no_ignore: bool) -> Vec<FileEntry> {
    let root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let completed: Mutex<Vec<Vec<FileEntry>>> = Mutex::new(Vec::new());

    let mut builder = WalkBuilder::new(&root);
    builder
        .hidden(false)
        .git_ignore(!no_ignore)
        .git_global(!no_ignore)
        .git_exclude(!no_ignore)
        .follow_links(false)
        .sort_by_file_path(|a, b| a.cmp(b));

    if let Some(threads) = n_threads {
        builder.threads(threads);
    }

    let sink_ptr: *const Mutex<Vec<Vec<FileEntry>>> = &completed;

    builder.build_parallel().run(|| {
        let mut tb = ThreadBatch {
            local: Vec::with_capacity(512),
            root: root.clone(),
            sink: sink_ptr,
        };
        Box::new(move |result| {
            if let Ok(entry) = result
                && let Some(ft) = entry.file_type()
                && ft.is_file()
                && let Ok(metadata) = entry.metadata()
            {
                let file_entry = FileEntry::from_path(entry.path(), &tb.root, &metadata);
                tb.local.push(file_entry);
            }
            ignore::WalkState::Continue
        })
    });

    let mut batches = completed.into_inner().unwrap();
    let total: usize = batches.iter().map(|b| b.len()).sum();
    let mut result = Vec::with_capacity(total);
    for batch in &mut batches {
        result.append(batch);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    #[test]
    fn test_scan_empty_dir() {
        let dir = TempDir::new().unwrap();
        let entries = scan_directory(dir.path(), None, false);
        assert!(entries.is_empty());
    }

    #[test]
    fn test_scan_with_files() {
        let dir = TempDir::new().unwrap();
        fs::write(dir.path().join("hello.py"), "print('hello')").unwrap();
        fs::write(dir.path().join("world.rs"), "fn main() {}").unwrap();
        fs::create_dir(dir.path().join("sub")).unwrap();
        fs::write(dir.path().join("sub/nested.txt"), "nested").unwrap();

        let entries = scan_directory(dir.path(), None, false);
        assert_eq!(entries.len(), 3);

        let names: Vec<&str> = entries.iter().map(|e| e.name.as_str()).collect();
        assert!(names.contains(&"hello.py"));
        assert!(names.contains(&"world.rs"));
        assert!(names.contains(&"nested.txt"));
    }

    #[test]
    fn test_scan_respects_gitignore() {
        let dir = TempDir::new().unwrap();
        // ignore crate needs a .git directory to honor .gitignore
        fs::create_dir(dir.path().join(".git")).unwrap();
        fs::write(dir.path().join(".gitignore"), "*.log\n").unwrap();
        fs::write(dir.path().join("keep.py"), "x = 1").unwrap();
        fs::write(dir.path().join("skip.log"), "log data").unwrap();

        let entries = scan_directory(dir.path(), None, false);
        let names: Vec<&str> = entries.iter().map(|e| e.name.as_str()).collect();
        assert!(names.contains(&"keep.py"));
        assert!(!names.contains(&"skip.log"));
    }
}
