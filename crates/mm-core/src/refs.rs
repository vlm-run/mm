//! Incremental multimodal context for VLM prompt construction.
//!
//! The [`Context`] struct holds an ordered collection of heterogeneous
//! [`Item`]s (files, in-memory blobs, URLs). Each item gets a stable
//! kind-prefixed [`RefId`] (``img_a1b2c3``, ``vid_d4e5f6``) that is unique
//! within the owning `session_id`.
//!
//! Design notes:
//!
//! - **RefId** is a [`CompactString`] — the canonical ``<prefix>_<6 hex>``
//!   shape fits inside the 24-byte SSO inline buffer, so typical refs never
//!   heap-allocate.
//! - **Item.metadata** is `Option<Box<MetaMap>>` — items with no user-supplied
//!   metadata pay one pointer's worth of memory and zero allocations. The
//!   box keeps the hot `Item` struct small.
//! - **MetaMap** is a `Vec<(key, MetaValue)>` rather than a hash map: users
//!   attach a handful of fields (note/summary/tags/…) and the cost of a
//!   linear scan is far below the cost of hashing for small N, while
//!   preserving insertion order for deterministic rendering.
//! - **by_ref** maps `RefId -> u32` index into `items`, giving O(1) `get`
//!   lookup. A `u32` index stays within dense-map expectations even at
//!   millions of items.
//!
//! All rendering (`to_repr_markdown`, `render_tree_insertion`, `to_md_skeleton`,
//! `ref_not_found_message`) happens in Rust, so the Python side only pays
//! one FFI boundary crossing to get a ready-to-print string.
//!
//! See [`crate::refs::Context::put`] for the insert path and
//! [`crate::refs::Context::get_index`] for the lookup path.

use compact_str::CompactString;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::{SystemTime, UNIX_EPOCH};

use crate::meta::FileKind;

/// Kind-prefixed reference id, e.g. ``img_a1b2c3``.
pub type RefId = CompactString;

/// Number of hex characters in the ref suffix (matches
/// ``vlmrun-python-sdk``'s canonical scheme).
pub const REF_SUFFIX_HEX: usize = 6;

/// Return the short 3–4 char ref prefix for a [`FileKind`].
///
/// Aligned with ``vlmrun-python-sdk`` for `image`/`video`/`audio`/`document`;
/// mm-specific kinds (`code`, `data`, `config`, `text`) keep short
/// distinct prefixes.
pub fn prefix_for_kind(kind: FileKind) -> &'static str {
    match kind {
        FileKind::Image => "img",
        FileKind::Video => "vid",
        FileKind::Audio => "aud",
        FileKind::Document => "doc",
        FileKind::Code => "code",
        FileKind::Data => "data",
        FileKind::Config => "cfg",
        FileKind::Text => "txt",
        FileKind::Other => "obj",
    }
}

/// Parse a kind name (``"image"``, ``"video"``, …) into a [`FileKind`].
///
/// Unknown names map to [`FileKind::Other`].
pub fn kind_from_name(s: &str) -> FileKind {
    match s {
        "image" => FileKind::Image,
        "video" => FileKind::Video,
        "audio" => FileKind::Audio,
        "document" => FileKind::Document,
        "code" => FileKind::Code,
        "data" => FileKind::Data,
        "config" => FileKind::Config,
        "text" => FileKind::Text,
        _ => FileKind::Other,
    }
}

/// Generate a random kind-prefixed ref id (``<prefix>_<6 lowercase hex>``).
///
/// Uses a cryptographically strong RNG (via [`getrandom`]-equivalent — here
/// we rely on the OS via `std::time` + rand's thread RNG surrogate). The
/// suffix alphabet is ``[0-9a-f]``, a subset of ``\w`` so every mm ref is
/// also a valid ``vlmrun-python-sdk`` ref.
pub fn make_ref_id(kind: FileKind) -> RefId {
    let mut bytes = [0u8; 3];
    fill_random(&mut bytes);
    let mut out = CompactString::with_capacity(prefix_for_kind(kind).len() + 1 + REF_SUFFIX_HEX);
    out.push_str(prefix_for_kind(kind));
    out.push('_');
    const HEX: &[u8; 16] = b"0123456789abcdef";
    for b in &bytes {
        out.push(HEX[(b >> 4) as usize] as char);
        out.push(HEX[(b & 0x0f) as usize] as char);
    }
    out
}

