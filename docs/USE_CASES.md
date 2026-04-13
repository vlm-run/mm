# mm — Use Cases

Scenarios that leverage mm's multimodal awareness, Rust-speed metadata extraction, token estimation, and semantic search. Each maps to existing CLI commands.

---

## Video (20)

### Surveillance and security

1. **Inventory NVR exports by camera and timestamp** — `mm find ~/nvr-export --kind video --sort modified` lists recordings chronologically. `mm cat -l 1` on each extracts resolution, duration, codec, and frame rate — all from native MP4/MKV parsing in Rust, no ffmpeg, <100ms per file.

2. **Verify footage integrity after evidence transfer** — `mm cat evidence.mp4 -l 1` returns the xxh3 content hash. Hash both sides of a transfer to confirm bit-for-bit integrity without re-watching hours of footage.

3. **Identify which recordings are HD vs SD** — `mm find ~/footage --kind video | mm cat -l 1 --format json` extracts resolution per file. Filter in jq or SQL: `mm sql "SELECT name, width, height FROM files WHERE kind='video'" --dir ~/footage` (after L1 populates dimensions).

4. **Estimate storage cost before archiving to S3** — `mm wc ~/security-cams --kind video --format json` gives total bytes across all video files. One number, directly usable for cost calculations.

### Content creation and media

5. **Catalog a YouTube download folder without playback** — `mm find ~/youtube --kind video | mm cat -l 1` extracts resolution, duration, codec, and audio track info for every file. No ffprobe installation needed — mm's Rust L1 parses MP4 and MKV natively.

6. **Generate keyframe mosaic thumbnails** — `mm cat lecture.mp4 -l 2` extracts keyframes into a tiled grid image. Useful for creating visual previews of long recordings — one glance shows the content arc without watching.

7. **Produce alt-text for a product demo** — `mm cat demo.mp4 -l 2` generates an LLM scene-by-scene description from keyframes. Pipe to clipboard: `mm cat demo.mp4 -l 2 | pbcopy`.

8. **Compare codec and container usage across a library** — `mm find ~/videos --kind video | mm cat -l 1 --format json` gives per-file codec info. Aggregate to see h264 vs h265 vs av1 distribution — useful before batch analysis and transcoding decisions, i.e., Iterate: `for f in ~/videos/*.mp4; do mm cat "$f" -l 1; done`.

### Education

9. **Build a lecture schedule from recording durations** — `mm find ~/lectures --kind video | mm cat -l 1 --format json` returns duration in seconds per file. Sum by folder to estimate total course hours, plan viewing schedules, or allocate transcription budgets.

10. **Estimate transcription cost for a video library** — `mm find ~/training --kind video | mm cat -l 1 --format json` gives total duration. At known $/minute rates (Whisper, Rev, etc.), calculate the total transcription budget in one pipeline.

11. **Generate accessibility descriptions for course videos** — `mm find ~/course --kind video | mm cat -l 2` produces LLM-generated scene descriptions. These can serve as content summaries for students who can't watch the videos.

### Media management

12. **Detect duplicate videos across volumes** — Run `mm find /Volumes/Drive1 --kind video | mm cat -l 1 --format json` on each volume. Compare xxh3 hashes to find exact duplicates without byte-by-byte comparison. Hash computation uses mmap — fast even on large files.

13. **Assess a GoPro/drone SD card before import** — `mm find /Volumes/GOPRO --tree --depth 1` shows file/size breakdown instantly. `mm wc /Volumes/GOPRO --by-kind` gives the storage split between video, photos, and thumbnails.

14. **Find the longest and shortest recordings** — `mm find ~/recordings --kind video | mm cat -l 1 --format json` gives actual duration per file. Sort client-side or via SQL after L1 extraction populates the metadata.

### Compliance

15. **Create a chain-of-custody file list for body camera footage** — `mm find ~/evidence --kind video --columns name,size,modified --sort modified --format csv > evidence_manifest.csv` — timestamped, sized, sortable. Attach to case files.

16. **Estimate LLM token cost before processing video evidence** — `mm cat bodycam.mp4 -l 1 --format json` gives duration and resolution.

### Pipelines

