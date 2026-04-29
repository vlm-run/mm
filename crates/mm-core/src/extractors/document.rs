use std::path::Path;

use crate::extract::{ContentExtractor, ExtractError, FastRecord};
use crate::hash;

pub struct DocumentExtractor;

impl ContentExtractor for DocumentExtractor {
    fn supports(&self, kind: &str) -> bool {
        kind == "document"
    }

    fn extract(&self, path: &Path) -> Result<FastRecord, ExtractError> {
        let content_hash = hash::full_hash_mmap(path).map(|h| format!("{:016x}", h));

        Ok(FastRecord {
            content_hash,
            ..Default::default()
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_supports_document_only() {
        let ext = DocumentExtractor;
        assert!(ext.supports("document"));
        assert!(!ext.supports("video"));
        assert!(!ext.supports("image"));
        assert!(!ext.supports("code"));
    }

    #[test]
    fn test_nonexistent_file() {
        let result = DocumentExtractor.extract(Path::new("/nonexistent/doc.pdf"));
        assert!(result.is_ok());
        let record = result.unwrap();
        assert!(record.content_hash.is_none());
    }
}
