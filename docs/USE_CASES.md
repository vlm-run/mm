# mm — Use Cases

Practical, realistic scenarios that mm solves today. Each use case maps to existing CLI commands and composable pipelines.

---

## Video

### Surveillance and security

1. **Inventory security footage by camera and date** — Index a NVR export directory. Use `mm find --kind video --sort modified` to list recordings chronologically, `mm cat -l 1` to extract duration/resolution/codec per file without playback.

2. **Estimate cloud storage cost for a video archive** — `mm wc ~/security-cams --kind video` gives total bytes and token estimates. Pipe to a cost model: `mm wc --format json | jq '.size'` to get raw bytes for S3 pricing calculations.

3. **Find the longest recording in a dashcam folder** — `mm sql "SELECT name, size FROM files WHERE kind='video' ORDER BY size DESC LIMIT 1" --dir ~/dashcam` — size correlates with duration for same-codec footage.

### Content creation

4. **Catalog a YouTube download folder** — `mm find ~/youtube --kind video --columns name,size,ext` lists all videos with format info. `mm cat -l 1` on each gives resolution, duration, codec — no ffprobe needed.

5. **Generate keyframe mosaics for video thumbnails** — `mm cat video.mp4 -l 2` extracts keyframes into a grid mosaic image. Use this for quick visual previews of long recordings without watching them.

6. **Describe a product demo video for alt-text** — `mm cat demo.mp4 -l 2` produces an LLM-generated scene-by-scene description. Pipe to clipboard: `mm cat demo.mp4 -l 2 | pbcopy`.

7. **Find all videos above a resolution threshold** — `mm sql "SELECT name, width, height, size FROM files WHERE kind='video' AND width >= 1920" --dir ~/media` — filter for HD+ content.

8. **Compare codec usage across a video library** — `mm find ~/videos --kind video | mm cat -l 1 --format json | jq '.[].video_codec'` — check how many files use h264 vs h265 vs av1.

### Education and training

9. **Index lecture recordings by duration for a syllabus** — `mm find ~/lectures --kind video | mm cat -l 1 --format json | jq '{name: .path, duration: .duration_s}'` — generate a table of lectures with runtimes for scheduling.

10. **Estimate transcription cost for a training video library** — `mm wc ~/training-videos --kind video` gives total size. Duration from L1 metadata feeds into Whisper/transcription pricing models.

11. **Caption a set of instructional videos for accessibility** — `mm find ~/course --kind video | mm cat -l 2` — LLM-generated descriptions for each video, usable as captions or metadata.

### Media management

12. **Find duplicate videos across drives** — `mm find /Volumes/Drive1 --kind video --format json` and compare hashes with `mm cat -l 1` output across volumes. The xxh3 hash identifies identical content.

13. **Split a video archive by year** — `mm sql "SELECT name, strftime('%Y', modified) as year FROM files WHERE kind='video'" --dir ~/archive` — shows the year breakdown for manual or scripted reorganization.

14. **Identify videos without audio tracks** — `mm find ~/videos --kind video | mm cat -l 1 --format json | jq 'select(.audio_codec == null) | .path'` — finds silent/muted recordings.

15. **Assess a GoPro SD card before import** — `mm find /Volumes/GOPRO --tree --depth 1` gives the file/size breakdown instantly. `mm wc /Volumes/GOPRO` shows total storage consumed.

### Compliance and legal

16. **Inventory body camera footage for a case** — `mm find ~/evidence --kind video --columns name,size,modified --sort modified` produces a chronological evidence list with file sizes for chain-of-custody documentation.

17. **Verify video integrity after transfer** — `mm cat video.mp4 -l 1` returns the xxh3 hash. Compare before/after transfer to confirm no corruption.

18. **Estimate token cost for sending video to an LLM** — `mm cat video.mp4 -l 1 --format json | jq '.duration_s'` gives duration. Multiply by keyframe rate and per-frame token estimate to get total cost.

### Video pipelines

19. **Build a video metadata CSV for a media asset manager** — `mm find ~/media --kind video | mm cat -l 1 --format json > video_metadata.json` — structured metadata for every video file, ready for database import.

20. **Pre-screen videos before expensive LLM processing** — `mm wc ~/inbox --kind video` shows total size. `mm find ~/inbox --kind video --max-size 100mb` filters to processable files. Run L2 only on the filtered set.

---

## Documents (PDF, DOCX, PPTX)

21. **Search across hundreds of PDFs for a legal term** — `mm grep "force majeure" ~/contracts --kind document` searches extracted text across all document types.

22. **Estimate LLM cost to process a document archive** — `mm wc ~/legal --kind document --format json` gives total token estimate. Multiply by provider price per Mtok.

23. **Find all scanned (image-only) PDFs** — `mm find ~/docs --ext pdf | mm cat -l 1 --format json | jq 'select(.text == "" or .text == null) | .path'` — identifies PDFs that need OCR.

24. **Extract text from a 500-page PDF for RAG chunking** — `mm cat large_report.pdf -l 1` extracts full text via pypdfium2. Pipe to a chunker or directly to an embedding pipeline.

25. **Create a document inventory with page counts** — `mm find ~/archive --kind document | mm cat -l 1 --format json | jq '{path: .path, pages: .pages}'` — quick audit of document sizes.

