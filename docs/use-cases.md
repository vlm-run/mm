# mm — Use Cases

53 scenarios that leverage mm's multimodal awareness, Rust-speed metadata extraction, token estimation, and semantic search. Each maps to existing CLI commands.

> **Note on `mm peek` vs `mm cat`:** `mm peek` returns local file metadata (image dims/EXIF/hash, video resolution/duration/codecs, audio metadata, mime, content hash). `mm cat` extracts content: PDF text, raw text/code passthrough, or a short LLM caption (`-m fast`) / LLM-heavy description (`-m accurate`) for image/video/PDF; audio returns a Whisper transcript by default (use `-p native` or `-p gemini-native` for LLM description). Examples below that need an LLM make the mode explicit.

---

## Video (20)

### Surveillance and security

<details><summary>1. Inventory NVR exports by camera and timestamp</summary>

`mm find ~/nvr-export --kind video --sort modified` lists recordings chronologically. `mm peek` on each extracts resolution, duration, codec, and frame rate — all from native MP4/MKV parsing in Rust, no ffmpeg, <100ms per file.
</details>

<details><summary>2. Verify footage integrity after evidence transfer</summary>

`mm peek evidence.mp4` returns the xxh3 content hash. Hash both sides of a transfer to confirm bit-for-bit integrity without re-watching hours of footage.
</details>

<details><summary>3. Identify which recordings are HD vs SD</summary>

`mm find ~/footage --kind video | mm peek --format json` extracts dimensions per file. Filter with jq or use SQL: `mm sql "SELECT name, dimensions FROM files WHERE kind='video'" --dir ~/footage --pre-index`.
</details>

<details><summary>4. Estimate storage cost before archiving to S3</summary>

`mm wc ~/security-cams --kind video --format json` gives total bytes across all video files. One number, directly usable for cost calculations.
</details>

### Content creation and media

<details><summary>5. Catalog a YouTube download folder without playback</summary>

`mm find ~/youtube --kind video | mm peek --format json` extracts dimensions, duration_s, video_codec, and audio_codec info for every file. No ffprobe installation needed — mm's Rust core parses MP4 and MKV natively.
</details>

<details><summary>6. Generate keyframe mosaic thumbnails</summary>

`mm cat lecture.mp4 -m fast` runs the video fast pipeline (`mosaic` encoder → 4×4 keyframe grid + short LLM description). Useful for creating visual previews of long recordings — one glance shows the content arc without watching.
</details>

<details><summary>7. Produce alt-text for a product demo</summary>

`mm cat demo.mp4 -m accurate` generates an LLM scene-by-scene description from keyframes. Pipe to clipboard: `mm cat demo.mp4 -m accurate | pbcopy`.
</details>

<details><summary>8. Compare codec and container usage across a library</summary>

`mm find ~/videos --kind video | mm peek --format json` gives per-file codec info. Aggregate to see h264 vs h265 vs av1 distribution — useful before batch transcoding decisions.
</details>

### Education

<details><summary>9. Build a lecture schedule from recording durations</summary>

`mm sql "SELECT name, duration_s FROM files WHERE kind='video' ORDER BY name" --dir ~/lectures --pre-index` returns duration per file from the local metadata index. Sum by folder to estimate total course hours or plan viewing schedules.
</details>

<details><summary>10. Estimate transcription cost for a video library</summary>

`mm sql "SELECT ROUND(SUM(duration_s)/3600.0, 1) as total_hours FROM files WHERE kind='video'" --dir ~/training --pre-index` gives total duration in one query. At known $/minute rates (Whisper, Rev, etc.), calculate the total transcription budget instantly.
</details>

<details><summary>11. Generate accessibility descriptions for course videos</summary>

`mm find ~/course --kind video | mm cat -m accurate` produces LLM-generated scene descriptions. These can serve as content summaries for students who can't watch the videos.
</details>

### Media management

<details><summary>12. Detect duplicate videos across volumes</summary>

