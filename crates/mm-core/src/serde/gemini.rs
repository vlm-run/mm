//! Pre-compiled Gemini Part serialization.
//!
//! Produces JSON strings matching the `google.genai.types.Part` dict format,
//! ready for direct inclusion in Gemini API requests.  Uses `serde_json` for
//! safe JSON construction and `mime_guess` for standard MIME detection.

use std::path::Path;

use base64::Engine;

/// Serialize an image file as a Gemini `inline_data` Part JSON string.
pub fn image_part_json(path: &Path) -> Result<String, String> {
    inline_data_json(path)
}

/// Serialize a document (PDF) file as a Gemini `inline_data` Part JSON string.
pub fn document_part_json(path: &Path) -> Result<String, String> {
    inline_data_json(path)
}

/// Serialize a video file as Gemini `inline_data` Part JSON strings.
///
/// For videos longer than `max_seconds`, produces multiple overlapping chunks.
/// CURRENTLY: it returns the full video as a single part; duration-based chunking
/// requires ffmpeg and is handled on the Python side.
pub fn video_parts_json(
    path: &Path,
    _max_seconds: u32,
    _overlap: u32,
) -> Result<Vec<String>, String> {
    Ok(vec![inline_data_json(path)?])
}

fn inline_data_json(path: &Path) -> Result<String, String> {
    let data =
        std::fs::read(path).map_err(|e| format!("failed to read {}: {e}", path.display()))?;
    let mime = mime_for_path(path);
    let b64 = base64::engine::general_purpose::STANDARD.encode(&data);
    let part = serde_json::json!({
        "inline_data": {
            "mime_type": mime,
            "data": b64,
        }
    });
    serde_json::to_string(&part).map_err(|e| format!("JSON serialization failed: {e}"))
}

fn mime_for_path(path: &Path) -> String {
    mime_guess::from_path(path)
        .first_raw()
        .unwrap_or("application/octet-stream")
        .to_string()
}
