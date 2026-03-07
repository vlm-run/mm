use std::path::Path;
use std::sync::Mutex;

use ignore::WalkBuilder;

use crate::meta::FileEntry;

pub fn scan_directory(root: &Path, n_threads: Option<usize>) -> Vec<FileEntry> {
    let root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let entries: Mutex<Vec<FileEntry>> = Mutex::new(Vec::with_capacity(4096));

    let mut builder = WalkBuilder::new(&root);
    builder
        .hidden(false)
        .git_ignore(true)
        .git_global(true)
        .git_exclude(true)
        .follow_links(false)
        .sort_by_file_path(|a, b| a.cmp(b));

    if let Some(threads) = n_threads {
        builder.threads(threads);
    }

    builder.build_parallel().run(|| {
        let entries = &entries;
        let root = &root;
        Box::new(move |result| {
            if let Ok(entry) = result {
                if let Some(ft) = entry.file_type() {
                    if ft.is_file() {
                        if let Ok(metadata) = entry.metadata() {
                            let file_entry =
                                FileEntry::from_path(entry.path(), root, &metadata);
                            entries.lock().unwrap().push(file_entry);
                        }
                    }
                }
            }
            ignore::WalkState::Continue
        })
    });

    entries.into_inner().unwrap()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    #[test]
    fn test_scan_empty_dir() {
        let dir = TempDir::new().unwrap();
        let entries = scan_directory(dir.path(), None);
        assert!(entries.is_empty());
    }

    #[test]
    fn test_scan_with_files() {
        let dir = TempDir::new().unwrap();
        fs::write(dir.path().join("hello.py"), "print('hello')").unwrap();
        fs::write(dir.path().join("world.rs"), "fn main() {}").unwrap();
        fs::create_dir(dir.path().join("sub")).unwrap();
        fs::write(dir.path().join("sub/nested.txt"), "nested").unwrap();

        let entries = scan_directory(dir.path(), None);
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

        let entries = scan_directory(dir.path(), None);
        let names: Vec<&str> = entries.iter().map(|e| e.name.as_str()).collect();
        assert!(names.contains(&"keep.py"));
        assert!(!names.contains(&"skip.log"));
    }
}
