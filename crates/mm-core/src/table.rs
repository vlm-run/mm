use std::sync::Arc;

use arrow::array::{
    ArrayRef, BooleanBuilder, RecordBatch, StringBuilder, TimestampMicrosecondBuilder,
    UInt16Builder, UInt32Builder, UInt64Builder,
};

use crate::meta::FileEntry;
use crate::schema::l0_schema;

pub fn build_l0_record_batch(
    entries: &[FileEntry],
) -> Result<RecordBatch, arrow::error::ArrowError> {
    let cap = entries.len();

    let mut path_builder = StringBuilder::with_capacity(cap, cap * 64);
    let mut name_builder = StringBuilder::with_capacity(cap, cap * 32);
    let mut stem_builder = StringBuilder::with_capacity(cap, cap * 32);
    let mut ext_builder = StringBuilder::with_capacity(cap, cap * 8);
    let mut size_builder = UInt64Builder::with_capacity(cap);
    let mut modified_builder = TimestampMicrosecondBuilder::with_capacity(cap);
    let mut created_builder = TimestampMicrosecondBuilder::with_capacity(cap);
    let mut mime_builder = StringBuilder::with_capacity(cap, cap * 32);
    let mut kind_builder = StringBuilder::with_capacity(cap, cap * 8);
    let mut is_binary_builder = BooleanBuilder::with_capacity(cap);
    let mut depth_builder = UInt16Builder::with_capacity(cap);
    let mut parent_builder = StringBuilder::with_capacity(cap, cap * 48);
    let mut width_builder = UInt32Builder::with_capacity(cap);
    let mut height_builder = UInt32Builder::with_capacity(cap);

    for entry in entries {
        path_builder.append_value(entry.path.as_str());
        name_builder.append_value(entry.name.as_str());
        stem_builder.append_value(entry.stem.as_str());
        ext_builder.append_value(entry.ext.as_str());
        size_builder.append_value(entry.size);
        modified_builder.append_value(entry.modified_epoch_us);
        created_builder.append_value(entry.created_epoch_us);
        mime_builder.append_value(entry.mime.as_str());
        kind_builder.append_value(entry.kind.to_string());
        is_binary_builder.append_value(entry.is_binary);
        depth_builder.append_value(entry.depth);
        parent_builder.append_value(entry.parent.as_str());
        match entry.width {
            Some(w) => width_builder.append_value(w),
            None => width_builder.append_null(),
        }
        match entry.height {
            Some(h) => height_builder.append_value(h),
            None => height_builder.append_null(),
        }
    }

    let columns: Vec<ArrayRef> = vec![
        Arc::new(path_builder.finish()),
        Arc::new(name_builder.finish()),
        Arc::new(stem_builder.finish()),
        Arc::new(ext_builder.finish()),
        Arc::new(size_builder.finish()),
        Arc::new(modified_builder.finish()),
        Arc::new(created_builder.finish()),
        Arc::new(mime_builder.finish()),
        Arc::new(kind_builder.finish()),
        Arc::new(is_binary_builder.finish()),
        Arc::new(depth_builder.finish()),
        Arc::new(parent_builder.finish()),
        Arc::new(width_builder.finish()),
        Arc::new(height_builder.finish()),
    ];

    RecordBatch::try_new(Arc::new(l0_schema()), columns)
}

pub fn write_parquet(
    batch: &RecordBatch,
    path: &std::path::Path,
) -> Result<(), Box<dyn std::error::Error>> {
    let file = std::fs::File::create(path)?;
    let props = parquet::file::properties::WriterProperties::builder()
        .set_compression(parquet::basic::Compression::ZSTD(
            parquet::basic::ZstdLevel::try_new(3)?,
        ))
        .build();
    let mut writer = parquet::arrow::ArrowWriter::try_new(file, batch.schema(), Some(props))?;
    writer.write(batch)?;
    writer.close()?;
    Ok(())
}