26. **Compare document storage across departments** — `mm sql "SELECT parent, COUNT(*) as docs, ROUND(SUM(size)/1e6,1) as mb FROM files WHERE kind='document' GROUP BY parent ORDER BY mb DESC" --dir ~/shared`.

---

## Images

27. **Organize photos by EXIF date** — `mm find ~/photos --kind image | mm cat -l 1 --format json | jq '{path: .path, date: .exif_date}'` — extract dates for sorting into year/month folders.

28. **Find all high-resolution images for print** — `mm sql "SELECT name, width, height, size FROM files WHERE kind='image' AND width >= 3000" --dir ~/assets` — filter for print-quality images.

29. **Caption images for a dataset** — `mm find ~/unlabeled --kind image | mm cat -l 2 --format json` — LLM-generated descriptions for each image. Output as JSONL for fine-tuning.

30. **Find near-duplicate images via perceptual hash** — mm computes pHash for every image at L1. Images with hamming distance < 8 are near-duplicates — useful for deduplication before training.

31. **Audit image formats in a web project** — `mm sql "SELECT ext, COUNT(*) as n, ROUND(SUM(size)/1e6,1) as mb FROM files WHERE kind='image' GROUP BY ext ORDER BY n DESC" --dir ~/site/assets` — check PNG vs WebP vs AVIF adoption.

32. **Estimate token cost for a batch of product photos** — `mm wc ~/products --kind image` gives file count. Each image's token cost depends on resolution: `mm find ~/products --kind image | mm cat -l 1 --format json | jq '.width, .height'` feeds into the tile-based token estimator.

---

## Audio

33. **Catalog a podcast archive** — `mm find ~/podcasts --kind audio --columns name,size,ext --sort size --reverse` lists episodes by size. `mm cat -l 1` on each gives duration and codec.

34. **Estimate transcription cost for an audio library** — `mm wc ~/audio --kind audio` gives total bytes. `mm find ~/audio --kind audio | mm cat -l 1 --format json | jq '.duration_s'` gives total duration for Whisper pricing.

35. **Find audio files over 1 hour** — `mm find ~/recordings --kind audio | mm cat -l 1 --format json | jq 'select(.duration_s > 3600) | .path'`.

36. **Transcribe and summarize a meeting recording** — `mm cat meeting.mp3 -l 2` sends audio through the LLM pipeline (extraction + transcription + summarization).

---

## Code and development

37. **Token budget check before sending a codebase to an LLM** — `mm wc ~/project --kind code` — instant answer: does this fit in a 200K context window?

38. **Find the largest source files** — `mm find ~/project --kind code --sort size --reverse --limit 10` — identify refactoring candidates.

39. **Search for TODO/FIXME across all code** — `mm grep "TODO\|FIXME" ~/project --kind code --count` — summary of technical debt per file.

40. **Generate a project structure description** — `mm find ~/project --tree --depth 3 | llm -s "Describe this project"` — automatic README material.

41. **Compare code volume across languages** — `mm sql "SELECT ext, COUNT(*) as files, ROUND(SUM(size)/1e3,1) as kb FROM files WHERE kind='code' GROUP BY ext ORDER BY files DESC" --dir ~/project`.

---

## Cross-modal and agentic

42. **Triage a Downloads folder** — `mm wc ~/Downloads --by-kind` shows the breakdown. `mm find ~/Downloads --tree --depth 1` gives visual structure. An agent can then organize by kind and date.

43. **Build a multimodal project digest** — Combine `mm find --tree`, `mm wc --by-kind`, and `mm grep "TODO"` into a single prompt for an LLM to generate a standup summary.

44. **Audit storage across file types** — `mm sql "SELECT kind, COUNT(*) as n, ROUND(SUM(size)/1e9,2) as gb FROM files GROUP BY kind ORDER BY gb DESC" --dir ~/` — whole-disk breakdown by semantic kind.

45. **Find all files modified today** — `mm sql "SELECT name, kind, size FROM files WHERE date(modified) = date('now') ORDER BY modified DESC" --dir ~/project`.

46. **Semantic search across all media types** — `mm grep "quarterly revenue" ~/shared -l 2` — searches PDFs, images (via captions), and video (via keyframe descriptions) with vector similarity.

47. **Export a file inventory to Parquet** — `mm find ~/data --format json | duckdb -c "COPY (SELECT * FROM read_json('/dev/stdin')) TO 'inventory.parquet' (FORMAT PARQUET)"`.

48. **Generate dataset labels from a media directory** — `mm find ~/unlabeled --kind image | mm cat -l 2 --format json` produces image-caption pairs. Redirect to JSONL for fine-tuning workflows.

49. **Pre-flight check before uploading to a cloud service** — `mm wc ~/upload` gives total size, file count, and token estimate. `mm find ~/upload --min-size 100mb` flags oversized files before the upload starts.

50. **Create an invoice summary from scanned documents** — `mm find ~/invoices --kind document | mm cat -l 2 --format json` — LLM extracts amounts and dates from each document. Pipe to `jq` to build a markdown table.

51. **Monitor a recording directory for new files** — `mm find ~/recordings --sort modified --reverse --limit 5` — quick check of the most recent additions without navigating the filesystem.

52. **Batch-extract metadata for a digital asset manager** — `mm find ~/dam --format json > manifest.json` — L0 metadata for every file. `mm find ~/dam | mm cat -l 1 --format json > l1.json` — L1 content metadata. Both are database-ready.
