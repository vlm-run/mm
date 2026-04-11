//! Image resize and tiling with base64 encoding.
//!
//! Uses the `image` crate for Lanczos3 resizing and JPEG/PNG encoding,
//! and the `base64` crate for encoding. Zero Python dependencies.

use std::io::Cursor;
use std::path::Path;

use image::imageops::FilterType;
use image::{DynamicImage, GenericImageView, ImageFormat, ImageReader};

use super::{EncodedImage, EncodedTile};

/// Resize an image to fit within `max_width` (keeping aspect ratio) and
/// return the base64-encoded result.
///
/// Output format: JPEG for opaque images, PNG if the source has alpha.
pub fn resize_and_encode(path: &Path, max_width: u32) -> Result<EncodedImage, String> {
    let img = load_image(path)?;
    let (orig_w, orig_h) = img.dimensions();

    let (resized, w, h) = if orig_w > max_width {
        let scale = max_width as f64 / orig_w as f64;
        let new_h = (orig_h as f64 * scale).round() as u32;
        let r = img.resize(max_width, new_h, FilterType::Lanczos3);
        let dims = r.dimensions();
        (r, dims.0, dims.1)
    } else {
        (img, orig_w, orig_h)
    };

    let (base64, mime) = encode_to_base64(&resized, path);
    Ok(EncodedImage {
        base64,
        mime,
        width: w,
        height: h,
    })
}

/// Tile a large image into `tile_size x tile_size` squares and encode each tile.
///
/// If the image is smaller than `tile_size` in both dimensions, returns a
/// single tile containing the full (possibly resized) image.
pub fn tile_and_encode(path: &Path, tile_size: u32) -> Result<Vec<EncodedTile>, String> {
    let img = load_image(path)?;
    let (w, h) = img.dimensions();

    // If image is smaller than one tile, just return it as a single tile
    if w <= tile_size && h <= tile_size {
        let (base64, mime) = encode_to_base64(&img, path);
        return Ok(vec![EncodedTile {
            base64,
            mime,
            col: 0,
            row: 0,
            total_cols: 1,
            total_rows: 1,
            width: w,
            height: h,
        }]);
    }

    let cols = (w + tile_size - 1) / tile_size;
    let rows = (h + tile_size - 1) / tile_size;
    let mut tiles = Vec::with_capacity((cols * rows) as usize);

    for row in 0..rows {
        for col in 0..cols {
            let x = col * tile_size;
            let y = row * tile_size;
            let tw = (tile_size).min(w - x);
            let th = (tile_size).min(h - y);

            let tile_img = img.crop_imm(x, y, tw, th);
            let (base64, mime) = encode_to_base64(&tile_img, path);

            tiles.push(EncodedTile {
                base64,
                mime,
                col,
                row,
                total_cols: cols,
                total_rows: rows,
                width: tw,
                height: th,
            });
        }
    }

    Ok(tiles)
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

fn load_image(path: &Path) -> Result<DynamicImage, String> {
    ImageReader::open(path)
        .map_err(|e| format!("failed to open image {}: {e}", path.display()))?
        .decode()
        .map_err(|e| format!("failed to decode image {}: {e}", path.display()))
}

/// Encode a `DynamicImage` to base64 as JPEG (opaque) or PNG (has alpha).
fn encode_to_base64(img: &DynamicImage, source_path: &Path) -> (String, String) {
    use base64::Engine;

    let has_alpha = matches!(
        img,
        DynamicImage::ImageRgba8(_)
            | DynamicImage::ImageRgba16(_)
            | DynamicImage::ImageRgba32F(_)
            | DynamicImage::ImageLumaA8(_)
            | DynamicImage::ImageLumaA16(_)
    );

    // Prefer source format hint for PNG/WebP/GIF; default JPEG for photos
    let ext = source_path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase();

    let (format, mime) = if has_alpha || ext == "png" {
        (ImageFormat::Png, "image/png")
    } else if ext == "webp" {
        (ImageFormat::WebP, "image/webp")
    } else {
        (ImageFormat::Jpeg, "image/jpeg")
    };

    let mut buf = Vec::new();
    let mut cursor = Cursor::new(&mut buf);

    // For JPEG, encode the RGB version to avoid alpha issues
    if format == ImageFormat::Jpeg {
        let rgb = DynamicImage::ImageRgb8(img.to_rgb8());
        rgb.write_to(&mut cursor, format)
            .expect("JPEG encode failed");
    } else {
        img.write_to(&mut cursor, format)
            .expect("image encode failed");
    }

    let b64 = base64::engine::general_purpose::STANDARD.encode(&buf);
    (b64, mime.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn create_test_image(tmp: &Path, name: &str, w: u32, h: u32) -> PathBuf {
        let img = DynamicImage::new_rgb8(w, h);
        let path = tmp.join(name);
        img.save(&path).unwrap();
        path
    }

    #[test]
    fn test_resize_small_image_no_change() {
        let tmp = tempfile::tempdir().unwrap();
        let path = create_test_image(tmp.path(), "small.png", 200, 100);
        let result = resize_and_encode(&path, 1024).unwrap();
        assert_eq!(result.width, 200);
        assert_eq!(result.height, 100);
        assert_eq!(result.mime, "image/png");
        assert!(!result.base64.is_empty());
    }

    #[test]
    fn test_resize_large_image() {
        let tmp = tempfile::tempdir().unwrap();
        let path = create_test_image(tmp.path(), "large.jpg", 3000, 2000);
        let result = resize_and_encode(&path, 1024).unwrap();
        assert_eq!(result.width, 1024);
        // Aspect ratio: 2000/3000 * 1024 ≈ 683
        assert!(result.height > 650 && result.height < 700);
        assert_eq!(result.mime, "image/jpeg");
    }

    #[test]
    fn test_tile_small_image() {
        let tmp = tempfile::tempdir().unwrap();
        let path = create_test_image(tmp.path(), "small.png", 500, 300);
        let tiles = tile_and_encode(&path, 1024).unwrap();
        assert_eq!(tiles.len(), 1);
        assert_eq!(tiles[0].total_cols, 1);
        assert_eq!(tiles[0].total_rows, 1);
    }

    #[test]
    fn test_tile_large_image() {
        let tmp = tempfile::tempdir().unwrap();
        let path = create_test_image(tmp.path(), "large.png", 3000, 2000);
        let tiles = tile_and_encode(&path, 1024).unwrap();
        // 3000/1024 = 3 cols, 2000/1024 = 2 rows → 6 tiles
        assert_eq!(tiles.len(), 6);
        assert_eq!(tiles[0].total_cols, 3);
        assert_eq!(tiles[0].total_rows, 2);
        // Each tile should have valid base64
        for tile in &tiles {
            assert!(!tile.base64.is_empty());
        }
    }
}
