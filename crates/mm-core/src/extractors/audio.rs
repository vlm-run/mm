use std::path::Path;

use crate::extract::{ContentExtractor, ExtractError, FastRecord};
use crate::hash;

use super::shared;

pub struct AudioExtractor;

impl ContentExtractor for AudioExtractor {
    fn supports(&self, kind: &str) -> bool {
        kind == "audio"
    }

    fn extract(&self, path: &Path) -> Result<FastRecord, ExtractError> {
        let ext = path
            .extension()
            .map(|e| e.to_string_lossy().to_ascii_lowercase())
            .unwrap_or_default();

        let content_hash = hash::full_hash_mmap(path).map(|h| format!("{:016x}", h));

        let mut record = match ext.as_str() {
            // M4A is an MP4 container with audio only
            "m4a" => shared::extract_mp4(path).unwrap_or_default(),
            // Symphonia handles all common audio-only formats
            "mp3" | "wav" | "flac" | "aac" | "ogg" | "opus" | "wma" => {
                shared::extract_symphonia(path).unwrap_or_default()
            }
            _ => shared::extract_symphonia(path).unwrap_or_default(),
        };

        record.content_hash = content_hash;
        Ok(record)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_supports_audio_only() {
        let ext = AudioExtractor;
        assert!(ext.supports("audio"));
        assert!(!ext.supports("video"));
        assert!(!ext.supports("image"));
        assert!(!ext.supports("code"));
    }

    #[test]
    fn test_nonexistent_file() {
        let result = AudioExtractor.extract(Path::new("/nonexistent/audio.mp3"));
        assert!(result.is_ok());
        let record = result.unwrap();
        assert!(record.duration_s.is_none());
        assert!(record.content_hash.is_none());
    }
}