pub fn read_parquet(path: &std::path::Path) -> Result<RecordBatch, Box<dyn std::error::Error>> {
    let file = std::fs::File::open(path)?;
    let reader =
        parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder::try_new(file)?.build()?;
    let batches: Vec<RecordBatch> = reader.collect::<Result<Vec<_>, _>>()?;
    if batches.is_empty() {
        return Err("Empty parquet file".into());
    }
    arrow::compute::concat_batches(&batches[0].schema(), &batches).map_err(|e| e.into())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::meta::enrich_image_dimensions;
    use crate::walk::scan_directory;
    use arrow::array::{Array, AsArray};
    use std::fs;
    use tempfile::TempDir;

    #[test]
    fn test_build_record_batch() {
        let dir = TempDir::new().unwrap();
        fs::write(dir.path().join("test.py"), "x = 1").unwrap();
        fs::write(dir.path().join("lib.rs"), "fn main() {}").unwrap();

        let entries = scan_directory(dir.path(), None, false);
        let batch = build_l0_record_batch(&entries).unwrap();

        assert_eq!(batch.num_rows(), 2);
        assert_eq!(batch.num_columns(), 14);
    }

    #[test]
    fn test_width_height_null_for_non_images() {
        let dir = TempDir::new().unwrap();
        fs::write(dir.path().join("test.py"), "x = 1").unwrap();

        let entries = scan_directory(dir.path(), None, false);
        let batch = build_l0_record_batch(&entries).unwrap();

        let width_col = batch.column_by_name("width").unwrap();
        let height_col = batch.column_by_name("height").unwrap();
        assert!(
            width_col
                .as_primitive::<arrow::datatypes::UInt32Type>()
                .is_null(0)
        );
        assert!(
            height_col
                .as_primitive::<arrow::datatypes::UInt32Type>()
                .is_null(0)
        );
    }

    #[test]
    fn test_width_height_populated_for_images() {
        let dir = TempDir::new().unwrap();
        create_minimal_png(dir.path().join("test.png"));

        let mut entries = scan_directory(dir.path(), None, false);
        enrich_image_dimensions(&mut entries, dir.path());
        let batch = build_l0_record_batch(&entries).unwrap();

        let width_col = batch.column_by_name("width").unwrap();
        let height_col = batch.column_by_name("height").unwrap();
        let w = width_col.as_primitive::<arrow::datatypes::UInt32Type>();
        let h = height_col.as_primitive::<arrow::datatypes::UInt32Type>();
        assert!(!w.is_null(0));
        assert!(!h.is_null(0));
        assert_eq!(w.value(0), 1);
        assert_eq!(h.value(0), 1);
    }

    #[test]
    fn test_parquet_roundtrip() {
        let dir = TempDir::new().unwrap();
        fs::write(dir.path().join("test.py"), "x = 1").unwrap();

        let entries = scan_directory(dir.path(), None, false);
        let batch = build_l0_record_batch(&entries).unwrap();

        let parquet_path = dir.path().join("index.parquet");
        write_parquet(&batch, &parquet_path).unwrap();

        let read_back = read_parquet(&parquet_path).unwrap();
        assert_eq!(read_back.num_rows(), batch.num_rows());
        assert_eq!(read_back.num_columns(), batch.num_columns());
    }

    #[test]
    fn test_parquet_roundtrip_with_image_dims() {
        let dir = TempDir::new().unwrap();
        create_minimal_png(dir.path().join("img.png"));
        fs::write(dir.path().join("code.py"), "x = 1").unwrap();

        let mut entries = scan_directory(dir.path(), None, false);
        enrich_image_dimensions(&mut entries, dir.path());
        let batch = build_l0_record_batch(&entries).unwrap();

        let parquet_path = dir.path().join("index.parquet");
        write_parquet(&batch, &parquet_path).unwrap();
        let read_back = read_parquet(&parquet_path).unwrap();

        assert_eq!(read_back.num_rows(), 2);
        assert_eq!(read_back.num_columns(), 14);

        let w = read_back.column_by_name("width").unwrap();
        let h = read_back.column_by_name("height").unwrap();
        let wa = w.as_primitive::<arrow::datatypes::UInt32Type>();
        let ha = h.as_primitive::<arrow::datatypes::UInt32Type>();

        let img_idx = {
            let names = read_back.column_by_name("name").unwrap();
            let names = names.as_string::<i32>();
            (0..read_back.num_rows())
                .find(|&i| names.value(i).ends_with(".png"))
                .unwrap()
        };

        assert!(!wa.is_null(img_idx));
        assert_eq!(wa.value(img_idx), 1);
        assert_eq!(ha.value(img_idx), 1);
    }

    fn create_minimal_png(path: std::path::PathBuf) {
        let img = image::RgbImage::new(1, 1);
        img.save(&path).unwrap();
    }
}
