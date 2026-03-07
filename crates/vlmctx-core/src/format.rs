use arrow::array::{AsArray, RecordBatch};
use arrow::datatypes::DataType;

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
        headers.iter().map(|_| "---").collect::<Vec<_>>().join(" | ")
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
