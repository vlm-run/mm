//! Office document conversion and parsing via [`libreoffice-pure`].
//!
//! Two surfaces:
//! - [`convert_to_pdf`] — any supported document → PDF on disk.
//! - [`parse`] — any supported document → plain content + core metadata.

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

/// Parse a document and return its plain content plus core metadata.
///
/// Supported formats: `docx`, `doc`, `odt`, `pdf`, `xlsx`, `ods`, `pptx`, `odp`.
/// Spreadsheet/presentation content is rendered as Markdown; word-processing and
/// PDF content is rendered as plain text. `pages` reflects sheet/slide counts;
/// it is `None` for word-processing inputs (no pagination without layout).
pub fn parse(input: &Path) -> Result<OfficeDoc, OfficeError> {
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

    match format.as_str() {
        "docx" => writer_doc(lo_writer::from_docx_bytes(title, &bytes)),
        "doc" => writer_doc(lo_writer::from_doc_bytes(title, &bytes)),
        "odt" => writer_doc(lo_writer::from_odt_bytes(title, &bytes)),
        "pdf" => writer_doc(lo_writer::from_pdf_bytes(title, &bytes)),
        "xlsx" => calc_doc(lo_calc::from_xlsx_bytes(title, &bytes)),
        "ods" => calc_doc(lo_calc::from_ods_bytes(title, &bytes)),
        "pptx" => impress_doc(lo_impress::from_pptx_bytes(title, &bytes)),
        "odp" => impress_doc(lo_impress::from_odp_bytes(title, &bytes)),
        other => Err(OfficeError::UnsupportedFormat(other.to_string())),
    }
}

fn writer_doc(
    res: Result<lo_core::TextDocument, lo_core::LoError>,
) -> Result<OfficeDoc, OfficeError> {
    let doc = res.map_err(|e| OfficeError::Backend(e.to_string()))?;
    Ok(OfficeDoc {
        content: lo_writer::to_plain_text(&doc),
        metadata: meta_from(&doc.meta, None),
    })
}

fn calc_doc(res: Result<lo_core::Workbook, lo_core::LoError>) -> Result<OfficeDoc, OfficeError> {
    let wb = res.map_err(|e| OfficeError::Backend(e.to_string()))?;
    let pages = Some(wb.sheets.len());
    Ok(OfficeDoc {
        content: lo_calc::to_markdown(&wb),
        metadata: meta_from(&wb.meta, pages),
    })
}

fn impress_doc(
    res: Result<lo_core::Presentation, lo_core::LoError>,
) -> Result<OfficeDoc, OfficeError> {
    let pres = res.map_err(|e| OfficeError::Backend(e.to_string()))?;
    let pages = Some(pres.slides.len());
    Ok(OfficeDoc {
        content: lo_impress::to_markdown(&pres),
        metadata: meta_from(&pres.meta, pages),
    })
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
        let err = parse(path).unwrap_err();
        assert!(matches!(err, OfficeError::UnsupportedFormat(_)));
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn missing_file_io_error() {
        let err = parse(Path::new("/nonexistent/doc.docx")).unwrap_err();
        assert!(matches!(err, OfficeError::Io(_)));
    }
}
