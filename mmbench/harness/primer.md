# mm is available on your PATH

`mm` gives you fast, multimodal context for files an LLM cannot read natively:
images, video, audio, PDFs, and other binary/media formats. Prefer it over
guessing or over slow per-file inspection. You decide which commands to use.

Commands:

- `mm find <dir>` list/inventory files (flags: `--kind`, `--ext`, `--tree`,
  `--sort size --reverse`, `--columns name,kind,size`, `--format json`).
- `mm peek <file>` local metadata: image dimensions/EXIF/hash, video
  resolution/duration/codec, audio duration/codec, mime. No LLM, <100ms.
- `mm wc <dir>` count files, total size, estimated tokens (`--by-kind`,
  `--kind image,document`).
- `mm sql "<query>" --dir <dir>` SQL over file metadata. Columns include
  `name, ext, size, kind, width, height`. Add `--pre-index` to warm the index.
- `mm grep <pattern> <dir>` content search across files (`--kind`, `-C N`,
  `--count`, `-i`, `-s`/`--semantic` for vector search).
- `mm cat <file>` extract content: PDF text, code/text passthrough, or an LLM
  caption/description for image/video/PDF (`-m accurate` for the LLM-heavy
  description); audio returns a transcript.

Use `--format json` when you want to parse the output. Run `mm <command> --help`
if you need the exact flags.
