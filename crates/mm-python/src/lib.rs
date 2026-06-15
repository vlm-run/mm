mod refs;

use std::path::PathBuf;

use arrow::array::RecordBatch;
use arrow::ipc::writer::StreamWriter;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBytes};

use mm_core::extract::ContentExtractor;
use mm_core::extract::MetadataRecord;
use mm_core::extractors::{
    AudioExtractor, CodeExtractor, DocumentExtractor, ImageExtractor, VideoExtractor,
};
use mm_core::meta::FileKind;

#[pyclass]
#[derive(Clone)]
struct Scanner {
    root: PathBuf,
    n_threads: Option<usize>,
    no_ignore: bool,
    entries: Vec<mm_core::FileEntry>,
    batch: Option<RecordBatch>,
}

#[pymethods]
impl Scanner {
    #[new]
    #[pyo3(signature = (root, n_threads=None, no_ignore=false))]
    fn new(root: String, n_threads: Option<usize>, no_ignore: bool) -> Self {
        Scanner {
            root: PathBuf::from(root),
            n_threads,
            no_ignore,
            entries: Vec::new(),
            batch: None,
        }
    }

    fn scan(&mut self) -> PyResult<usize> {
        self.entries = mm_core::scan_directory(&self.root, self.n_threads, self.no_ignore);
        mm_core::enrich_image_dimensions(&mut self.entries, &self.root);
        let count = self.entries.len();
        let batch = mm_core::build_metadata_batch(&self.entries)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        self.batch = Some(batch);
        Ok(count)
    }

    fn num_files(&self) -> usize {
        self.entries.len()
    }

    fn to_arrow(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let batch = self
            .batch
            .as_ref()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("Call scan() first"))?;

        export_batch_to_pyarrow(py, batch)
    }

    fn write_parquet(&self, path: String) -> PyResult<()> {
        let batch = self
            .batch
            .as_ref()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("Call scan() first"))?;
        mm_core::table::write_parquet(batch, &PathBuf::from(path))
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))
    }

    fn to_json(&self) -> PyResult<String> {
        let batch = self
            .batch
            .as_ref()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("Call scan() first"))?;
        mm_core::format::record_batch_to_json(batch)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
    }

    /// Fast JSON: serialize entries directly, bypassing Arrow entirely.
    #[pyo3(signature = (kind=None, ext=None, min_size=None, max_size=None, name=None, limit=None, sort_by=None, descending=false))]
    #[allow(clippy::too_many_arguments)]
    fn to_json_fast(
        &self,
        kind: Option<&str>,
        ext: Option<&str>,
        min_size: Option<u64>,
        max_size: Option<u64>,
        name: Option<&str>,
        limit: Option<usize>,
        sort_by: Option<&str>,
        descending: bool,
    ) -> PyResult<String> {
        if self.entries.is_empty() {
            return Err(pyo3::exceptions::PyRuntimeError::new_err(
                "Call scan() first",
            ));
        }
        Ok(mm_core::entries_to_json_filtered(
            &self.entries,
            kind,
            ext,
            min_size,
            max_size,
            name,
            limit,
            sort_by,
            descending,
        ))
    }

    fn to_markdown(&self) -> PyResult<String> {
        let batch = self
            .batch
            .as_ref()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("Call scan() first"))?;
        Ok(mm_core::format::record_batch_to_markdown(batch))
    }

    fn to_csv(&self) -> PyResult<String> {
        let batch = self
            .batch
            .as_ref()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("Call scan() first"))?;
        Ok(mm_core::format::record_batch_to_csv(batch, b','))
    }

    fn to_tsv(&self) -> PyResult<String> {
        let batch = self
            .batch
            .as_ref()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("Call scan() first"))?;
        Ok(mm_core::format::record_batch_to_csv(batch, b'\t'))
    }

    fn to_lines(&self) -> PyResult<String> {
        let batch = self
            .batch
            .as_ref()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("Call scan() first"))?;
        Ok(mm_core::format::record_batch_to_lines(batch))
    }

    /// Newline-delimited paths, bypassing Arrow.
    #[pyo3(signature = (kind=None, ext=None, min_size=None, max_size=None, name=None, limit=None, sort_by=None, descending=false))]
    #[allow(clippy::too_many_arguments)]
    fn to_lines_fast(
        &self,
        kind: Option<&str>,
        ext: Option<&str>,
        min_size: Option<u64>,
        max_size: Option<u64>,
        name: Option<&str>,
        limit: Option<usize>,
        sort_by: Option<&str>,
        descending: bool,
    ) -> PyResult<String> {
        if self.entries.is_empty() {
            return Err(pyo3::exceptions::PyRuntimeError::new_err(
                "Call scan() first",
            ));
        }
        Ok(mm_core::format::entries_to_lines_filtered(
            &self.entries,
            kind,
            ext,
            min_size,
            max_size,
            name,
            limit,
            sort_by,
            descending,
        ))
    }

    fn extract_metadata(&self, path: String) -> PyResult<MetadataResult> {
        let p = PathBuf::from(&path);

        let entry = self.entries.iter().find(|e| e.path.as_str() == path);
        let kind = entry.map(|e| e.kind).unwrap_or(FileKind::Other);

        let record = match kind {
            FileKind::Code | FileKind::Text | FileKind::Config => {
                CodeExtractor.extract(&self.root.join(&p))
            }
            FileKind::Image => ImageExtractor.extract(&self.root.join(&p)),
            FileKind::Video => VideoExtractor.extract(&self.root.join(&p)),
            FileKind::Audio => AudioExtractor.extract(&self.root.join(&p)),
            FileKind::Document => DocumentExtractor.extract(&self.root.join(&p)),
            _ => Ok(MetadataRecord::default()),
        }
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        Ok(MetadataResult {
            content_hash: record.content_hash,
            text_preview: record.text_preview,
            line_count: record.line_count,
            word_count: record.word_count,
            language: record.language,
            dimensions: record.dimensions,
            pages: record.pages,
            duration_s: record.duration_s,
            magic_mime: record.magic_mime,
            exif_camera: record.exif_camera,
            exif_date: record.exif_date,
            exif_gps: record.exif_gps,
            exif_orientation: record.exif_orientation,
            video_codec: record.video_codec,
            audio_codec: record.audio_codec,
            fps: record.fps,
            has_audio: record.has_audio,
            phash: record.phash,
        })
    }

    /// Count files, bytes, lines, tokens. Returns JSON.
    #[pyo3(signature = (kind=None))]
    fn wc(&self, kind: Option<&str>) -> PyResult<String> {
        let filtered = mm_core::filter_entries(
            &self.entries,
            kind,
            None,
            None,
            None,
            None,
            None,
            None,
            false,
        );
        let result = mm_core::wc::count_entries(&filtered, &self.root);
        Ok(mm_core::wc::wc_to_json(&result))
    }

    fn __repr__(&self) -> String {
        format!(
            "Scanner(root='{}', files={})",
            self.root.display(),
            self.entries.len()
        )
    }
}

