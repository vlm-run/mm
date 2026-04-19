use std::collections::HashMap;
use std::fs;
use std::path::Path;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct CacheEntry {
    pub mtime_us: i64,
    pub size: u64,
}

#[derive(Debug, Default, serde::Serialize, serde::Deserialize)]
pub struct IndexManifest {
    pub entries: HashMap<String, CacheEntry>,
}

impl IndexManifest {
    pub fn load(path: &Path) -> Option<Self> {
        let data = fs::read(path).ok()?;
        serde_json::from_slice(&data).ok()
    }

    pub fn save(&self, path: &Path) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let data = serde_json::to_vec(self)?;
        fs::write(path, data)?;
        Ok(())
    }

    pub fn is_stale(&self, path: &str, mtime_us: i64, size: u64) -> bool {
        match self.entries.get(path) {
            Some(entry) => entry.mtime_us != mtime_us || entry.size != size,
            None => true,
        }
    }
}
