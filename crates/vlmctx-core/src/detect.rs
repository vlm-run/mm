use crate::meta::FileKind;

pub fn kind_from_extension(ext: &str) -> FileKind {
    let ext = ext.strip_prefix('.').unwrap_or(ext).to_ascii_lowercase();
    match ext.as_str() {
        "rs" | "py" | "js" | "ts" | "tsx" | "jsx" | "c" | "cpp" | "cc" | "h" | "hpp" | "go"
        | "java" | "kt" | "kts" | "swift" | "rb" | "php" | "cs" | "scala" | "clj" | "ex"
        | "exs" | "erl" | "hs" | "ml" | "mli" | "lua" | "r" | "jl" | "sh" | "bash" | "zsh"
        | "fish" | "ps1" | "bat" | "cmd" | "pl" | "pm" | "v" | "sv" | "vhd" | "vhdl"
        | "zig" | "nim" | "d" | "dart" | "elm" | "vue" | "svelte" | "astro" | "sql"
        | "graphql" | "gql" | "proto" | "thrift" | "asm" | "s" | "m" | "mm" | "f90"
        | "f95" | "f03" | "cob" | "cbl" | "ada" | "adb" | "ads" => FileKind::Code,

        "png" | "jpg" | "jpeg" | "gif" | "bmp" | "tiff" | "tif" | "webp" | "svg" | "ico"
        | "heic" | "heif" | "avif" | "raw" | "cr2" | "nef" | "arw" | "dng" | "psd" | "ai"
        | "eps" => FileKind::Image,

        "pdf" | "doc" | "docx" | "xls" | "xlsx" | "ppt" | "pptx" | "odt" | "ods" | "odp"
        | "rtf" | "tex" | "latex" | "epub" => FileKind::Document,

        "mp4" | "mkv" | "avi" | "mov" | "wmv" | "flv" | "webm" | "m4v" | "mpg" | "mpeg"
        | "3gp" | "ogv" => FileKind::Video,

        "mp3" | "wav" | "flac" | "aac" | "ogg" | "wma" | "m4a" | "opus" | "aiff" | "ape"
        | "alac" => FileKind::Audio,

        "csv" | "tsv" | "json" | "jsonl" | "ndjson" | "xml" | "parquet" | "arrow" | "ipc"
        | "avro" | "feather" | "hdf5" | "h5" | "sqlite" | "db" | "pickle" | "pkl" | "npy"
        | "npz" | "mat" => FileKind::Data,

        "toml" | "yaml" | "yml" | "ini" | "cfg" | "conf" | "config" | "env" | "properties"
        | "plist" | "editorconfig" | "prettierrc" | "eslintrc" | "babelrc" => FileKind::Config,

        "md" | "markdown" | "rst" | "txt" | "text" | "log" | "readme" | "changelog"
        | "license" | "licence" | "authors" | "contributors" | "todo" | "notes"
        | "org" | "adoc" | "asciidoc" | "wiki" => FileKind::Text,

        _ => FileKind::Other,
    }
}

pub fn mime_from_extension(ext: &str) -> String {
    mime_guess::from_ext(ext.strip_prefix('.').unwrap_or(ext))
        .first()
        .map(|m| m.to_string())
        .unwrap_or_else(|| "application/octet-stream".to_string())
}

pub fn is_binary_extension(ext: &str) -> bool {
    let ext = ext.strip_prefix('.').unwrap_or(ext).to_ascii_lowercase();
    matches!(
        kind_from_extension(&ext),
        FileKind::Image | FileKind::Video | FileKind::Audio
    ) || matches!(
        ext.as_str(),
        "exe" | "dll" | "so" | "dylib" | "bin" | "o" | "a"
            | "class" | "pyc" | "pyo" | "wasm"
            | "zip" | "gz" | "bz2" | "xz" | "zst" | "tar"
            | "rar" | "7z" | "jar" | "war"
            | "parquet" | "arrow" | "ipc" | "avro"
            | "sqlite" | "db" | "pickle" | "pkl"
            | "npy" | "npz" | "hdf5" | "h5"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kind_from_extension() {
        assert_eq!(kind_from_extension(".py"), FileKind::Code);
        assert_eq!(kind_from_extension("rs"), FileKind::Code);
        assert_eq!(kind_from_extension(".png"), FileKind::Image);
        assert_eq!(kind_from_extension(".pdf"), FileKind::Document);
        assert_eq!(kind_from_extension(".mp4"), FileKind::Video);
        assert_eq!(kind_from_extension(".mp3"), FileKind::Audio);
        assert_eq!(kind_from_extension(".csv"), FileKind::Data);
        assert_eq!(kind_from_extension(".toml"), FileKind::Config);
        assert_eq!(kind_from_extension(".md"), FileKind::Text);
        assert_eq!(kind_from_extension(".xyz_unknown"), FileKind::Other);
    }

    #[test]
    fn test_is_binary() {
        assert!(is_binary_extension(".png"));
        assert!(is_binary_extension(".exe"));
        assert!(!is_binary_extension(".py"));
        assert!(!is_binary_extension(".md"));
    }
}
