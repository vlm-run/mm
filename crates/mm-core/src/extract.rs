use std::path::Path;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum ExtractError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
    #[error("Unsupported file type: {0}")]
    Unsupported(String),
}

#[derive(Debug, Clone, Default)]
pub struct FastRecord {
    pub content_hash: Option<String>,
    pub text_preview: Option<String>,
    pub line_count: Option<u32>,
    pub word_count: Option<u32>,
    pub language: Option<String>,
    pub dimensions: Option<String>,
    pub pages: Option<u32>,
    pub duration_s: Option<f64>,
    pub magic_mime: Option<String>,
    pub exif_camera: Option<String>,
    pub exif_date: Option<String>,
    pub exif_gps: Option<String>,
    pub exif_orientation: Option<String>,
    pub video_codec: Option<String>,
    pub audio_codec: Option<String>,
    pub fps: Option<f64>,
    pub has_audio: Option<bool>,
    pub phash: Option<u64>,
}

pub trait ContentExtractor: Send + Sync {
    fn extract(&self, path: &Path) -> Result<FastRecord, ExtractError>;
    fn supports(&self, kind: &str) -> bool;
}

pub trait SemanticAnalyzer: Send + Sync {
    fn caption(&self, path: &Path, content: &[u8]) -> Result<String, ExtractError>;
    fn embed(&self, path: &Path, content: &[u8]) -> Result<Vec<f32>, ExtractError>;
    fn describe(&self, path: &Path, content: &[u8]) -> Result<String, ExtractError>;
}