#[pyclass]
#[derive(Clone)]
struct MetadataResult {
    #[pyo3(get)]
    content_hash: Option<String>,
    #[pyo3(get)]
    text_preview: Option<String>,
    #[pyo3(get)]
    line_count: Option<u32>,
    #[pyo3(get)]
    word_count: Option<u32>,
    #[pyo3(get)]
    language: Option<String>,
    #[pyo3(get)]
    dimensions: Option<String>,
    #[pyo3(get)]
    pages: Option<u32>,
    #[pyo3(get)]
    duration_s: Option<f64>,
    #[pyo3(get)]
    magic_mime: Option<String>,
    #[pyo3(get)]
    exif_camera: Option<String>,
    #[pyo3(get)]
    exif_date: Option<String>,
    #[pyo3(get)]
    exif_gps: Option<String>,
    #[pyo3(get)]
    exif_orientation: Option<String>,
    #[pyo3(get)]
    video_codec: Option<String>,
    #[pyo3(get)]
    audio_codec: Option<String>,
    #[pyo3(get)]
    fps: Option<f64>,
    #[pyo3(get)]
    has_audio: Option<bool>,
    #[pyo3(get)]
    phash: Option<u64>,
}

#[pymethods]
impl MetadataResult {
    fn __repr__(&self) -> String {
        format!(
            "MetadataResult(hash={:?}, lines={:?}, lang={:?}, dims={:?}, phash={:?})",
            self.content_hash, self.line_count, self.language, self.dimensions, self.phash
        )
    }
}

fn export_batch_to_pyarrow(py: Python<'_>, batch: &RecordBatch) -> PyResult<Py<PyAny>> {
    let mut buf = Vec::new();
    {
        let mut writer = StreamWriter::try_new(&mut buf, &batch.schema())
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        writer
            .write(batch)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        writer
            .finish()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
    }

    let py_bytes = PyBytes::new(py, &buf);
    let pa = py.import("pyarrow")?;
    let ipc = pa.getattr("ipc")?;
    let reader = ipc.call_method1("open_stream", (py_bytes,))?;
    let table = reader.call_method0("read_all")?;
    Ok(table.into_pyobject(py)?.into_any().unbind())
}

