use std::path::Path;

use crate::extract::{ContentExtractor, ExtractError, FastRecord};
use crate::hash;

use super::shared;

pub struct VideoExtractor;

impl ContentExtractor for VideoExtractor {
    fn supports(&self, kind: &str) -> bool {
        kind == "video"
    }

    fn extract(&self, path: &Path) -> Result<FastRecord, ExtractError> {
        let ext = path
            .extension()
            .map(|e| e.to_string_lossy().to_ascii_lowercase())
            .unwrap_or_default();

        let content_hash = hash::full_hash_mmap(path).map(|h| format!("{:016x}", h));

        let mut record = match ext.as_str() {
            "mp4" | "m4v" | "mov" | "3gp" => shared::extract_mp4(path).unwrap_or_default(),
            "mkv" | "webm" => shared::extract_matroska(path).unwrap_or_default(),
            _ => FastRecord::default(),
        };

        record.content_hash = content_hash;
        Ok(record)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_supports_video_only() {
        let ext = VideoExtractor;
        assert!(ext.supports("video"));
        assert!(!ext.supports("image"));
        assert!(!ext.supports("code"));
        assert!(!ext.supports("audio"));
    }

    #[test]
    fn test_nonexistent_file() {
        let result = VideoExtractor.extract(Path::new("/nonexistent/video.mp4"));
        assert!(result.is_ok());
        let record = result.unwrap();
        assert!(record.dimensions.is_none());
        assert!(record.content_hash.is_none());
    }

    #[test]
    fn test_mkv_codec_mapping() {
        use super::shared::mkv_codec_id_to_name;
        assert_eq!(mkv_codec_id_to_name("V_VP9"), "vp9");
        assert_eq!(mkv_codec_id_to_name("V_MPEG4/ISO/AVC"), "h264");
        assert_eq!(mkv_codec_id_to_name("A_OPUS"), "opus");
        assert_eq!(mkv_codec_id_to_name("UNKNOWN"), "unknown");
    }
}
