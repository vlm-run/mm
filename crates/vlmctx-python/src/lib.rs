use std::path::PathBuf;

use arrow::array::RecordBatch;
use arrow::ipc::writer::StreamWriter;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

use vlmctx_core::extract::ContentExtractor;
use vlmctx_core::extract::L1Record;
use vlmctx_core::extractors::{CodeExtractor, ImageExtractor, VideoExtractor};
use vlmctx_core::meta::FileKind;

#[pyclass]
#[derive(Clone)]
struct Scanner {
    root: PathBuf,
    n_threads: Option<usize>,
    entries: Vec<vlmctx_core::FileEntry>,
    batch: Option<RecordBatch>,
}

#[pymethods]
impl Scanner {
    #[new]
    #[pyo3(signature = (root, n_threads=None))]
    fn new(root: String, n_threads: Option<usize>) -> Self {
        Scanner {
            root: PathBuf::from(root),
            n_threads,
            entries: Vec::new(),
            batch: None,
        }
    }

    fn scan(&mut self) -> PyResult<usize> {
        self.entries = vlmctx_core::scan_directory(&self.root, self.n_threads);
        vlmctx_core::enrich_image_dimensions(&mut self.entries, &self.root);
        let count = self.entries.len();
        let batch = vlmctx_core::build_l0_record_batch(&self.entries)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        self.batch = Some(batch);
        Ok(count)
    }

    fn num_files(&self) -> usize {
        self.entries.len()
    }

    fn to_arrow(&self, py: Python<'_>) -> PyResult<PyObject> {
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
        vlmctx_core::table::write_parquet(batch, &PathBuf::from(path))
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))
    }

    fn to_json(&self) -> PyResult<String> {
        let batch = self
            .batch
            .as_ref()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("Call scan() first"))?;
        vlmctx_core::format::record_batch_to_json(batch)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
    }

    fn to_markdown(&self) -> PyResult<String> {
        let batch = self
            .batch
            .as_ref()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("Call scan() first"))?;
        Ok(vlmctx_core::format::record_batch_to_markdown(batch))
    }

    fn to_csv(&self) -> PyResult<String> {
        let batch = self
            .batch
            .as_ref()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("Call scan() first"))?;
        Ok(vlmctx_core::format::record_batch_to_csv(batch, b','))
    }

    fn to_tsv(&self) -> PyResult<String> {
        let batch = self
            .batch
            .as_ref()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("Call scan() first"))?;
        Ok(vlmctx_core::format::record_batch_to_csv(batch, b'\t'))
    }

    fn to_lines(&self) -> PyResult<String> {
        let batch = self
            .batch
            .as_ref()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("Call scan() first"))?;
        Ok(vlmctx_core::format::record_batch_to_lines(batch))
    }

    fn extract_l1(&self, path: String) -> PyResult<L1Result> {
        let p = PathBuf::from(&path);

        let entry = self.entries.iter().find(|e| e.path.as_str() == path);
        let kind = entry.map(|e| e.kind).unwrap_or(FileKind::Other);

        let record = match kind {
            FileKind::Code | FileKind::Text | FileKind::Config => {
                CodeExtractor.extract(&self.root.join(&p))
            }
            FileKind::Image => ImageExtractor.extract(&self.root.join(&p)),
            FileKind::Video | FileKind::Audio => VideoExtractor.extract(&self.root.join(&p)),
            _ => Ok(L1Record::default()),
        }
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        Ok(L1Result {
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
        })
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
struct L1Result {
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
}

#[pymethods]
impl L1Result {
    fn __repr__(&self) -> String {
        format!(
            "L1Result(hash={:?}, lines={:?}, lang={:?}, dims={:?})",
            self.content_hash, self.line_count, self.language, self.dimensions
        )
    }
}

fn export_batch_to_pyarrow(py: Python<'_>, batch: &RecordBatch) -> PyResult<PyObject> {
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

#[pymodule]
#[pyo3(name = "_vlmctx")]
fn vlmctx_module(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Scanner>()?;
    m.add_class::<L1Result>()?;
    Ok(())
}
