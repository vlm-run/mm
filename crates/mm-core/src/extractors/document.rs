use std::path::Path;

use crate::extract::{ContentExtractor, ExtractError, L1Record};
use crate::hash;

pub struct DocumentExtractor;

impl ContentExtractor for DocumentExtractor {
    fn supports(&self, kind: &str) -> bool {
        kind == "document"
    }

    fn extract(&self, path: &Path) -> Result<L1Record, ExtractError> {
        let content_hash = hash::full_hash_mmap(path).map(|h| format!("{:016x}", h));

        let mut record = L1Record::default();
        record.content_hash = content_hash;
        Ok(record)
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
