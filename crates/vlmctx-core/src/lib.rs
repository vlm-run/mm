pub mod cache;
pub mod detect;
pub mod extract;
pub mod extractors;
pub mod format;
pub mod meta;
pub mod schema;
pub mod table;
pub mod walk;

pub use meta::{enrich_image_dimensions, FileEntry, FileKind};
pub use schema::{l0_schema, l1_schema};
pub use table::build_l0_record_batch;
pub use walk::scan_directory;
