use arrow::array::{AsArray, RecordBatch};
use arrow::datatypes::DataType;
use regex::Regex;

use crate::meta::FileEntry;

/// Name matcher: regex if the pattern compiles, otherwise case-insensitive substring.
enum NameMatcher {
    Regex(Regex),
    Substring(String),
}

impl NameMatcher {
    fn new(pattern: &str) -> Self {
        match Regex::new(pattern) {
            Ok(re) => NameMatcher::Regex(re),
            Err(_) => NameMatcher::Substring(pattern.to_lowercase()),
        }
    }

    fn is_match(&self, name: &str) -> bool {
        match self {
            NameMatcher::Regex(re) => re.is_match(name),
            NameMatcher::Substring(pat) => name.to_lowercase().contains(pat),
        }
    }
}

pub enum OutputFormat {
    Markdown,
    Json,
    Csv,
    Lines,
}

pub fn record_batch_to_markdown(batch: &RecordBatch) -> String {
    let schema = batch.schema();
    let fields = schema.fields();

    let headers: Vec<&str> = fields.iter().map(|f| f.name().as_str()).collect();
    let mut lines = Vec::with_capacity(batch.num_rows() + 2);

    lines.push(format!("| {} |", headers.join(" | ")));
    lines.push(format!(
        "| {} |",
        headers
            .iter()
            .map(|_| "---")
            .collect::<Vec<_>>()
            .join(" | ")
    ));

    for row in 0..batch.num_rows() {
        let cells: Vec<String> = (0..batch.num_columns())
            .map(|col| format_cell(batch, row, col))
            .collect();
        lines.push(format!("| {} |", cells.join(" | ")));
    }

    lines.join("\n")
}

pub fn record_batch_to_json(batch: &RecordBatch) -> Result<String, serde_json::Error> {
    let mut rows = Vec::with_capacity(batch.num_rows());
    let schema = batch.schema();

    for row in 0..batch.num_rows() {
        let mut map = serde_json::Map::new();
        for col in 0..batch.num_columns() {
            let name = schema.field(col).name().clone();
            let value = format_cell(batch, row, col);
            map.insert(name, serde_json::Value::String(value));
        }
        rows.push(serde_json::Value::Object(map));
    }

    serde_json::to_string_pretty(&rows)
}

pub fn record_batch_to_csv(batch: &RecordBatch, delimiter: u8) -> String {
    let schema = batch.schema();
    let headers: Vec<&str> = schema.fields().iter().map(|f| f.name().as_str()).collect();
    let sep = delimiter as char;

    let mut lines = Vec::with_capacity(batch.num_rows() + 1);
    lines.push(headers.join(&sep.to_string()));

    for row in 0..batch.num_rows() {
        let cells: Vec<String> = (0..batch.num_columns())
            .map(|col| format_cell(batch, row, col))
            .collect();
        lines.push(cells.join(&sep.to_string()));
    }

    lines.join("\n")
}

pub fn record_batch_to_lines(batch: &RecordBatch) -> String {
    let path_col = batch
        .schema()
        .fields()
        .iter()
        .position(|f| f.name() == "path")
        .unwrap_or(0);

    let mut lines = Vec::with_capacity(batch.num_rows());
    for row in 0..batch.num_rows() {
        lines.push(format_cell(batch, row, path_col));
    }
    lines.join("\n")
}

/// Serialize entries directly to JSON, bypassing Arrow entirely.
/// ~100x faster than Arrow → pyarrow → Python dict → json.dumps.
pub fn entries_to_json(entries: &[FileEntry]) -> String {
    let rows: Vec<serde_json::Value> = entries.iter().map(entry_to_json_value).collect();
    serde_json::to_string_pretty(&rows).unwrap_or_else(|_| "[]".to_string())
}

/// Filter + sort entries, returning references. Shared by JSON and lines output.
#[allow(clippy::too_many_arguments)]
fn filter_entries<'a>(
    entries: &'a [FileEntry],
    kind: Option<&str>,
    ext: Option<&str>,
    min_size: Option<u64>,
    max_size: Option<u64>,
    name: Option<&str>,
    limit: Option<usize>,
    sort_by: Option<&str>,
    descending: bool,
) -> Vec<&'a FileEntry> {
    let matcher = name.map(NameMatcher::new);

    let mut filtered: Vec<&FileEntry> = entries
        .iter()
        .filter(|e| kind.is_none() || e.kind.to_string() == kind.unwrap())
        .filter(|e| ext.is_none() || e.ext.as_str() == ext.unwrap())
        .filter(|e| min_size.is_none() || e.size >= min_size.unwrap())
        .filter(|e| max_size.is_none() || e.size <= max_size.unwrap())
        .filter(|e| matcher.as_ref().map_or(true, |m| m.is_match(e.name.as_str())))
        .collect();

    if let Some(field) = sort_by {
        filtered.sort_by(|a, b| {
            let cmp = match field {
                "size" => a.size.cmp(&b.size),
                "name" => a.name.cmp(&b.name),
                "path" => a.path.cmp(&b.path),
                "ext" => a.ext.cmp(&b.ext),
                "kind" => a.kind.to_string().cmp(&b.kind.to_string()),
                "modified" => a.modified_epoch_us.cmp(&b.modified_epoch_us),
                "created" => a.created_epoch_us.cmp(&b.created_epoch_us),
                "depth" => a.depth.cmp(&b.depth),
                _ => std::cmp::Ordering::Equal,
            };
            if descending { cmp.reverse() } else { cmp }
        });
    }

    if let Some(n) = limit {
        filtered.truncate(n);
    }

    filtered
}