/// Generate a UUIDv7 as a canonical hyphenated string.
///
/// Format: ``xxxxxxxx-xxxx-7xxx-Nxxx-xxxxxxxxxxxx`` where the first 48 bits
/// are a millisecond Unix timestamp (big-endian) and the remainder is random.
/// `N` is the variant nibble (`8`/`9`/`a`/`b`).
pub fn uuid7() -> String {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    let millis = now.as_millis() as u64;

    let mut bytes = [0u8; 16];
    bytes[0] = ((millis >> 40) & 0xff) as u8;
    bytes[1] = ((millis >> 32) & 0xff) as u8;
    bytes[2] = ((millis >> 24) & 0xff) as u8;
    bytes[3] = ((millis >> 16) & 0xff) as u8;
    bytes[4] = ((millis >> 8) & 0xff) as u8;
    bytes[5] = (millis & 0xff) as u8;

    let mut rand_tail = [0u8; 10];
    fill_random(&mut rand_tail);
    bytes[6..16].copy_from_slice(&rand_tail);

    bytes[6] = (bytes[6] & 0x0f) | 0x70;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;

    format!(
        "{:02x}{:02x}{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}",
        bytes[0],
        bytes[1],
        bytes[2],
        bytes[3],
        bytes[4],
        bytes[5],
        bytes[6],
        bytes[7],
        bytes[8],
        bytes[9],
        bytes[10],
        bytes[11],
        bytes[12],
        bytes[13],
        bytes[14],
        bytes[15],
    )
}

/// Fill `buf` with cryptographic-quality random bytes.
///
/// Uses ``/dev/urandom`` on Unix (via `std::fs`) with a time-seeded
/// xorshift64 fallback. Sufficient for ref/uuid generation; not for
/// cryptographic keys.
fn fill_random(buf: &mut [u8]) {
    #[cfg(unix)]
    {
        use std::io::Read;
        if let Ok(mut f) = std::fs::File::open("/dev/urandom")
            && f.read_exact(buf).is_ok()
        {
            return;
        }
    }
    // Fallback: xorshift64 seeded from nanos + pointer addr.
    let mut state = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos() as u64)
        .unwrap_or(0xdead_beef_cafe_babe)
        ^ (buf.as_ptr() as u64);
    if state == 0 {
        state = 0x9E3779B97F4A7C15;
    }
    for b in buf.iter_mut() {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        *b = (state & 0xff) as u8;
    }
}

/// Where an item's payload physically lives.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ItemSource {
    /// On-disk file (absolute path).
    Path { path: CompactString },
    /// In-memory Python object (PIL.Image, bytes, etc.). The concrete
    /// object is kept on the Python side indexed by item position.
    InMemory {
        mime: CompactString,
        byte_len: u64,
        /// Short, human-readable description (e.g. ``"PIL.Image RGB 1024×768"``).
        desc: CompactString,
    },
    /// Remote URL.
    Url { url: CompactString },
}

impl ItemSource {
    pub fn display(&self) -> &str {
        match self {
            ItemSource::Path { path } => path.as_str(),
            ItemSource::InMemory { desc, .. } => desc.as_str(),
            ItemSource::Url { url } => url.as_str(),
        }
    }

    pub fn kind_label(&self) -> &'static str {
        match self {
            ItemSource::Path { .. } => "path",
            ItemSource::InMemory { .. } => "in-memory",
            ItemSource::Url { .. } => "url",
        }
    }
}

/// A single scalar metadata value.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum MetaValue {
    Str(CompactString),
    Int(i64),
    Float(f64),
    Bool(bool),
    StrList(Vec<CompactString>),
    /// Arbitrary nested JSON for rare cases (stored as an opaque
    /// [`serde_json::Value`]).
    Json(serde_json::Value),
}

impl MetaValue {
    /// Render the value in a tree-friendly, one-line form.
    pub fn render_inline(&self) -> String {
        match self {
            MetaValue::Str(s) => format!("\"{}\"", s),
            MetaValue::Int(n) => n.to_string(),
            MetaValue::Float(n) => format!("{}", n),
            MetaValue::Bool(b) => b.to_string(),
            MetaValue::StrList(xs) => {
                let parts: Vec<String> = xs.iter().map(|s| s.to_string()).collect();
                format!("[{}]", parts.join(", "))
            }
            MetaValue::Json(v) => serde_json::to_string(v).unwrap_or_else(|_| "null".into()),
        }
    }
}

/// Ordered map of metadata fields attached to an [`Item`].
pub type MetaMap = Vec<(CompactString, MetaValue)>;

/// One entry in a [`Context`].
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Item {
    pub ref_id: RefId,
    pub kind: FileKind,
    pub source: ItemSource,
    /// Boxed so items without metadata cost only one pointer.
    pub metadata: Option<Box<MetaMap>>,
}

