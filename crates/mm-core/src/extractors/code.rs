use std::fs;
use std::path::Path;

use crate::extract::{ContentExtractor, ExtractError, L1Record};

pub struct CodeExtractor;

impl ContentExtractor for CodeExtractor {
    fn supports(&self, kind: &str) -> bool {
        matches!(kind, "code" | "text" | "config")
    }

    fn extract(&self, path: &Path) -> Result<L1Record, ExtractError> {
        let content = fs::read_to_string(path).map_err(ExtractError::Io)?;

        let line_count = content.lines().count() as u32;
        let word_count = content.split_whitespace().count() as u32;
        let preview: String = content.chars().take(500).collect();

        let hash = xxhash_rust::xxh3::xxh3_64(content.as_bytes());
        let content_hash = format!("{:016x}", hash);

        let language = detect_language(path);

        Ok(L1Record {
            content_hash: Some(content_hash),
            text_preview: Some(preview),
            line_count: Some(line_count),
            word_count: Some(word_count),
            language,
            ..Default::default()
        })
    }
}

fn detect_language(path: &Path) -> Option<String> {
    let ext = path.extension()?.to_str()?;
    let lang = match ext {
        "rs" => "rust",
        "py" => "python",
        "js" => "javascript",
        "ts" => "typescript",
        "tsx" => "typescript",
        "jsx" => "javascript",
        "c" => "c",
        "cpp" | "cc" | "cxx" => "cpp",
        "h" | "hpp" => "c/cpp",
        "go" => "go",
        "java" => "java",
        "kt" | "kts" => "kotlin",
        "swift" => "swift",
        "rb" => "ruby",
        "php" => "php",
        "cs" => "csharp",
        "scala" => "scala",
        "sh" | "bash" | "zsh" => "shell",
        "sql" => "sql",
        "html" | "htm" => "html",
        "css" | "scss" | "sass" | "less" => "css",
        "json" => "json",
        "yaml" | "yml" => "yaml",
        "toml" => "toml",
        "xml" => "xml",
        "md" | "markdown" => "markdown",
        "dart" => "dart",
        "r" => "r",
        "jl" => "julia",
        "lua" => "lua",
        "zig" => "zig",
        "nim" => "nim",
        "ex" | "exs" => "elixir",
        "erl" => "erlang",
        "hs" => "haskell",
        "vue" => "vue",
        "svelte" => "svelte",
        _ => return None,
    };
    Some(lang.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::extract::ContentExtractor;
    use tempfile::TempDir;

    #[test]
    fn test_supports_code_text_config() {
        let ext = CodeExtractor;
        assert!(ext.supports("code"));
        assert!(ext.supports("text"));
        assert!(ext.supports("config"));
        assert!(!ext.supports("image"));
        assert!(!ext.supports("video"));
        assert!(!ext.supports("audio"));
    }

    #[test]
    fn test_line_count() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.py");
        std::fs::write(&path, "line1\nline2\nline3\n").unwrap();
        let result = CodeExtractor.extract(&path).unwrap();
        assert_eq!(result.line_count, Some(3));
    }

    #[test]
    fn test_word_count() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.py");
        std::fs::write(&path, "hello world foo bar\n").unwrap();
        let result = CodeExtractor.extract(&path).unwrap();
        assert_eq!(result.word_count, Some(4));
    }

    #[test]
    fn test_content_hash_deterministic() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.py");
        std::fs::write(&path, "x = 1\n").unwrap();
        let h1 = CodeExtractor.extract(&path).unwrap().content_hash;
        let h2 = CodeExtractor.extract(&path).unwrap().content_hash;
        assert_eq!(h1, h2);
    }

    #[test]
    fn test_content_hash_16_chars() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.py");
        std::fs::write(&path, "x = 1\n").unwrap();
        let hash = CodeExtractor.extract(&path).unwrap().content_hash.unwrap();
        assert_eq!(hash.len(), 16);
    }

    #[test]
    fn test_different_content_different_hash() {
        let dir = TempDir::new().unwrap();
        let p1 = dir.path().join("a.py");
        let p2 = dir.path().join("b.py");
        std::fs::write(&p1, "aaa\n").unwrap();
        std::fs::write(&p2, "bbb\n").unwrap();
        let h1 = CodeExtractor.extract(&p1).unwrap().content_hash;
        let h2 = CodeExtractor.extract(&p2).unwrap().content_hash;
        assert_ne!(h1, h2);
    }

    #[test]
    fn test_text_preview_capped_at_500() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("big.py");
        std::fs::write(&path, "x".repeat(2000)).unwrap();
        let preview = CodeExtractor.extract(&path).unwrap().text_preview.unwrap();
        assert_eq!(preview.len(), 500);
    }

    #[test]
    fn test_language_detection_python() {
        assert_eq!(detect_language(Path::new("test.py")), Some("python".into()));
    }

    #[test]
    fn test_language_detection_rust() {
        assert_eq!(detect_language(Path::new("lib.rs")), Some("rust".into()));
    }

    #[test]
    fn test_language_detection_js() {
        assert_eq!(
            detect_language(Path::new("app.js")),
            Some("javascript".into())
        );
    }

    #[test]
    fn test_language_detection_ts() {
        assert_eq!(
            detect_language(Path::new("app.ts")),
            Some("typescript".into())
        );
    }

    #[test]
    fn test_language_detection_tsx() {
        assert_eq!(
            detect_language(Path::new("App.tsx")),
            Some("typescript".into())
        );
    }

    #[test]
    fn test_language_detection_go() {
        assert_eq!(detect_language(Path::new("main.go")), Some("go".into()));
    }

    #[test]
    fn test_language_detection_yaml() {
        assert_eq!(
            detect_language(Path::new("config.yaml")),
            Some("yaml".into())
        );
        assert_eq!(
            detect_language(Path::new("config.yml")),
            Some("yaml".into())
        );
    }

    #[test]
    fn test_language_detection_markdown() {
        assert_eq!(
            detect_language(Path::new("README.md")),
            Some("markdown".into())
        );
    }

    #[test]
    fn test_language_detection_unknown() {
        assert_eq!(detect_language(Path::new("file.xyz_unknown")), None);
    }

    #[test]
    fn test_language_detection_no_extension() {
        assert_eq!(detect_language(Path::new("Makefile")), None);
    }

    #[test]
    fn test_no_exif_fields_for_code() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.py");
        std::fs::write(&path, "x = 1\n").unwrap();
        let result = CodeExtractor.extract(&path).unwrap();
        assert!(result.exif_camera.is_none());
        assert!(result.exif_date.is_none());
        assert!(result.exif_gps.is_none());
        assert!(result.exif_orientation.is_none());
    }

    #[test]
    fn test_no_dimensions_for_code() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.py");
        std::fs::write(&path, "x = 1\n").unwrap();
        let result = CodeExtractor.extract(&path).unwrap();
        assert!(result.dimensions.is_none());
    }

    #[test]
    fn test_empty_file() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("empty.py");
        std::fs::write(&path, "").unwrap();
        let result = CodeExtractor.extract(&path).unwrap();
        assert_eq!(result.line_count, Some(0));
        assert_eq!(result.word_count, Some(0));
    }
}
