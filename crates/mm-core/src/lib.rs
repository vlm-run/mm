pub mod cache;
pub mod detect;
pub use detect::kind_from_path;
pub mod extract;
pub mod extractors;
pub mod format;
pub mod hash;
pub mod meta;
pub mod office;
pub mod refs;
pub mod schema;
pub mod serde;
pub mod table;
pub mod walk;
pub mod wc;

pub use format::{entries_to_json, entries_to_json_filtered, filter_entries};
pub use hash::{directory_hash, fast_fingerprint, full_hash_mmap, hamming_distance, phash};
pub use meta::{FileEntry, FileKind, enrich_image_dimensions};
pub use office::{OfficeDoc, OfficeError, OfficeMetadata};
pub use refs::{
    Context as RefsContext, Item, ItemSource, MetaMap, MetaValue, RefId, RefNotFound,
    kind_from_name, make_ref_id, prefix_for_kind, uuid7,
};
pub use schema::{metadata_record_schema, metadata_schema};
pub use table::build_metadata_batch;
pub use walk::scan_directory;
