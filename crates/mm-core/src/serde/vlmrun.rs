//! VLMRun-specific serialization.
//!
//! Optimized encoding for the VLMRun inference server protocol.
//! Currently a scaffold — implementations will be added as the
//! VLMRun server protocol stabilizes.

use std::path::Path;

/// Encode an image for VLMRun (resize + base64, same as OpenAI format for now).
pub fn encode_image(path: &Path, max_width: u32) -> Result<String, String> {
    let encoded = super::image::resize_and_encode(path, max_width)?;
    Ok(serde_json::json!({
        "type": "image_url",
        "image_url": {
            "url": format!("data:{};base64,{}", encoded.mime, encoded.base64)
        }
    })
    .to_string())
}

/// Encode video chunks for VLMRun.
///
/// Scaffold — delegates to Gemini format for now.
pub fn encode_video_chunks(path: &Path, max_seconds: u32) -> Result<Vec<String>, String> {
    super::gemini::video_parts_json(path, max_seconds, 0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_encode_image_produces_json() {
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join("test.png");
        let img = image::DynamicImage::new_rgb8(100, 100);
        img.save(&path).unwrap();

        let json_str = encode_image(&path, 1024).unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&json_str).unwrap();
        assert_eq!(parsed["type"], "image_url");
        assert!(
            parsed["image_url"]["url"]
                .as_str()
                .unwrap()
                .starts_with("data:image/png;base64,")
        );
    }
}
