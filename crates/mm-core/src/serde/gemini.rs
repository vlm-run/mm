//! Pre-compiled Gemini Part serialization.
//!
//! Produces JSON strings matching the `google.genai.types.Part` dict format,
//! ready for direct inclusion in Gemini API requests.

use std::path::Path;

use base64::Engine;

/// Serialize an image file as a Gemini `inline_data` Part JSON string.
pub fn image_part_json(path: &Path) -> Result<String, String> {
    let data = std::fs::read(path)
        .map_err(|e| format!("failed to read {}: {e}", path.display()))?;
    let mime = mime_for_path(path);
    let b64 = base64::engine::general_purpose::STANDARD.encode(&data);
    Ok(format!(
        r#"{{"inline_data":{{"mime_type":"{}","data":"{}"}}}}"#,
        mime, b64
    ))
}

/// Serialize a document (PDF) file as a Gemini `inline_data` Part JSON string.
pub fn document_part_json(path: &Path) -> Result<String, String> {
    let data = std::fs::read(path)
        .map_err(|e| format!("failed to read {}: {e}", path.display()))?;
    let mime = mime_for_path(path);
    let b64 = base64::engine::general_purpose::STANDARD.encode(&data);
    Ok(format!(
        r#"{{"inline_data":{{"mime_type":"{}","data":"{}"}}}}"#,
        mime, b64
    ))
}

/// Serialize a video file as Gemini `inline_data` Part JSON strings.
///
/// For videos longer than `max_seconds`, produces multiple overlapping chunks.
/// Each chunk is a separate JSON string.
///
/// Note: This reads the full video bytes. For very large files, the Python
/// side should handle ffmpeg-based segment extraction instead.
pub fn video_parts_json(path: &Path, _max_seconds: u32, _overlap: u32) -> Result<Vec<String>, String> {
    // For now, return the full video as a single part.
    // Chunking by duration requires ffmpeg or container parsing,
    // which is better handled on the Python side.
    let data = std::fs::read(path)
        .map_err(|e| format!("failed to read {}: {e}", path.display()))?;
    let mime = mime_for_path(path);
    let b64 = base64::engine::general_purpose::STANDARD.encode(&data);
    Ok(vec![format!(
        r#"{{"inline_data":{{"mime_type":"{}","data":"{}"}}}}"#,
        mime, b64
    )])
}

fn mime_for_path(path: &Path) -> &'static str {
    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase();
    // Borrow checker: match on owned String
    match ext.as_str() {
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "gif" => "image/gif",
        "webp" => "image/webp",
        "bmp" => "image/bmp",
        "pdf" => "application/pdf",
        "mp4" => "video/mp4",
        "mov" => "video/quicktime",
        "mkv" => "video/x-matroska",
        "webm" => "video/webm",
        "avi" => "video/x-msvideo",
        "mp3" => "audio/mpeg",
        "wav" => "audio/wav",
        "flac" => "audio/flac",
        "ogg" => "audio/ogg",
        _ => "application/octet-stream",
    }
}
