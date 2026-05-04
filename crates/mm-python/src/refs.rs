//! PyO3 bindings for [`mm_core::refs::Context`].
//!
//! Exposes `PyContext` to Python as `_mm.PyContext`. The Python wrapper in
//! `mm.context.Context` pre-classifies user objects (Path, PIL.Image, bytes,
//! URL) and calls [`PyContext::put`] with primitive values; Rust owns the
//! storage, ref generation, lookup, and rendering.
//!
//! In-memory Python objects are kept alive on the Rust side in a parallel
//! `Vec<Option<Py<PyAny>>>` indexed by item position, so [`PyContext::get`]
//! returns the exact object the caller passed in — no copy, no rehydrate.

use compact_str::CompactString;
use mm_core::meta::FileKind;
use mm_core::refs::{Context, ItemSource, MetaMap, MetaValue, kind_from_name, uuid7};
use pyo3::exceptions::{PyKeyError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use serde_json::Value as JsonValue;
use std::collections::HashMap;

pyo3::create_exception!(_mm, RefNotFoundError, PyKeyError);

/// Python-facing incremental context. See [`mm_core::refs::Context`].
#[pyclass(name = "PyContext", module = "_mm")]
pub struct PyContext {
    inner: Context,
    /// Parallel to `inner.items` — holds PIL / bytes / arbitrary Python
    /// objects for in-memory items. `None` for path/url items.
    py_objs: Vec<Option<Py<PyAny>>>,
}

#[pymethods]
impl PyContext {
    #[new]
    #[pyo3(signature = (session_id=None))]
    fn new(session_id: Option<String>) -> Self {
        let sid = session_id.unwrap_or_else(uuid7);
        PyContext {
            inner: Context::new(sid),
            py_objs: Vec::new(),
        }
    }

    #[getter]
    fn session_id(&self) -> &str {
        self.inner.session_id.as_str()
    }

    fn __len__(&self) -> usize {
        self.inner.len()
    }

    fn num_items(&self) -> usize {
        self.inner.len()
    }

    /// Primitive-typed put. The Python wrapper classifies `obj` into
    /// `kind` (one of the mm kinds) + a `source_kind` in
    /// ``("path", "in_memory", "url")`` + a `source_value` string.
    ///
    /// For `in_memory` items:
    ///   - `byte_len`: decoded/raw byte length (best-effort).
    ///   - `desc`: short human-readable description used in tree / repr.
    ///   - `py_obj`: the original Python object, retained for `get`.
    ///
    /// `metadata_json` is an optional JSON object; keys are rendered in
    /// insertion order. Values may be strings, ints, floats, bools, string
    /// lists, or arbitrary nested JSON.
    #[pyo3(signature = (kind, source_kind, source_value, byte_len=None, desc=None, py_obj=None, metadata_json=None))]
    #[allow(clippy::too_many_arguments)]
    fn put(
        &mut self,
        kind: &str,
        source_kind: &str,
        source_value: &str,
        byte_len: Option<u64>,
        desc: Option<&str>,
        py_obj: Option<Py<PyAny>>,
        metadata_json: Option<&str>,
    ) -> PyResult<String> {
        let file_kind = kind_from_name(kind);
        let source = build_source(source_kind, source_value, byte_len, desc)?;
        let metadata = parse_metadata(metadata_json)?;

        let ref_id = self.inner.put(file_kind, source, metadata);
        self.py_objs.push(py_obj);
        Ok(ref_id.to_string())
    }

    /// Return the stored Python object for an in-memory item, a
    /// freshly-constructed `pathlib.Path` for on-disk items, or the URL
    /// string for remote items.
    ///
    /// Raises `_mm.RefNotFoundError` (a `KeyError`) with an agent-friendly
    /// markdown message on miss.
    fn get(&self, py: Python<'_>, ref_id: &str) -> PyResult<Py<PyAny>> {
        let idx = self
            .inner
            .get_index(ref_id)
            .map_err(|e| RefNotFoundError::new_err(e.message))?;
        let item = &self.inner.items[idx];
        match &item.source {
            ItemSource::InMemory { .. } => {
                if let Some(obj) = self.py_objs.get(idx).and_then(|o| o.as_ref()) {
                    Ok(obj.clone_ref(py))
                } else {
                    Err(PyValueError::new_err(format!(
                        "ref {:?} is in-memory but no Python object is held for it",
                        ref_id
                    )))
                }
            }
            ItemSource::Path { path } => {
                let pathlib = py.import("pathlib")?;
                let p = pathlib.getattr("Path")?.call1((path.as_str(),))?;
                Ok(p.unbind())
            }
            ItemSource::Url { url } => Ok(url.as_str().into_pyobject(py)?.into_any().unbind()),
        }
    }

    /// Return the item metadata at `ref_id` as a dict:
    /// ``{ref_id, kind, source_kind, source_value, byte_len, desc, metadata}``.
    fn item(&self, py: Python<'_>, ref_id: &str) -> PyResult<Py<PyAny>> {
        let idx = self
            .inner
            .get_index(ref_id)
            .map_err(|e| RefNotFoundError::new_err(e.message))?;
        self.item_at(py, idx)
    }

    /// Return a Python list of item dicts in insertion order.
    fn items(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let list = PyList::empty(py);
        for i in 0..self.inner.len() {
            let d = self.item_at(py, i)?;
            list.append(d)?;
        }
        Ok(list.into_pyobject(py)?.into_any().unbind())
    }

    /// Return the markdown `__repr__` for this context.
    fn repr_markdown(&self) -> String {
        self.inner.to_repr_markdown()
    }

    fn __repr__(&self) -> String {
        self.inner.to_repr_markdown()
    }

    /// Return the T4 ``insertion``-layout tree rendering.
    fn render_tree_insertion(&self) -> String {
        self.inner.render_tree_insertion()
    }

    /// Build the markdown table for `to_md`.
    ///
    /// `contents` maps `ref_id -> cat()-extracted content string`. Refs
    /// without an entry fall back to the item's `summary`/`note`
    /// metadata when present.
    fn to_md_table(&self, contents: HashMap<String, String>) -> String {
        self.inner.to_md_with_contents(&contents)
    }

    /// Build the "ref not found" markdown message for `ref_id`.
    fn ref_not_found_message(&self, ref_id: &str) -> String {
        self.inner.ref_not_found_message(ref_id)
    }

    /// Return all ref ids in insertion order.
    fn ref_ids(&self) -> Vec<String> {
        self.inner
            .items
            .iter()
            .map(|i| i.ref_id.to_string())
            .collect()
    }

    /// Return `True` if `ref_id` is currently stored.
    fn contains(&self, ref_id: &str) -> bool {
        self.inner.by_ref.contains_key(ref_id)
    }
}

impl PyContext {
    fn item_at(&self, py: Python<'_>, idx: usize) -> PyResult<Py<PyAny>> {
        let item = self
            .inner
            .items
            .get(idx)
            .ok_or_else(|| PyValueError::new_err(format!("item index {} out of range", idx)))?;
        let d = PyDict::new(py);
        d.set_item("ref_id", item.ref_id.as_str())?;
        d.set_item("kind", item.kind.to_string())?;
        match &item.source {
            ItemSource::Path { path } => {
                d.set_item("source_kind", "path")?;
                d.set_item("source_value", path.as_str())?;
                d.set_item("byte_len", py.None())?;
                d.set_item("desc", path.as_str())?;
            }
            ItemSource::InMemory {
                mime,
                byte_len,
                desc,
            } => {
                d.set_item("source_kind", "in_memory")?;
                d.set_item("source_value", mime.as_str())?;
                d.set_item("byte_len", *byte_len)?;
                d.set_item("desc", desc.as_str())?;
            }
            ItemSource::Url { url } => {
                d.set_item("source_kind", "url")?;
                d.set_item("source_value", url.as_str())?;
                d.set_item("byte_len", py.None())?;
                d.set_item("desc", url.as_str())?;
            }
        }
        let meta_dict = PyDict::new(py);
        if let Some(meta) = &item.metadata {
            for (k, v) in meta.iter() {
                meta_dict.set_item(k.as_str(), metavalue_to_py(py, v)?)?;
            }
        }
        d.set_item("metadata", meta_dict)?;
        Ok(d.into_pyobject(py)?.into_any().unbind())
    }
}

fn build_source(
    source_kind: &str,
    source_value: &str,
    byte_len: Option<u64>,
    desc: Option<&str>,
) -> PyResult<ItemSource> {
    match source_kind {
        "path" => Ok(ItemSource::Path {
            path: CompactString::from(source_value),
        }),
        "url" => Ok(ItemSource::Url {
            url: CompactString::from(source_value),
        }),
        "in_memory" => Ok(ItemSource::InMemory {
            mime: CompactString::from(source_value),
            byte_len: byte_len.unwrap_or(0),
            desc: CompactString::from(desc.unwrap_or(source_value)),
        }),
        other => Err(PyValueError::new_err(format!(
            "unknown source_kind {:?}; expected 'path' | 'url' | 'in_memory'",
            other
        ))),
    }
}

fn parse_metadata(metadata_json: Option<&str>) -> PyResult<Option<MetaMap>> {
    let Some(raw) = metadata_json else {
        return Ok(None);
    };
    if raw.is_empty() {
        return Ok(None);
    }
    let value: JsonValue = serde_json::from_str(raw)
        .map_err(|e| PyValueError::new_err(format!("invalid metadata JSON: {}", e)))?;
    let JsonValue::Object(map) = value else {
        return Err(PyValueError::new_err(
            "metadata_json must be a JSON object (dict)",
        ));
    };
    if map.is_empty() {
        return Ok(None);
    }
    let mut out: MetaMap = Vec::with_capacity(map.len());
    for (k, v) in map {
        out.push((CompactString::from(k), json_to_meta(v)));
    }
    Ok(Some(out))
}

fn json_to_meta(v: JsonValue) -> MetaValue {
    match v {
        JsonValue::String(s) => MetaValue::Str(CompactString::from(s)),
        JsonValue::Bool(b) => MetaValue::Bool(b),
        JsonValue::Number(n) => {
            if let Some(i) = n.as_i64() {
                MetaValue::Int(i)
            } else if let Some(f) = n.as_f64() {
                MetaValue::Float(f)
            } else {
                MetaValue::Json(JsonValue::Number(n))
            }
        }
        JsonValue::Array(xs) => {
            if xs.iter().all(|x| x.is_string()) {
                MetaValue::StrList(
                    xs.into_iter()
                        .map(|x| CompactString::from(x.as_str().unwrap_or("")))
                        .collect(),
                )
            } else {
                MetaValue::Json(JsonValue::Array(xs))
            }
        }
        other => MetaValue::Json(other),
    }
}

fn metavalue_to_py(py: Python<'_>, v: &MetaValue) -> PyResult<Py<PyAny>> {
    Ok(match v {
        MetaValue::Str(s) => s.as_str().into_pyobject(py)?.into_any().unbind(),
        MetaValue::Int(n) => n.into_pyobject(py)?.into_any().unbind(),
        MetaValue::Float(n) => n.into_pyobject(py)?.into_any().unbind(),
        MetaValue::Bool(b) => b.into_pyobject(py)?.to_owned().into_any().unbind(),
        MetaValue::StrList(xs) => {
            let list = PyList::empty(py);
            for s in xs {
                list.append(s.as_str())?;
            }
            list.into_pyobject(py)?.into_any().unbind()
        }
        MetaValue::Json(v) => {
            let json = py.import("json")?;
            let text = serde_json::to_string(v).unwrap_or_else(|_| "null".into());
            json.call_method1("loads", (text,))?.unbind()
        }
    })
}

/// Free function: generate a fresh kind-prefixed ref id.
#[pyfunction]
pub fn make_ref_id(kind: &str) -> String {
    mm_core::refs::make_ref_id(kind_from_name(kind)).to_string()
}

/// Free function: generate a fresh UUIDv7 string.
#[pyfunction]
pub fn uuid7_py() -> String {
    uuid7()
}

/// The mm kind inferred from a conventional file name / extension.
#[pyfunction]
pub fn kind_for_name(name: &str) -> &'static str {
    let ext = std::path::Path::new(name)
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| format!(".{}", e.to_ascii_lowercase()))
        .unwrap_or_default();
    match mm_core::detect::kind_from_extension(&ext) {
        FileKind::Image => "image",
        FileKind::Video => "video",
        FileKind::Audio => "audio",
        FileKind::Document => "document",
        FileKind::Code => "code",
        FileKind::Data => "data",
        FileKind::Config => "config",
        FileKind::Text => "text",
        FileKind::Other => "other",
    }
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyContext>()?;
    m.add("RefNotFoundError", m.py().get_type::<RefNotFoundError>())?;
    m.add_function(wrap_pyfunction!(make_ref_id, m)?)?;
    m.add_function(wrap_pyfunction!(uuid7_py, m)?)?;
    m.add_function(wrap_pyfunction!(kind_for_name, m)?)?;
    Ok(())
}