17. **Build a video metadata table for a media asset manager** — `mm find ~/dam --kind video | mm cat -l 1 --format json > video_l1.json` — structured metadata (resolution, duration, codec, fps, hash) for every video, ready for database import.

18. **Pre-screen videos by size before expensive L2 processing** — `mm find ~/inbox --kind video --max-size 100mb` filters to small files first. Run `mm cat -l 2` only on the filtered set to control LLM costs.

19. **Generate a searchable video index with scene descriptions** — `mm find ~/archive --kind video | mm cat -l 2 --format json > scenes.json` — each entry has keyframe-based scene descriptions. Load into a search index for text-based video retrieval.

20. **Audit a video archive for codec migration planning** — `mm find ~/archive --kind video | mm cat -l 1 --format json` reveals which files use legacy codecs (h264 baseline) vs modern (h265, av1). Prioritize transcoding by file size × codec age.

---

## Documents (8)

21. **Full-text search across a PDF collection** — `mm grep "force majeure" ~/contracts --kind document` searches extracted text from all PDFs/DOCX/PPTX. Returns file paths and matching lines — no manual opening of each file.

22. **Estimate LLM ingestion cost for a document archive** — `mm wc ~/legal --kind document` gives total file count, bytes, and estimated tokens. Multiply tokens by provider $/Mtok for a budget estimate.

23. **Identify scanned (image-only) PDFs that need OCR** — `mm cat scanned.pdf -l 1` returns `[No extractable text — this PDF may contain scanned images only]` for image-only PDFs. Batch-check: run across all PDFs and flag empty text responses.

24. **Extract text from a large PDF for RAG chunking** — `mm cat report.pdf -l 1` extracts full text via pypdfium2. Pipe directly to a chunker or embedding pipeline. Works on 500+ page documents.

25. **Compare document volume across directory groups** — `mm sql "SELECT parent, COUNT(*) as docs, ROUND(SUM(size)/1e6,1) as mb FROM files WHERE kind='document' GROUP BY parent ORDER BY mb DESC" --dir ~/shared` — shows which teams or projects have the most document mass.

26. **Search for specific clauses across contract PDFs** — `mm grep "indemnification" ~/contracts --kind document -C 2` — returns matching lines with 2 lines of context, across all extractable documents in the directory.

27. **Semantic search across documents** — `mm grep "revenue forecast" ~/reports -l 2 --kind document` — vector similarity search across embedded document chunks. Finds conceptually related content, not just keyword matches.

28. **Audit file formats in a document archive** — `mm sql "SELECT ext, COUNT(*) as n, ROUND(SUM(size)/1e6,1) as mb FROM files WHERE kind='document' GROUP BY ext ORDER BY n DESC" --dir ~/archive` — see PDF vs DOCX vs PPTX distribution.

---

## Images (8)

29. **Extract EXIF metadata for photo organization** — `mm find ~/photos --kind image | mm cat -l 1 --format json` returns dimensions, MIME, hash, and EXIF fields (camera, date, GPS) per file. Use for sorting into date/location folders.

30. **Find print-quality images by resolution** — `mm sql "SELECT name, width, height FROM files WHERE kind='image' AND width >= 3000 ORDER BY width DESC" --dir ~/assets` — filter for images that meet minimum print DPI requirements.

31. **Caption images for fine-tuning datasets** — `mm find ~/unlabeled --kind image | mm cat -l 2 --format json` — LLM-generated descriptions for each image. Each entry is an image-caption pair, directly usable as JSONL training data.

32. **Detect near-duplicate images** — mm computes perceptual hashes (pHash) via DCT in Rust. Two images with hamming distance < 8 are near-duplicates regardless of resize or mild compression — useful for deduplicating training sets or photo libraries.

33. **Audit image format adoption in a web project** — `mm sql "SELECT ext, COUNT(*) as n, ROUND(SUM(size)/1e6,1) as mb FROM files WHERE kind='image' GROUP BY ext ORDER BY mb DESC" --dir ~/site/public` — see how much bandwidth is wasted on PNG vs WebP vs AVIF.

34. **Estimate token cost for batch image processing** — Image token cost depends on resolution (tile-based). `mm find ~/products --kind image | mm cat -l 1 --format json` gives per-image dimensions.