Run `mm find /Volumes/Drive1 --kind video | mm peek --format json` on each volume. Compare xxh3 hashes to find exact duplicates without byte-by-byte comparison. Hash computation uses mmap — fast even on large files.
</details>

<details><summary>13. Assess a GoPro/drone SD card before import</summary>

`mm find /Volumes/GOPRO --tree --depth 1` shows file/size breakdown instantly. `mm wc /Volumes/GOPRO --by-kind` gives the storage split between video, photos, and thumbnails.
</details>

<details><summary>14. Find the longest and shortest recordings</summary>

`mm sql "SELECT name, duration_s FROM files WHERE kind='video' ORDER BY duration_s DESC" --dir ~/recordings --pre-index` — sort by duration directly from the metadata index.
</details>

### Compliance

<details><summary>15. Create a chain-of-custody file list for body camera footage</summary>

`mm find ~/evidence --kind video --columns name,size,modified --sort modified --format csv > evidence_manifest.csv` — timestamped, sized, sortable. Attach to case files.
</details>

<details><summary>16. Estimate LLM token cost before processing video evidence</summary>

`mm peek bodycam.mp4` gives duration and resolution. Use duration to estimate transcription tokens and resolution to estimate per-frame vision tokens.
</details>

### Pipelines

<details><summary>17. Build a video metadata table for a media asset manager</summary>

`mm find ~/dam --kind video | mm peek --format json > video_metadata.json` — structured metadata (resolution, duration, codec, fps, hash) for every video, ready for database import.
</details>

<details><summary>18. Pre-screen videos by size before expensive accurate-mode processing</summary>

`mm find ~/inbox --kind video --max-size 100mb` filters to small files first. Run `mm cat -m accurate` only on the filtered set to control LLM costs.
</details>

<details><summary>19. Generate a searchable video index with scene descriptions</summary>

`mm find ~/archive --kind video | mm cat -m accurate --format json > scenes.json` — each entry has keyframe-based scene descriptions. Load into a search index for text-based video retrieval.
</details>

<details><summary>20. Audit a video archive for codec migration planning</summary>

`mm sql "SELECT name,video_codec from files where kind='video' ORDER BY video_codec" --dir ~/archive --pre-index` reveals which files use legacy codecs (h264 baseline) vs modern (h265, av1). Prioritize transcoding by file size × codec age.
</details>

---

## Documents (8)

<details><summary>21. Full-text search across a PDF collection</summary>

`mm grep "force majeure" ~/contracts --kind document` searches extracted text from all PDFs/DOCX/PPTX. Returns file paths and matching lines — no manual opening of each file.
</details>

<details><summary>22. Estimate LLM ingestion cost for a document archive</summary>

`mm wc ~/legal --kind document` gives total file count, bytes, and estimated tokens. Multiply tokens by provider $/Mtok for a budget estimate.
</details>

<details><summary>23. Identify scanned (image-only) PDFs that need OCR</summary>

`mm cat scanned.pdf` returns `[No extractable text — this PDF may contain scanned images only]` for image-only PDFs. Batch-check: run across all PDFs and flag empty text responses.
</details>

<details><summary>24. Extract text from a large PDF for RAG chunking</summary>

`mm cat report.pdf` extracts full text via pypdfium2. Pipe directly to a chunker or embedding pipeline. Works on 500+ page documents.
</details>

<details><summary>25. Compare document volume across directory groups</summary>

`mm sql "SELECT parent, COUNT(*) as docs, ROUND(SUM(size)/1e6,1) as mb FROM files WHERE kind='document' GROUP BY parent ORDER BY mb DESC" --dir ~/shared --pre-index` — shows which teams or projects have the most document mass.
</details>

<details><summary>26. Search for specific clauses across contract PDFs</summary>

`mm grep "indemnification" ~/contracts --kind document -C 2` — returns matching lines with 2 lines of context, across all extractable documents in the directory.
</details>

<details><summary>27. Semantic search across documents</summary>