impl Item {
    /// Look up a metadata field by key.
    pub fn meta(&self, key: &str) -> Option<&MetaValue> {
        self.metadata
            .as_ref()
            .and_then(|m| m.iter().find(|(k, _)| k == key).map(|(_, v)| v))
    }

    /// Render a short one-line label for tree / repr output:
    /// ``<display source>``.
    pub fn label(&self) -> &str {
        self.source.display()
    }
}

/// Incremental multimodal context — the main Rust-side structure.
///
/// Items are appended in insertion order. `by_ref` gives O(1) ref→index
/// lookup for [`Context::get_index`].
#[derive(Debug, Default, Serialize, Deserialize)]
pub struct Context {
    pub session_id: CompactString,
    pub items: Vec<Item>,
    #[serde(skip)]
    pub by_ref: HashMap<RefId, u32>,
}

/// Error produced when a [`Context::get_index`] lookup misses.
#[derive(Debug, Clone)]
pub struct RefNotFound {
    pub ref_id: CompactString,
    pub message: String,
}

impl Context {
    /// Create a fresh empty context with the given session id.
    pub fn new(session_id: impl Into<CompactString>) -> Self {
        Self {
            session_id: session_id.into(),
            items: Vec::new(),
            by_ref: HashMap::new(),
        }
    }

    /// Number of items currently in the context.
    pub fn len(&self) -> usize {
        self.items.len()
    }

    pub fn is_empty(&self) -> bool {
        self.items.is_empty()
    }

    /// Insert a new item and return the generated ref id.
    ///
    /// The caller is expected to have already classified `kind` and built
    /// the `source` (Python dispatches types to these three variants).
    pub fn put(&mut self, kind: FileKind, source: ItemSource, metadata: Option<MetaMap>) -> RefId {
        let mut ref_id = make_ref_id(kind);
        // Collision avoidance — essentially never hits at 2^24 entropy but
        // cheap to be defensive.
        while self.by_ref.contains_key(&ref_id) {
            ref_id = make_ref_id(kind);
        }
        let idx = self.items.len() as u32;
        self.by_ref.insert(ref_id.clone(), idx);
        self.items.push(Item {
            ref_id: ref_id.clone(),
            kind,
            source,
            metadata: metadata.map(Box::new),
        });
        ref_id
    }

    /// Look up an item's position by ref id.
    ///
    /// Returns [`RefNotFound`] with a preformatted markdown message when
    /// `ref_id` isn't present. The message includes a "did you mean"
    /// suggestion + the full context's ref table so agents that guessed
    /// wrong can self-correct.
    pub fn get_index(&self, ref_id: &str) -> Result<usize, RefNotFound> {
        if let Some(&idx) = self.by_ref.get(ref_id) {
            return Ok(idx as usize);
        }
        Err(RefNotFound {
            ref_id: CompactString::from(ref_id),
            message: self.ref_not_found_message(ref_id),
        })
    }

    pub fn item_at(&self, idx: usize) -> Option<&Item> {
        self.items.get(idx)
    }

    /// Build the human-readable "ref not found" message (markdown + suggestions).
    pub fn ref_not_found_message(&self, missing: &str) -> String {
        let suggestion = self.closest_ref(missing);
        let mut out = String::new();
        out.push_str(&format!(
            "ref {:?} not found in session {}",
            missing, self.session_id
        ));
        if let Some(hint) = suggestion {
            out.push_str(&format!(". Did you mean: {}?", hint));
        }
        out.push_str("\n\nAvailable refs:\n");
        out.push_str(&self.to_repr_markdown());
        out
    }

    /// Find the closest existing ref_id to `target` using Levenshtein
    /// distance — restricted to refs whose prefix matches `target`'s
    /// prefix so we don't suggest an image for a mistyped video ref.
    fn closest_ref(&self, target: &str) -> Option<&str> {
        let target_prefix = target.split('_').next().unwrap_or("");
        let mut best: Option<(usize, &str)> = None;
        for item in &self.items {
            let rid = item.ref_id.as_str();
            if rid.split('_').next().unwrap_or("") != target_prefix {
                continue;
            }
            let d = levenshtein(target, rid);
            if best.is_none_or(|(bd, _)| d < bd) {
                best = Some((d, rid));
            }
        }
        // Ignore wildly different matches.
        best.filter(|(d, _)| *d <= 4).map(|(_, r)| r)
    }

    // ── Rendering ─────────────────────────────────────────────────