/// Hamming distance between two perceptual hashes.
/// Returns the number of differing bits (0 = identical, <8 = near-duplicate).
#[pyfunction]
fn hamming_distance(a: u64, b: u64) -> u32 {
    mm_core::hamming_distance(a, b)
}

/// Fast xxh3 content hash of a file via mmap. Returns 16-char hex string.
#[pyfunction]
fn content_hash(path: String) -> PyResult<Option<String>> {
    let p = std::path::Path::new(&path);
    Ok(mm_core::hash::full_hash_mmap(p).map(|h| format!("{:016x}", h)))
}

/// Hash a directory listing (sorted name:mtime:size). Returns 16-char hex string.
/// Deterministic — same files with same mtimes produce the same hash.
#[pyfunction]
fn directory_hash(path: String) -> PyResult<Option<String>> {
    let p = std::path::Path::new(&path);
    Ok(mm_core::directory_hash(p).map(|h| format!("{:016x}", h)))
}

/// Perceptual hash of an image file. Returns 64-bit hash as integer.
#[pyfunction]
fn perceptual_hash(path: String) -> PyResult<Option<u64>> {
    let p = std::path::Path::new(&path);
    let data = std::fs::read(p).map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;
    Ok(mm_core::hash::phash(&data))
}

/// Resize image to max_width (keeping aspect ratio).
///
/// Returns a dict with keys: base64, mime, width, height.
/// JPEG quality defaults to 85; pass `quality` to override.
#[pyfunction]
#[pyo3(signature = (path, max_width, quality=85))]
fn resize_image(py: Python<'_>, path: String, max_width: u32, quality: u8) -> PyResult<Py<PyAny>> {
    let p = std::path::Path::new(&path);
    let result = mm_core::serde::image::resize_and_encode_with_quality(p, max_width, quality)
        .map_err(pyo3::exceptions::PyRuntimeError::new_err)?;
    let dict = pyo3::types::PyDict::new(py);
    dict.set_item("base64", &result.base64)?;
    dict.set_item("mime", &result.mime)?;
    dict.set_item("width", result.width)?;
    dict.set_item("height", result.height)?;
    Ok(dict.into_pyobject(py)?.into_any().unbind())
}

/// Tile image into tile_size squares.
///
/// Returns a list of dicts, one per tile.
/// JPEG quality defaults to 85; pass `quality` to override.
#[pyfunction]
#[pyo3(signature = (path, tile_size, quality=85))]
fn tile_image(py: Python<'_>, path: String, tile_size: u32, quality: u8) -> PyResult<Py<PyAny>> {
    let p = std::path::Path::new(&path);
    let tiles = mm_core::serde::image::tile_and_encode_with_quality(p, tile_size, quality)
        .map_err(pyo3::exceptions::PyRuntimeError::new_err)?;
    let list = pyo3::types::PyList::empty(py);
    for tile in &tiles {
        let dict = pyo3::types::PyDict::new(py);
        dict.set_item("base64", &tile.base64)?;
        dict.set_item("mime", &tile.mime)?;
        dict.set_item("col", tile.col)?;
        dict.set_item("row", tile.row)?;
        dict.set_item("total_cols", tile.total_cols)?;
        dict.set_item("total_rows", tile.total_rows)?;
        dict.set_item("width", tile.width)?;
        dict.set_item("height", tile.height)?;
        list.append(dict)?;
    }
    Ok(list.into_pyobject(py)?.into_any().unbind())
}

/// Serialize image as Gemini inline_data Part JSON string.
#[pyfunction]
fn gemini_image_part(path: String) -> PyResult<String> {
    let p = std::path::Path::new(&path);
    mm_core::serde::gemini::image_part_json(p).map_err(pyo3::exceptions::PyRuntimeError::new_err)
}

/// Serialize video as Gemini inline_data Part JSON strings (with chunking).
#[pyfunction]
#[pyo3(signature = (path, max_seconds=120, overlap=10))]
fn gemini_video_parts(path: String, max_seconds: u32, overlap: u32) -> PyResult<Vec<String>> {
    let p = std::path::Path::new(&path);
    mm_core::serde::gemini::video_parts_json(p, max_seconds, overlap)
        .map_err(pyo3::exceptions::PyRuntimeError::new_err)
}

/// Serialize document as Gemini inline_data Part JSON string.
#[pyfunction]
fn gemini_document_part(path: String) -> PyResult<String> {
    let p = std::path::Path::new(&path);
    mm_core::serde::gemini::document_part_json(p).map_err(pyo3::exceptions::PyRuntimeError::new_err)
}