`mm grep "revenue forecast" ~/reports -s --kind document --pre-index` — vector similarity search across embedded document chunks. Finds conceptually related content, not just keyword matches.
</details>

<details><summary>28. Audit file formats in a document archive</summary>

`mm sql "SELECT ext, COUNT(*) as n, ROUND(SUM(size)/1e6,1) as mb FROM files WHERE kind='document' GROUP BY ext ORDER BY n DESC" --dir ~/archive --pre-index` — see PDF vs DOCX vs PPTX distribution.
</details>

---

## Images (8)

<details><summary>29. Extract EXIF metadata for photo organization</summary>

`mm find ~/photos --kind image | mm peek --format json` returns dimensions, MIME, hash, phash (perceptual hash), and EXIF fields (camera, date, GPS) per file. Use for sorting into date/location folders.
</details>

<details><summary>30. Find print-quality images by resolution</summary>

`mm sql "SELECT name, width, height FROM files WHERE kind='image' AND width >= 3000 ORDER BY width DESC" --dir ~/assets --pre-index` — filter for images that meet minimum print DPI requirements.
</details>

<details><summary>31. Caption images for fine-tuning datasets</summary>

`mm find ~/unlabeled --kind image | mm cat -m accurate --format json` — LLM-generated descriptions for each image. Each entry is an image-caption pair, directly usable as JSONL training data.
</details>

<details><summary>32. Detect near-duplicate images</summary>

mm computes perceptual hashes (pHash) via DCT in Rust. Two images with hamming distance < 8 are near-duplicates regardless of resize or mild compression — useful for deduplicating training sets or photo libraries.
</details>

<details><summary>33. Audit image format adoption in a web project</summary>

`mm sql "SELECT ext, COUNT(*) as n, ROUND(SUM(size)/1e6,1) as mb FROM files WHERE kind='image' GROUP BY ext ORDER BY mb DESC" --dir ~/site/public --pre-index` — see how much bandwidth is wasted on PNG vs WebP vs AVIF.
</details>

<details><summary>34. Estimate token cost for batch image processing</summary>

Image token cost depends on resolution (tile-based). `mm find ~/products --kind image | mm peek --format json` gives per-image dimensions (width, height) directly from the metadata scan.
</details>

<details><summary>35. Separate photos from screenshots and synthetic images</summary>

`mm find ~/photos --kind image | mm peek --format json` — images without camera/date/GPS EXIF fields are likely screenshots, downloads, or synthetic. Useful for separating real photos from non-photo images.
</details>

<details><summary>36. Semantic search across images</summary>

`mm grep "sunset over ocean" ~/photos -s --pre-index` — vector similarity search over image embeddings. Returns images whose LLM-generated captions are semantically close to the query.
</details>

---

## Audio (5)

<details><summary>37. Catalog a podcast archive by duration</summary>

`mm sql "SELECT name,duration_s,audio_codec FROM files WHERE kind='audio' ORDER BY duration_s DESC" --dir ~/podcasts --pre-index` extracts duration and codec per file. Sort by duration to find the longest episodes or estimate total listening time.
</details>

<details><summary>38. Estimate transcription cost</summary>

`mm sql "SELECT name, ROUND(duration_s/60.0, 1) as minutes FROM files WHERE kind='audio' ORDER BY duration_s DESC" --dir ~/audio --pre-index` gives per-file duration. Sum durations and multiply by $/minute for Whisper, Rev, or Deepgram pricing.
</details>

<details><summary>39. Find long recordings that need chunking</summary>

Audio files over 80 seconds exceed Gemini's single-part embedding limit. `mm sql "SELECT name, duration_s FROM files WHERE kind='audio' AND duration_s > 80 ORDER BY duration_s DESC" --dir ~/recordings --pre-index` identifies files that need `audio_parts()` chunking before embedding.
</details>

<details><summary>40. Summarize a meeting recording</summary>

