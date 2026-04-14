//! VLM message serialization — fast-path encoding for images, Gemini, and VLMRun.
//!
//! Each sub-module provides pure functions that take a file path and return
//! encoded data (base64 strings, JSON Part dicts, etc.) suitable for direct
//! inclusion in chat-completions message arrays.

pub mod gemini;
pub mod image;
pub mod vlmrun;

/// Result of resizing an image and encoding it as base64.
#[derive(Debug, Clone)]
pub struct EncodedImage {
    /// Base64-encoded image bytes (no data-URI prefix).
    pub base64: String,
    /// MIME type (e.g. "image/jpeg").
    pub mime: String,
    /// Width of the encoded image in pixels.
    pub width: u32,
    /// Height of the encoded image in pixels.
    pub height: u32,
}

/// A single tile from a tiled image.
#[derive(Debug, Clone)]
pub struct EncodedTile {
    /// Base64-encoded tile bytes.
    pub base64: String,
    /// MIME type.
    pub mime: String,
    /// Column index (0-based).
    pub col: u32,
    /// Row index (0-based).
    pub row: u32,
    /// Total columns in the grid.
    pub total_cols: u32,
    /// Total rows in the grid.
    pub total_rows: u32,
    /// Tile width in pixels.
    pub width: u32,
    /// Tile height in pixels.
    pub height: u32,
}