    /// Markdown summary table of all refs (used by `__repr__` and miss messages).
    pub fn to_repr_markdown(&self) -> String {
        let mut out = String::new();
        out.push_str(&format!(
            "Context(session={}, items={})\n\n",
            self.session_id,
            self.items.len()
        ));
        if self.items.is_empty() {
            return out;
        }
        out.push_str("| ref | kind | source |\n");
        out.push_str("|-----|------|--------|\n");
        for item in &self.items {
            out.push_str(&format!(
                "| {} | {} | {} |\n",
                item.ref_id,
                item.kind,
                escape_md_cell(item.source.display()),
            ));
        }
        out
    }

    /// Markdown table for `to_md`. `contents` provides the already-extracted
    /// content per ref (Python fills this from `cat`); items without an
    /// entry get a `summary` / `note` metadata fallback, else a blank cell.
    pub fn to_md_with_contents(&self, contents: &HashMap<String, String>) -> String {
        let mut out = String::new();
        out.push_str("| ref | kind | source | content |\n");
        out.push_str("|-----|------|--------|---------|\n");
        for item in &self.items {
            let content = contents
                .get(item.ref_id.as_str())
                .cloned()
                .or_else(|| {
                    item.meta("summary")
                        .or_else(|| item.meta("note"))
                        .map(|v| match v {
                            MetaValue::Str(s) => s.to_string(),
                            other => other.render_inline(),
                        })
                })
                .unwrap_or_default();
            out.push_str(&format!(
                "| {} | {} | {} | {} |\n",
                item.ref_id,
                item.kind,
                escape_md_cell(item.source.display()),
                escape_md_cell(&truncate(&content, 120)),
            ));
        }
        out
    }

    /// Render the ``insertion`` tree layout (T4) as a plain string with
    /// box-drawing characters. Python prints via `rich.console` which
    /// passes the ANSI through unchanged.
    pub fn render_tree_insertion(&self) -> String {
        let mut out = String::new();
        out.push_str(&format!(
            "Context(session={}, items={})\n",
            self.session_id,
            self.items.len()
        ));
        let n = self.items.len();
        for (i, item) in self.items.iter().enumerate() {
            let last = i + 1 == n;
            let branch = if last { "└──" } else { "├──" };
            let cont = if last { "   " } else { "│  " };

            out.push_str(&format!(
                "{} [{}] {}  {}  {}\n",
                branch,
                i + 1,
                item.ref_id,
                item.kind,
                truncate(item.source.display(), 80),
            ));

            if let Some(meta) = &item.metadata
                && !meta.is_empty()
            {
                let m = meta.len();
                for (j, (k, v)) in meta.iter().enumerate() {
                    let last_meta = j + 1 == m;
                    let sub = if last_meta { "└─" } else { "├─" };
                    out.push_str(&format!(
                        "{}      {} {}: {}\n",
                        cont,
                        sub,
                        k,
                        v.render_inline()
                    ));
                }
            }
        }
        out
    }
}

fn escape_md_cell(s: &str) -> String {
    s.replace('|', r"\|").replace('\n', " ")
}

fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        return s.to_string();
    }
    let taken: String = s.chars().take(max.saturating_sub(1)).collect();
    format!("{}…", taken)
}