`mm cat meeting.mp3 -p native -m accurate` runs the full pipeline: audio extraction and transcription or LLM summarization. The default `transcribe` encoder is encode-only — use `-p native` or `-p gemini-native` for LLM description.
</details>

<details><summary>41. Assess a field recording SD card</summary>

`mm find /Volumes/RECORDER --tree --depth 1` shows the directory structure. `mm wc /Volumes/RECORDER --kind audio` gives file count and total storage. For total recorded time: `mm sql "SELECT ROUND(SUM(duration_s)/3600.0, 1) as hours FROM files WHERE kind='audio'" --dir /Volumes/RECORDER --pre-index`.
</details>

---

## Code and development (5)

<details><summary>42. Check if a codebase fits in an LLM context window</summary>

`mm wc ~/project --kind code` gives file count, total bytes, and estimated tokens in one line. Instant answer: does this fit in 200K tokens?
</details>

<details><summary>43. Find refactoring candidates by file size</summary>

`mm find ~/project --kind code --sort size --reverse --limit 10` — the largest source files are often the ones most in need of splitting.
</details>

<details><summary>44. Audit technical debt</summary>

`mm grep "TODO|FIXME|HACK" ~/project --kind code --count` — per-file counts of debt markers. Pipe to an LLM for triage: `mm grep "TODO" --kind code | llm -s "Prioritize these by severity"`.
</details>

<details><summary>45. Compare code volume across languages</summary>

`mm sql "SELECT ext, COUNT(*) as files, ROUND(SUM(size)/1e3,1) as kb FROM files WHERE kind='code' GROUP BY ext ORDER BY files DESC" --dir ~/project --pre-index` — understand the language mix in a polyglot repo.
</details>

<details><summary>46. Generate a project overview for onboarding</summary>

`mm find ~/project --tree --depth 3` produces a complete directory structure. Combined with `mm wc --by-kind`, a new team member immediately sees what types of content exist and how they're organized.
</details>

---

## Cross-modal (7)

<details><summary>47. Triage a Downloads folder by media type</summary>

`mm wc ~/Downloads --by-kind` shows the breakdown: how much is video, documents, images, etc. `mm find ~/Downloads --tree --depth 1` gives the visual layout. An agent uses this to propose an organization plan.
</details>

<details><summary>48. Semantic search across all media types simultaneously</summary>

`mm grep "quarterly revenue" ~/shared -s --pre-index` searches PDFs (extracted text), images (via LLM captions), and video (via keyframe descriptions) in a single query using vector similarity.
</details>

<details><summary>49. Build a multimodal evidence package</summary>

For a construction project with permits (PDF), site photos (JPEG), and walkthrough video (MP4): `mm find ~/project --tree` shows everything, `mm wc --by-kind` quantifies it, and `mm peek` on each file gives structured metadata. One directory becomes a queryable index across all media types.
</details>

<details><summary>50. Create an invoice summary from mixed document formats</summary>

`mm find ~/invoices --kind document | mm cat -m accurate --format json` — the LLM extracts amounts, dates, and vendor names from PDFs, DOCX, and scanned documents. Output is structured JSON ready for aggregation.
</details>

<details><summary>51. Estimate total LLM cost for a mixed-media directory</summary>

`mm wc ~/data --by-kind --format json` gives token estimates broken down by kind.
</details>

<details><summary>52. Find all files modified today</summary>

`mm sql "SELECT name, kind, size, datetime(modified/1000000,'unixepoch') as modified FROM files WHERE datetime(modified/1000000,'unixepoch') >= date('now','start of day') ORDER BY modified DESC" --dir ~/project --pre-index` — see what changed today across all media types without relying on git or filesystem watches.
</details>

<details><summary>53. Batch-extract metadata for a digital asset manager</summary>

`mm find ~/dam --format json > metadata.json` for file-level scan metadata. `mm find ~/dam | mm peek --format json > content.json` for richer local extraction (text, dimensions, duration, hash, EXIF). Add `--full` to also pull document author / title / subject / keywords / page count from PDFs and Office files.
</details>