35. **Find images without EXIF data** — `mm find ~/photos --kind image | mm cat -l 1 --format json` — images without camera/date/GPS fields are likely screenshots, downloads, or synthetic. Useful for separating photos from non-photo images.

36. **Semantic search across images** — `mm grep "sunset over ocean" ~/photos -l 2` — vector similarity search over image embeddings. Returns images whose LLM-generated captions are semantically close to the query.

---

## Audio (5)

37. **Catalog a podcast archive by duration** — `mm find ~/podcasts --kind audio | mm cat -l 1 --format json` extracts duration, codec, and sample rate per file. Sort by duration to find the longest episodes or estimate total listening time.

38. **Estimate transcription cost** — `mm find ~/audio --kind audio | mm cat -l 1 --format json` gives per-file duration. Sum durations and multiply by $/minute for Whisper, Rev, or Deepgram pricing.

39. **Find long recordings that need chunking** — Audio files over 80 seconds exceed Gemini's single-part embedding limit. `mm find ~/recordings --kind audio | mm cat -l 1 --format json` identifies files that need `audio_parts()` chunking before embedding.

40. **Summarize a meeting recording** — `mm cat meeting.mp3 -l 2` runs the full pipeline: audio extraction, transcription, and LLM summarization. Returns a structured summary without manual transcription.

41. **Assess a field recording SD card** — `mm find /Volumes/RECORDER --tree --depth 1` shows the directory structure. `mm wc /Volumes/RECORDER --kind audio` gives total duration and storage. Decide what to import before copying gigabytes.

---

## Code and development (5)

42. **Check if a codebase fits in an LLM context window** — `mm wc ~/project --kind code` gives file count, total bytes, and estimated tokens in one line. Instant answer: does this fit in 200K tokens?

43. **Find refactoring candidates by file size** — `mm find ~/project --kind code --sort size --reverse --limit 10` — the largest source files are often the ones most in need of splitting.

44. **Audit technical debt** — `mm grep "TODO\|FIXME\|HACK" ~/project --kind code --count` — per-file counts of debt markers. Pipe to an LLM for triage: `mm grep "TODO" --kind code | llm -s "Prioritize these by severity"`.

45. **Compare code volume across languages** — `mm sql "SELECT ext, COUNT(*) as files, ROUND(SUM(size)/1e3,1) as kb FROM files WHERE kind='code' GROUP BY ext ORDER BY files DESC" --dir ~/project` — understand the language mix in a polyglot repo.

46. **Generate a project overview for onboarding** — `mm find ~/project --tree --depth 3` produces a complete directory structure. Combined with `mm wc --by-kind`, a new team member immediately sees what types of content exist and how they're organized.

---

## Cross-modal (6)

47. **Triage a Downloads folder by media type** — `mm wc ~/Downloads --by-kind` shows the breakdown: how much is video, documents, images, etc. `mm find ~/Downloads --tree --depth 1` gives the visual layout. An agent uses this to propose an organization plan.

48. **Semantic search across all media types simultaneously** — `mm grep "quarterly revenue" ~/shared -l 2` searches PDFs (extracted text), images (via LLM captions), and video (via keyframe descriptions) in a single query using vector similarity.

49. **Build a multimodal evidence package** — For a construction project with permits (PDF), site photos (JPEG), and walkthrough video (MP4): `mm find ~/project --tree` shows everything, `mm wc --by-kind` quantifies it, and `mm cat -l 1` on each file gives structured metadata. One directory becomes a queryable index across all media types.

50. **Create an invoice summary from mixed document formats** — `mm find ~/invoices --kind document | mm cat -l 2 --format json` — the LLM extracts amounts, dates, and vendor names from PDFs, DOCX, and scanned documents. Output is structured JSON ready for aggregation.

51. **Estimate total LLM cost for a mixed-media directory** — `mm wc ~/data --by-kind --format json` gives token estimates broken down by kind.

52. **Batch-extract metadata for a digital asset manager** — `mm find ~/dam --format json > l0.json` for file-level metadata. `mm find ~/dam | mm cat -l 1 --format json > l1.json` for content metadata (text, dimensions, duration, hash, EXIF). Both are database-ready — one L0 scan at ~0.02ms/file, one L1 pass for richer extraction.
