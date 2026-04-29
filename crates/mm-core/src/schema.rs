use arrow::datatypes::{DataType, Field, Schema, TimeUnit};
use std::sync::Arc;

pub fn metadata_schema() -> Schema {
    Schema::new(vec![
        Field::new("path", DataType::Utf8, false),
        Field::new("name", DataType::Utf8, false),
        Field::new("stem", DataType::Utf8, false),
        Field::new("ext", DataType::Utf8, false),
        Field::new("size", DataType::UInt64, false),
        Field::new(
            "modified",
            DataType::Timestamp(TimeUnit::Microsecond, None),
            false,
        ),
        Field::new(
            "created",
            DataType::Timestamp(TimeUnit::Microsecond, None),
            false,
        ),
        Field::new("mime", DataType::Utf8, false),
        Field::new("kind", DataType::Utf8, false),
        Field::new("is_binary", DataType::Boolean, false),
        Field::new("depth", DataType::UInt16, false),
        Field::new("parent", DataType::Utf8, false),
        Field::new("width", DataType::UInt32, true),
        Field::new("height", DataType::UInt32, true),
    ])
}

pub fn metadata_record_schema() -> Schema {
    let mut fields = metadata_schema().fields().to_vec();
    fields.extend(vec![
        Arc::new(Field::new("content_hash", DataType::Utf8, true)),
        Arc::new(Field::new("text_preview", DataType::Utf8, true)),
        Arc::new(Field::new("line_count", DataType::UInt32, true)),
        Arc::new(Field::new("word_count", DataType::UInt32, true)),
        Arc::new(Field::new("language", DataType::Utf8, true)),
        Arc::new(Field::new("dimensions", DataType::Utf8, true)),
        Arc::new(Field::new("pages", DataType::UInt32, true)),
        Arc::new(Field::new("duration_s", DataType::Float64, true)),
        Arc::new(Field::new("magic_mime", DataType::Utf8, true)),
        Arc::new(Field::new("exif_camera", DataType::Utf8, true)),
        Arc::new(Field::new("exif_date", DataType::Utf8, true)),
        Arc::new(Field::new("exif_gps", DataType::Utf8, true)),
        Arc::new(Field::new("exif_orientation", DataType::Utf8, true)),
        Arc::new(Field::new("video_codec", DataType::Utf8, true)),
        Arc::new(Field::new("audio_codec", DataType::Utf8, true)),
        Arc::new(Field::new("fps", DataType::Float64, true)),
        Arc::new(Field::new("has_audio", DataType::Boolean, true)),
        Arc::new(Field::new("phash", DataType::UInt64, true)),
    ]);
    Schema::new(fields)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_metadata_schema_field_count() {
        let schema = metadata_schema();
        assert_eq!(schema.fields().len(), 14);
    }

    #[test]
    fn test_metadata_has_dimension_columns() {
        let schema = metadata_schema();
        assert!(schema.field_with_name("width").is_ok());
        assert!(schema.field_with_name("height").is_ok());
        let w = schema.field_with_name("width").unwrap();
        assert_eq!(*w.data_type(), DataType::UInt32);
        assert!(w.is_nullable());
    }

    #[test]
    fn test_metadata_record_schema_extends_metadata() {
        let basic = metadata_schema();
        let full = metadata_record_schema();
        assert!(full.fields().len() > basic.fields().len());
        assert_eq!(full.fields().len(), 32);
    }

    #[test]
    fn test_metadata_record_has_exif_columns() {
        let full = metadata_record_schema();
        assert!(full.field_with_name("exif_camera").is_ok());
        assert!(full.field_with_name("exif_date").is_ok());
        assert!(full.field_with_name("exif_gps").is_ok());
        assert!(full.field_with_name("exif_orientation").is_ok());
    }

    #[test]
    fn test_metadata_record_has_video_columns() {
        let full = metadata_record_schema();
        assert!(full.field_with_name("video_codec").is_ok());
        assert!(full.field_with_name("audio_codec").is_ok());
        assert!(full.field_with_name("fps").is_ok());
        assert!(full.field_with_name("has_audio").is_ok());
    }
}
