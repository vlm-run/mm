//! Office document conversion and parsing via [`libreoffice-pure`].
//!
//! Surfaces:
//! - [`convert_to_pdf`] — any supported document → PDF on disk.
//! - [`content`]        — content only (skips metadata work).
//! - [`metadata`]       — metadata only (skips content rendering).
//! - [`parse_full`]     — content + metadata.

use std::fs;
use std::path::{Path, PathBuf};

use libreoffice_pure::{convert_path_bytes, sniff_format_from_path};
use lo_core::Metadata;

#[derive(Debug, thiserror::Error)]
pub enum OfficeError {
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),

    #[error("invalid path: {0}")]
    InvalidPath(PathBuf),

    #[error("unsupported format: {0}")]
    UnsupportedFormat(String),

    #[error("backend error: {0}")]
    Backend(String),
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct OfficeMetadata {
    pub author: String,
    pub title: String,
    pub subject: String,
    pub description: String,
    pub keywords: Vec<String>,
    pub created: String,
    pub modified: String,
    pub pages: Option<usize>,
}

#[derive(Clone, Debug, Default)]
pub struct OfficeDoc {
    pub content: String,
    pub metadata: OfficeMetadata,
}

/// Convert any `libreoffice-pure`–supported document to PDF and write it to `output`.
///
/// Returns the path the PDF was written to.
pub fn convert_to_pdf(input: &Path, output: &Path) -> Result<PathBuf, OfficeError> {
    let path_str = input
        .to_str()
        .ok_or_else(|| OfficeError::InvalidPath(input.to_path_buf()))?;
    let bytes = fs::read(input)?;
    let pdf = convert_path_bytes(path_str, &bytes, "pdf")
        .map_err(|e| OfficeError::Backend(e.to_string()))?;
    fs::write(output, pdf)?;
    Ok(output.to_path_buf())
}

/// Extract just the textual content of a supported document.
pub fn content(input: &Path) -> Result<String, OfficeError> {
    Ok(load(input)?.content())
}

/// Extract just the core metadata of a supported document.
pub fn metadata(input: &Path) -> Result<OfficeMetadata, OfficeError> {
    let doc = load(input)?;
    let pages = doc.pages();
    Ok(meta_from(doc.meta_ref(), pages))
}

/// Extract content + metadata in one pass.
///
/// Supported formats: `docx`, `doc`, `odt`, `xlsx`, `ods`, `pptx`, `odp`.
pub fn parse_full(input: &Path) -> Result<OfficeDoc, OfficeError> {
    let doc = load(input)?;
    let pages = doc.pages();
    let metadata = meta_from(doc.meta_ref(), pages);
    Ok(OfficeDoc {
        content: doc.content(),
        metadata,
    })
}

enum Family {
    Writer(lo_core::TextDocument),
    Calc(lo_core::Workbook),
    Impress(lo_core::Presentation),
}

impl Family {
    fn content(&self) -> String {
        match self {
            Family::Writer(d) => lo_writer::to_plain_text(d),
            Family::Calc(w) => lo_calc::to_markdown(w),
            Family::Impress(p) => lo_impress::to_markdown(p),
        }
    }

    fn meta_ref(&self) -> &Metadata {
        match self {
            Family::Writer(d) => &d.meta,
            Family::Calc(w) => &w.meta,
            Family::Impress(p) => &p.meta,
        }
    }

    fn pages(&self) -> Option<usize> {
        match self {
            Family::Writer(_) => None,
            Family::Calc(w) => Some(w.sheets.len()),
            Family::Impress(p) => Some(p.slides.len()),
        }
    }
}

fn load(input: &Path) -> Result<Family, OfficeError> {
    let path_str = input
        .to_str()
        .ok_or_else(|| OfficeError::InvalidPath(input.to_path_buf()))?;
    let format = sniff_format_from_path(path_str)
        .ok_or_else(|| OfficeError::UnsupportedFormat(String::from("unknown")))?;
    let bytes = fs::read(input)?;
    let title = input
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("document")
        .to_string();

    let backend = |e: lo_core::LoError| OfficeError::Backend(e.to_string());
    match format.as_str() {
        "docx" => lo_writer::from_docx_bytes(title, &bytes)
            .map(Family::Writer)
            .map_err(backend),
        "doc" => lo_writer::from_doc_bytes(title, &bytes)
            .map(Family::Writer)
            .map_err(backend),
        "odt" => lo_writer::from_odt_bytes(title, &bytes)
            .map(Family::Writer)
            .map_err(backend),
        "xlsx" => lo_calc::from_xlsx_bytes(title, &bytes)
            .map(Family::Calc)
            .map_err(backend),
        "ods" => lo_calc::from_ods_bytes(title, &bytes)
            .map(Family::Calc)
            .map_err(backend),
        "pptx" => lo_impress::from_pptx_bytes(title, &bytes)
            .map(Family::Impress)
            .map_err(backend),
        "odp" => lo_impress::from_odp_bytes(title, &bytes)
            .map(Family::Impress)
            .map_err(backend),
        other => Err(OfficeError::UnsupportedFormat(other.to_string())),
    }
}

fn meta_from(m: &Metadata, pages: Option<usize>) -> OfficeMetadata {
    OfficeMetadata {
        author: m.creator.clone(),
        title: m.title.clone(),
        subject: m.subject.clone(),
        description: m.description.clone(),
        keywords: m.keywords.clone(),
        created: m.created.clone(),
        modified: m.modified.clone(),
        pages,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unsupported_format_rejected() {
        let path = Path::new("/tmp/mm-office-test.bogus");
        std::fs::write(path, b"hello").unwrap();
        let err = parse_full(path).unwrap_err();
        assert!(matches!(err, OfficeError::UnsupportedFormat(_)));
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn missing_file_io_error() {
        let err = parse_full(Path::new("/nonexistent/doc.docx")).unwrap_err();
        assert!(matches!(err, OfficeError::Io(_)));
    }

    #[test]
    fn content_and_metadata_are_independent() {
        let err = content(Path::new("/nonexistent/doc.docx")).unwrap_err();
        assert!(matches!(err, OfficeError::Io(_)));
        let err = metadata(Path::new("/nonexistent/doc.docx")).unwrap_err();
        assert!(matches!(err, OfficeError::Io(_)));
    }
}
