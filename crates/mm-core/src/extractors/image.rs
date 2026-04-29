use std::io::{BufReader, Cursor};
use std::path::Path;

use crate::extract::{ContentExtractor, ExtractError, FastRecord};

pub struct ImageExtractor;

impl ContentExtractor for ImageExtractor {
    fn supports(&self, kind: &str) -> bool {
        kind == "image"
    }

    fn extract(&self, path: &Path) -> Result<FastRecord, ExtractError> {
        let file = std::fs::File::open(path)?;
        let mmap = unsafe { memmap2::Mmap::map(&file) }.map_err(std::io::Error::other)?;

        let content_hash = format!("{:016x}", xxhash_rust::xxh3::xxh3_64(&mmap));
        let magic_mime = infer::get(&mmap).map(|t| t.mime_type().to_string());

        let dimensions = image::ImageReader::new(Cursor::new(&mmap[..]))
            .with_guessed_format()
            .ok()
            .and_then(|r| r.into_dimensions().ok())
            .map(|(w, h)| format!("{}x{}", w, h));

        let phash = crate::hash::phash(&mmap);

        let exif_data = extract_exif(path);

        Ok(FastRecord {
            content_hash: Some(content_hash),
            dimensions,
            magic_mime,
            phash,
            exif_camera: exif_data.camera,
            exif_date: exif_data.date,
            exif_gps: exif_data.gps,
            exif_orientation: exif_data.orientation,
            ..Default::default()
        })
    }
}

struct ExifData {
    camera: Option<String>,
    date: Option<String>,
    gps: Option<String>,
    orientation: Option<String>,
}

fn extract_exif(path: &Path) -> ExifData {
    let file = match std::fs::File::open(path) {
        Ok(f) => f,
        Err(_) => {
            return ExifData {
                camera: None,
                date: None,
                gps: None,
                orientation: None,
            };
        }
    };
    let mut reader = BufReader::new(file);
    let exif = match exif::Reader::new().read_from_container(&mut reader) {
        Ok(e) => e,
        Err(_) => {
            return ExifData {
                camera: None,
                date: None,
                gps: None,
                orientation: None,
            };
        }
    };

    let camera = {
        let make = exif
            .get_field(exif::Tag::Make, exif::In::PRIMARY)
            .map(|f| f.display_value().to_string().trim().to_string());
        let model = exif
            .get_field(exif::Tag::Model, exif::In::PRIMARY)
            .map(|f| f.display_value().to_string().trim().to_string());
        match (make, model) {
            (Some(m), Some(md)) => {
                let m = m.trim_matches('"').to_string();
                let md = md.trim_matches('"').to_string();
                if md.starts_with(&m) {
                    Some(md)
                } else {
                    Some(format!("{} {}", m, md))
                }
            }
            (Some(m), None) => Some(m.trim_matches('"').to_string()),
            (None, Some(md)) => Some(md.trim_matches('"').to_string()),
            (None, None) => None,
        }
    };

    let date = exif
        .get_field(exif::Tag::DateTimeOriginal, exif::In::PRIMARY)
        .or_else(|| exif.get_field(exif::Tag::DateTime, exif::In::PRIMARY))
        .map(|f| f.display_value().to_string().trim_matches('"').to_string());

    let gps = extract_gps(&exif);

    let orientation = exif
        .get_field(exif::Tag::Orientation, exif::In::PRIMARY)
        .map(|f| f.display_value().to_string().trim_matches('"').to_string());

    ExifData {
        camera,
        date,
        gps,
        orientation,
    }
}

fn extract_gps(exif: &exif::Exif) -> Option<String> {
    let lat = exif.get_field(exif::Tag::GPSLatitude, exif::In::PRIMARY)?;
    let lat_ref = exif.get_field(exif::Tag::GPSLatitudeRef, exif::In::PRIMARY)?;
    let lon = exif.get_field(exif::Tag::GPSLongitude, exif::In::PRIMARY)?;
    let lon_ref = exif.get_field(exif::Tag::GPSLongitudeRef, exif::In::PRIMARY)?;

    let lat_val = parse_gps_coord(&lat.value)?;
    let lon_val = parse_gps_coord(&lon.value)?;

    let lat_sign = if lat_ref.display_value().to_string().contains('S') {
        -1.0
    } else {
        1.0
    };
    let lon_sign = if lon_ref.display_value().to_string().contains('W') {
        -1.0
    } else {
        1.0
    };

    Some(format!(
        "{:.6},{:.6}",
        lat_val * lat_sign,
        lon_val * lon_sign
    ))
}

