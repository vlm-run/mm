//! Image resize and tiling with base64 encoding.
//!
//! Provides high-performance image-to-base64 encoding for VLM message
//! construction.  Uses the `image` crate for Lanczos3 resizing and the
//! `base64` crate for encoding.  Zero Python or ffmpeg dependencies.
//!
//! # Quality
//!
//! JPEG quality defaults to **85** — a good balance between file size
//! and visual fidelity for VLM consumption.  Most VLMs downsample
//! internally, so quality above 90 wastes tokens without benefit.

use std::io::Cursor;
use std::path::Path;

use base64::Engine;
use image::codecs::jpeg::JpegEncoder;
use image::imageops::FilterType;
use image::{DynamicImage, GenericImageView, ImageFormat, ImageReader};

use super::{EncodedImage, EncodedTile};

/// Default JPEG quality (1–100).  85 balances size and fidelity for VLMs.
const DEFAULT_JPEG_QUALITY: u8 = 85;

/// Resize an image to fit within `max_width` pixels (preserving aspect
/// ratio) and return the base64-encoded result.
///
/// # Arguments
///
/// * `path` – Filesystem path to the source image.
/// * `max_width` – Maximum output width.  Images narrower than this are
///   returned unchanged.
///
/// Output format is JPEG for opaque images and PNG when the source has an
/// alpha channel.
pub fn resize_and_encode(path: &Path, max_width: u32) -> Result<EncodedImage, String> {
    resize_and_encode_with_quality(path, max_width, DEFAULT_JPEG_QUALITY)
}

/// Like [`resize_and_encode`] but with an explicit JPEG quality setting.
///
/// # Arguments
///
/// * `quality` – JPEG quality from 1 (worst) to 100 (best).  Ignored
///   when the output format is PNG.
pub fn resize_and_encode_with_quality(
    path: &Path,
    max_width: u32,
    quality: u8,
) -> Result<EncodedImage, String> {
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

    let (base64, mime) = encode_to_base64(&resized, path, quality);
    Ok(EncodedImage {
        base64,
        mime,
        width: w,
        height: h,
    })
}

/// Tile a large image into `tile_size × tile_size` squares and encode
/// each tile as base64.
///
/// Images smaller than `tile_size` in both dimensions are returned as a
/// single tile without splitting.
pub fn tile_and_encode(path: &Path, tile_size: u32) -> Result<Vec<EncodedTile>, String> {
    tile_and_encode_with_quality(path, tile_size, DEFAULT_JPEG_QUALITY)
}

/// Like [`tile_and_encode`] but with an explicit JPEG quality setting.
pub fn tile_and_encode_with_quality(
    path: &Path,
    tile_size: u32,
    quality: u8,
) -> Result<Vec<EncodedTile>, String> {
    let img = load_image(path)?;
    let (w, h) = img.dimensions();

    if w <= tile_size && h <= tile_size {
        let (base64, mime) = encode_to_base64(&img, path, quality);
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
            let tw = tile_size.min(w - x);
            let th = tile_size.min(h - y);

            let tile_img = img.crop_imm(x, y, tw, th);
            let (base64, mime) = encode_to_base64(&tile_img, path, quality);

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

fn load_image(path: &Path) -> Result<DynamicImage, String> {
    ImageReader::open(path)
        .map_err(|e| format!("failed to open image {}: {e}", path.display()))?
        .decode()
        .map_err(|e| format!("failed to decode image {}: {e}", path.display()))
}

/// Encode a `DynamicImage` to base64 using the most appropriate format.
///
/// Format selection:
///   - **PNG** if the image has an alpha channel or the source is `.png`.
///   - **WebP** if the source is `.webp`.
///   - **JPEG** otherwise, encoded with the given `quality` (1–100).
///
/// For JPEG the image is first converted to RGB8 to strip any alpha
/// channel that would cause the encoder to fail.
fn encode_to_base64(img: &DynamicImage, source_path: &Path, quality: u8) -> (String, String) {
    let has_alpha = matches!(
        img,
        DynamicImage::ImageRgba8(_)
            | DynamicImage::ImageRgba16(_)
            | DynamicImage::ImageRgba32F(_)
            | DynamicImage::ImageLumaA8(_)
            | DynamicImage::ImageLumaA16(_)
    );

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

    let mut buf: Vec<u8> = Vec::new();

    if format == ImageFormat::Jpeg {
        // Use JpegEncoder directly so we can control quality.
        let rgb = img.to_rgb8();
        let mut encoder = JpegEncoder::new_with_quality(&mut buf, quality);
        encoder
            .encode_image(&rgb)
            .expect("JPEG encode failed");
    } else {
        let mut cursor = Cursor::new(&mut buf);
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
        assert!(result.height > 650 && result.height < 700);
        assert_eq!(result.mime, "image/jpeg");
    }

    #[test]
    fn test_resize_with_explicit_quality() {
        let tmp = tempfile::tempdir().unwrap();
        // Create a noisy image so JPEG quality actually affects size.
        let mut img = image::RgbImage::new(800, 600);
        for (x, y, pixel) in img.enumerate_pixels_mut() {
            *pixel = image::Rgb([(x % 256) as u8, (y % 256) as u8, ((x + y) % 256) as u8]);
        }
        let path = tmp.path().join("noisy.jpg");
        DynamicImage::ImageRgb8(img).save(&path).unwrap();

        let high = resize_and_encode_with_quality(&path, 1024, 95).unwrap();
        let low = resize_and_encode_with_quality(&path, 1024, 50).unwrap();
        // Lower quality → smaller base64 string
        assert!(
            low.base64.len() < high.base64.len(),
            "q50 ({}) should be smaller than q95 ({})",
            low.base64.len(),
            high.base64.len()
        );
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
        assert_eq!(tiles.len(), 6);
        assert_eq!(tiles[0].total_cols, 3);
        assert_eq!(tiles[0].total_rows, 2);
        for tile in &tiles {
            assert!(!tile.base64.is_empty());
        }
    }
}