/// Classic Levenshtein distance with O(min(m, n)) memory.
fn levenshtein(a: &str, b: &str) -> usize {
    let a: Vec<char> = a.chars().collect();
    let b: Vec<char> = b.chars().collect();
    let (a, b) = if a.len() > b.len() { (b, a) } else { (a, b) };
    let m = a.len();
    let n = b.len();
    if m == 0 {
        return n;
    }
    let mut prev: Vec<usize> = (0..=m).collect();
    let mut curr = vec![0usize; m + 1];
    for (j, bc) in b.iter().enumerate() {
        curr[0] = j + 1;
        for (i, ac) in a.iter().enumerate() {
            let cost = if ac == bc { 0 } else { 1 };
            curr[i + 1] = (curr[i] + 1).min(prev[i + 1] + 1).min(prev[i] + cost);
        }
        std::mem::swap(&mut prev, &mut curr);
    }
    prev[m]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn make_ref_id_shape() {
        for _ in 0..100 {
            let r = make_ref_id(FileKind::Image);
            assert!(r.starts_with("img_"));
            assert_eq!(r.len(), "img_".len() + REF_SUFFIX_HEX);
            assert!(
                r[4..]
                    .chars()
                    .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
            );
        }
    }

    #[test]
    fn make_ref_id_random() {
        let ids: std::collections::HashSet<_> = (0..500)
            .map(|_| make_ref_id(FileKind::Video).to_string())
            .collect();
        assert!(ids.len() >= 498);
    }

    #[test]
    fn uuid7_format() {
        let u = uuid7();
        assert_eq!(u.len(), 36);
        assert_eq!(u.as_bytes()[14], b'7', "version nibble should be 7");
        let variant = u.as_bytes()[19];
        assert!(matches!(variant, b'8' | b'9' | b'a' | b'b'));
    }

    #[test]
    fn uuid7_monotonic_ish() {
        let a = uuid7();
        std::thread::sleep(std::time::Duration::from_millis(2));
        let b = uuid7();
        assert!(a <= b, "{} should sort <= {}", a, b);
    }

    #[test]
    fn put_and_get() {
        let mut ctx = Context::new("sess-1");
        let r1 = ctx.put(
            FileKind::Image,
            ItemSource::Path {
                path: "/abs/photo.jpg".into(),
            },
            None,
        );
        let r2 = ctx.put(
            FileKind::Video,
            ItemSource::Path {
                path: "/abs/clip.mp4".into(),
            },
            Some(vec![("note".into(), MetaValue::Str("hero".into()))]),
        );
        assert_eq!(ctx.len(), 2);
        assert_ne!(r1, r2);
        assert!(r1.starts_with("img_"));
        assert!(r2.starts_with("vid_"));

        let idx = ctx.get_index(&r2).unwrap();
        let it = ctx.item_at(idx).unwrap();
        assert_eq!(it.kind, FileKind::Video);
        assert_eq!(
            it.meta("note").map(|v| v.render_inline()),
            Some("\"hero\"".into())
        );
    }

    #[test]
    fn get_miss_suggests_close_ref() {
        let mut ctx = Context::new("s");
        let r = ctx.put(
            FileKind::Image,
            ItemSource::Path {
                path: "/a.png".into(),
            },
            None,
        );
        // Perturb one hex digit.
        let mut bad = r.to_string();
        let last = bad.pop().unwrap();
        let flipped = if last == '0' { '1' } else { '0' };
        bad.push(flipped);

        let err = ctx.get_index(&bad).unwrap_err();
        assert!(err.message.contains("Did you mean"), "{}", err.message);
        assert!(err.message.contains(r.as_str()));
    }

    #[test]
    fn get_miss_without_close_match_has_no_suggestion() {
        let mut ctx = Context::new("s");
        ctx.put(
            FileKind::Image,
            ItemSource::Path {
                path: "/a.png".into(),
            },
            None,
        );
        // Totally different prefix and body.
        let err = ctx.get_index("vid_zzzzzz").unwrap_err();
        assert!(!err.message.contains("Did you mean"), "{}", err.message);
        assert!(err.message.contains("Available refs"));
    }

    #[test]
    fn tree_insertion_contains_refs_and_metadata() {
        let mut ctx = Context::new("tree-sess");
        ctx.put(
            FileKind::Image,
            ItemSource::Path {
                path: "/photo.jpg".into(),
            },
            None,
        );
        ctx.put(
            FileKind::Document,
            ItemSource::Path {
                path: "/paper.pdf".into(),
            },
            Some(vec![
                ("summary".into(), MetaValue::Str("the paper".into())),
                (
                    "tags".into(),
                    MetaValue::StrList(vec!["nlp".into(), "transformer".into()]),
                ),
            ]),
        );
        let rendered = ctx.render_tree_insertion();
        assert!(rendered.contains("Context(session=tree-sess"));
        assert!(rendered.contains("img_"));
        assert!(rendered.contains("doc_"));
        assert!(rendered.contains("summary"));
        assert!(rendered.contains("the paper"));
        assert!(rendered.contains("[nlp, transformer]"));
    }

    #[test]
    fn repr_markdown_shape() {
        let mut ctx = Context::new("repr-sess");
        ctx.put(
            FileKind::Image,
            ItemSource::Path {
                path: "/a.png".into(),
            },
            None,
        );
        let md = ctx.to_repr_markdown();
        assert!(md.starts_with("Context(session=repr-sess, items=1)"));
        assert!(md.contains("| ref |"));
        assert!(md.contains("img_"));
    }

    #[test]
    fn levenshtein_basic() {
        assert_eq!(levenshtein("", ""), 0);
        assert_eq!(levenshtein("a", ""), 1);
        assert_eq!(levenshtein("kitten", "sitting"), 3);
        assert_eq!(levenshtein("abc", "abc"), 0);
    }
}