fn parse_gps_coord(value: &exif::Value) -> Option<f64> {
    if let exif::Value::Rational(rationals) = value
        && rationals.len() >= 3
    {
        let deg = rationals[0].to_f64();
        let min = rationals[1].to_f64();
        let sec = rationals[2].to_f64();
        return Some(deg + min / 60.0 + sec / 3600.0);
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::extract::ContentExtractor;
    use tempfile::TempDir;

    fn create_test_png(path: &std::path::Path, w: u32, h: u32) {
        let img = image::RgbImage::new(w, h);
        img.save(path).unwrap();
    }

    fn create_test_jpeg(path: &std::path::Path, w: u32, h: u32) {
        let img = image::RgbImage::new(w, h);
        img.save(path).unwrap();
    }

    #[test]
    fn test_supports_image_only() {
        let ext = ImageExtractor;
        assert!(ext.supports("image"));
        assert!(!ext.supports("code"));
        assert!(!ext.supports("video"));
        assert!(!ext.supports("text"));
    }

    #[test]
    fn test_png_dimensions() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.png");
        create_test_png(&path, 100, 50);
        let result = ImageExtractor.extract(&path).unwrap();
        assert_eq!(result.dimensions, Some("100x50".into()));
    }

    #[test]
    fn test_jpeg_dimensions() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.jpg");
        create_test_jpeg(&path, 320, 240);
        let result = ImageExtractor.extract(&path).unwrap();
        assert_eq!(result.dimensions, Some("320x240".into()));
    }

    #[test]
    fn test_1x1_png() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("tiny.png");
        create_test_png(&path, 1, 1);
        let result = ImageExtractor.extract(&path).unwrap();
        assert_eq!(result.dimensions, Some("1x1".into()));
    }

    #[test]
    fn test_large_dimensions() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("large.png");
        create_test_png(&path, 4000, 3000);
        let result = ImageExtractor.extract(&path).unwrap();
        assert_eq!(result.dimensions, Some("4000x3000".into()));
    }

    #[test]
    fn test_content_hash_populated() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.png");
        create_test_png(&path, 10, 10);
        let result = ImageExtractor.extract(&path).unwrap();
        assert!(result.content_hash.is_some());
        assert_eq!(result.content_hash.unwrap().len(), 16);
    }

    #[test]
    fn test_content_hash_deterministic() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.png");
        create_test_png(&path, 10, 10);
        let h1 = ImageExtractor.extract(&path).unwrap().content_hash;
        let h2 = ImageExtractor.extract(&path).unwrap().content_hash;
        assert_eq!(h1, h2);
    }

    #[test]
    fn test_different_images_different_hashes() {
        let dir = TempDir::new().unwrap();
        let p1 = dir.path().join("a.png");
        let p2 = dir.path().join("b.png");
        create_test_png(&p1, 10, 10);
        create_test_png(&p2, 20, 20);
        let h1 = ImageExtractor.extract(&p1).unwrap().content_hash;
        let h2 = ImageExtractor.extract(&p2).unwrap().content_hash;
        assert_ne!(h1, h2);
    }

    #[test]
    fn test_magic_mime_for_png() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.png");
        create_test_png(&path, 10, 10);
        let result = ImageExtractor.extract(&path).unwrap();
        assert!(result.magic_mime.is_some());
        assert!(result.magic_mime.unwrap().contains("png"));
    }

    #[test]
    fn test_no_line_count_for_image() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.png");
        create_test_png(&path, 10, 10);
        let result = ImageExtractor.extract(&path).unwrap();
        assert!(result.line_count.is_none());
        assert!(result.word_count.is_none());
        assert!(result.language.is_none());
    }

    #[test]
    fn test_no_video_fields_for_image() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.png");
        create_test_png(&path, 10, 10);
        let result = ImageExtractor.extract(&path).unwrap();
        assert!(result.video_codec.is_none());
        assert!(result.audio_codec.is_none());
        assert!(result.fps.is_none());
        assert!(result.has_audio.is_none());
        assert!(result.duration_s.is_none());
    }

    #[test]
    fn test_synthetic_png_no_exif() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.png");
        create_test_png(&path, 10, 10);
        let result = ImageExtractor.extract(&path).unwrap();
        assert!(result.exif_camera.is_none());
        assert!(result.exif_date.is_none());
        assert!(result.exif_gps.is_none());
    }

    #[test]
    fn test_phash_populated_for_image() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.png");
        create_test_png(&path, 100, 100);
        let result = ImageExtractor.extract(&path).unwrap();
        assert!(result.phash.is_some());
    }

    #[test]
    fn test_phash_deterministic_via_extractor() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.png");
        create_test_png(&path, 50, 50);
        let h1 = ImageExtractor.extract(&path).unwrap().phash;
        let h2 = ImageExtractor.extract(&path).unwrap().phash;
        assert_eq!(h1, h2);
    }

    #[test]
    fn test_io_error_on_missing_file() {
        let result = ImageExtractor.extract(Path::new("/nonexistent/image.png"));
        assert!(result.is_err());
    }
}