/// Serialize entries to JSON with filtering/sorting applied in Rust.
#[allow(clippy::too_many_arguments)]
pub fn entries_to_json_filtered(
    entries: &[FileEntry],
    kind: Option<&str>,
    ext: Option<&str>,
    min_size: Option<u64>,
    max_size: Option<u64>,
    name: Option<&str>,
    limit: Option<usize>,
    sort_by: Option<&str>,
    descending: bool,
) -> String {
    let filtered = filter_entries(
        entries, kind, ext, min_size, max_size, name, limit, sort_by, descending,
    );
    let rows: Vec<serde_json::Value> = filtered.iter().map(|e| entry_to_json_value(e)).collect();
    serde_json::to_string_pretty(&rows).unwrap_or_else(|_| "[]".to_string())
}

/// Newline-delimited paths with filtering, bypassing Arrow.
#[allow(clippy::too_many_arguments)]
pub fn entries_to_lines_filtered(
    entries: &[FileEntry],
    kind: Option<&str>,
    ext: Option<&str>,
    min_size: Option<u64>,
    max_size: Option<u64>,
    name: Option<&str>,
    limit: Option<usize>,
    sort_by: Option<&str>,
    descending: bool,
) -> String {
    let filtered = filter_entries(
        entries, kind, ext, min_size, max_size, name, limit, sort_by, descending,
    );
    filtered
        .iter()
        .map(|e| e.path.as_str())
        .collect::<Vec<_>>()
        .join("\n")
}

fn epoch_us_to_string(us: i64) -> String {
    chrono::DateTime::from_timestamp_micros(us)
        .map(|dt| dt.format("%Y-%m-%d %H:%M:%S%.6f").to_string())
        .unwrap_or_default()
}

fn entry_to_json_value(e: &FileEntry) -> serde_json::Value {
    serde_json::json!({
        "path": e.path.as_str(),
        "name": e.name.as_str(),
        "stem": e.stem.as_str(),
        "ext": e.ext.as_str(),
        "size": e.size,
        "modified": epoch_us_to_string(e.modified_epoch_us),
        "created": epoch_us_to_string(e.created_epoch_us),
        "mime": e.mime.as_str(),
        "kind": e.kind.to_string(),
        "is_binary": e.is_binary,
        "depth": e.depth,
        "parent": e.parent.as_str(),
        "width": e.width,
        "height": e.height,
    })
}

fn format_cell(batch: &RecordBatch, row: usize, col: usize) -> String {
    let array = batch.column(col);

    if array.is_null(row) {
        return String::new();
    }

    match array.data_type() {
        DataType::Utf8 => array.as_string::<i32>().value(row).to_string(),
        DataType::UInt64 => {
            let arr = array
                .as_any()
                .downcast_ref::<arrow::array::UInt64Array>()
                .unwrap();
            arr.value(row).to_string()
        }
        DataType::UInt32 => {
            let arr = array
                .as_any()
                .downcast_ref::<arrow::array::UInt32Array>()
                .unwrap();
            arr.value(row).to_string()
        }
        DataType::UInt16 => {
            let arr = array
                .as_any()
                .downcast_ref::<arrow::array::UInt16Array>()
                .unwrap();
            arr.value(row).to_string()
        }
        DataType::Boolean => {
            let arr = array
                .as_any()
                .downcast_ref::<arrow::array::BooleanArray>()
                .unwrap();
            arr.value(row).to_string()
        }
        DataType::Timestamp(_, _) => {
            let arr = array
                .as_any()
                .downcast_ref::<arrow::array::TimestampMicrosecondArray>()
                .unwrap();
            let us = arr.value(row);
            let secs = us / 1_000_000;
            let nsecs = ((us % 1_000_000) * 1000) as u32;
            chrono::DateTime::from_timestamp(secs, nsecs)
                .map(|dt| dt.format("%Y-%m-%d %H:%M:%S").to_string())
                .unwrap_or_default()
        }
        DataType::Float64 => {
            let arr = array
                .as_any()
                .downcast_ref::<arrow::array::Float64Array>()
                .unwrap();
            format!("{:.2}", arr.value(row))
        }
        _ => format!("{:?}", array),
    }
}