#[pyclass]
#[derive(Clone)]
struct OfficeMetadata {
    #[pyo3(get)]
    author: String,
    #[pyo3(get)]
    title: String,
    #[pyo3(get)]
    subject: String,
    #[pyo3(get)]
    description: String,
    #[pyo3(get)]
    keywords: Vec<String>,
    #[pyo3(get)]
    created: String,
    #[pyo3(get)]
    modified: String,
    #[pyo3(get)]
    pages: Option<usize>,
}

#[pymethods]
impl OfficeMetadata {
    fn __repr__(&self) -> String {
        let pages = self
            .pages
            .map(|p| p.to_string())
            .unwrap_or_else(|| "None".to_string());
        format!(
            "OfficeMetadata(title={:?}, author={:?}, pages={})",
            self.title, self.author, pages
        )
    }
}

#[pyclass]
#[derive(Clone)]
struct OfficeDoc {
    #[pyo3(get)]
    content: String,
    #[pyo3(get)]
    meta: OfficeMetadata,
}

#[pymethods]
impl OfficeDoc {
    fn __repr__(&self) -> String {
        let pages = self
            .meta
            .pages
            .map(|p| p.to_string())
            .unwrap_or_else(|| "None".to_string());
        format!(
            "OfficeDoc(title={:?}, author={:?}, pages={}, content_len={})",
            self.meta.title,
            self.meta.author,
            pages,
            self.content.len()
        )
    }
}

fn meta_to_py(m: mm_core::office::OfficeMetadata) -> OfficeMetadata {
    OfficeMetadata {
        author: m.author,
        title: m.title,
        subject: m.subject,
        description: m.description,
        keywords: m.keywords,
        created: m.created,
        modified: m.modified,
        pages: m.pages,
    }
}

/// Extract just the content of a docx/pptx/xlsx/odt/ods/odp/doc/pdf.
#[pyfunction]
fn office_content(path: String) -> PyResult<String> {
    let p = std::path::Path::new(&path);
    mm_core::office::content(p)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
}

/// Extract just the metadata of a docx/pptx/xlsx/odt/ods/odp/doc/pdf.
#[pyfunction]
fn office_metadata(path: String) -> PyResult<OfficeMetadata> {
    let p = std::path::Path::new(&path);
    let m = mm_core::office::metadata(p)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
    Ok(meta_to_py(m))
}

/// Parse a docx/pptx/xlsx/odt/ods/odp/doc/pdf and return content + metadata.
#[pyfunction]
fn office_parse_full(path: String) -> PyResult<OfficeDoc> {
    let p = std::path::Path::new(&path);
    let doc = mm_core::office::parse_full(p)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
    Ok(OfficeDoc {
        content: doc.content,
        meta: meta_to_py(doc.metadata),
    })
}

/// Convert a supported office document to PDF and write it to `output`.
/// Returns the output path.
#[pyfunction]
fn office_to_pdf(input: String, output: String) -> PyResult<String> {
    let inp = std::path::Path::new(&input);
    let out = std::path::Path::new(&output);
    let p = mm_core::office::convert_to_pdf(inp, out)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
    p.to_str()
        .map(|s| s.to_string())
        .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("non-utf8 output path"))
}

#[pymodule]
#[pyo3(name = "_mm")]
fn mm_module(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Scanner>()?;
    m.add_class::<MetadataResult>()?;
    m.add_class::<OfficeDoc>()?;
    m.add_class::<OfficeMetadata>()?;
    m.add_function(wrap_pyfunction!(office_content, m)?)?;
    m.add_function(wrap_pyfunction!(office_metadata, m)?)?;
    m.add_function(wrap_pyfunction!(office_parse_full, m)?)?;
    m.add_function(wrap_pyfunction!(office_to_pdf, m)?)?;
    m.add_function(wrap_pyfunction!(hamming_distance, m)?)?;
    m.add_function(wrap_pyfunction!(content_hash, m)?)?;
    m.add_function(wrap_pyfunction!(directory_hash, m)?)?;
    m.add_function(wrap_pyfunction!(perceptual_hash, m)?)?;
    // Serde functions
    m.add_function(wrap_pyfunction!(resize_image, m)?)?;
    m.add_function(wrap_pyfunction!(tile_image, m)?)?;
    m.add_function(wrap_pyfunction!(gemini_image_part, m)?)?;
    m.add_function(wrap_pyfunction!(gemini_video_parts, m)?)?;
    m.add_function(wrap_pyfunction!(gemini_document_part, m)?)?;
    refs::register(m)?;
    Ok(())
}
