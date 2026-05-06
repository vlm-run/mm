#!/usr/bin/env bash
# bench_cli_universal_assistant_image.sh — image-focused universal CLI bench.
#
# Variant of bench_cli_universal_assistant.sh that targets a large
# image-only directory (~100+ images) drawn from the public HuggingFace
# dataset vlm-run/FineVision-vlmbench-mini. Tasks are heavily weighted
# toward `mm cat` (the workhorse), with `mm grep` (incl. --semantic)
# and a representative `mm find` / `mm wc` / `mm sql` task.
#
# Usage:
#   ./benchmarks/bench_cli_universal_assistant_image.sh                         # fast mode (5 tasks)
#   ./benchmarks/bench_cli_universal_assistant_image.sh --mode full             # all 22 tasks
#   ./benchmarks/bench_cli_universal_assistant_image.sh --tasks 10              # first N
#   ./benchmarks/bench_cli_universal_assistant_image.sh --assistant claude      # one assistant
#   ./benchmarks/bench_cli_universal_assistant_image.sh --assistant claude,codex
#   ./benchmarks/bench_cli_universal_assistant_image.sh --timeout 60
#
# Output YAML feeds benchmarks/universal_cli/visualize_universal.py — same
# schema as the multimodal bench, so the report works unchanged.
#
# Task budget (full mode, 15 tasks):
#    9 cat  (~60%) — all --mode fast (accurate-mode cat tasks were removed
#                    on purpose: every one of them adds a per-call VLM
#                    round-trip that dominates wall time, which caps the
#                    measurable with/without-mm speedup. Fast mode is
#                    where the upper bound lives.)
#    2 grep (~13%) — both --semantic, with different queries (regex grep
#                    is a no-op on image dirs, since binary kinds are
#                    skipped unless --semantic is passed)
#    3 misc (~20%) — 1 find + 1 wc + 1 sql (wc moved into fast mode so
#                    the smoke test exercises a bulk-aggregate call)
#    1 peek (~7%)  — single-image raw metadata (dims + EXIF + hash, no LLM)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="${SCRIPT_DIR}/universal_cli"

BENCH_DIR="${SCRIPT_DIR}/data/universal-bench/images"
BENCH_LABEL="Image"
FAST_TASKS=5
SUPPORTED_ASSISTANTS="claude codex gemini"

# shellcheck source=universal_cli/lib_common.sh
source "${LIB_DIR}/lib_common.sh"

# Sample images picked dynamically after setup_data — a small jpg, a larger
# image (likely PNG), and a cohort for batch ops. Task registration runs
# after setup, so files are guaranteed present.
SAMPLE_SMALL=""
SAMPLE_LARGE=""
SAMPLE_THIRD=""

setup_data() {
  if [ -f "${BENCH_DIR}/.ready" ]; then
    local n
    n="$(find "${BENCH_DIR}" -type f ! -name '.ready' ! -name '.source.parquet' ! -name '.DS_Store' | wc -l | tr -d ' ')"
    echo "Image bench data ready: ${n} images at ${BENCH_DIR}"
    return
  fi
  echo "Image bench data missing — downloading FineVision-vlmbench-mini..."
  uv run python "${LIB_DIR}/download_finevision_images.py"
  if [ ! -f "${BENCH_DIR}/.ready" ]; then
    echo "Error: downloader did not produce ${BENCH_DIR}/.ready"
    exit 1
  fi
}

# Pick a few sample files for single-file tasks. Smallest is fast/cheap; a
# larger image stresses metadata extraction; a third gives variety.
_pick_samples() {
  # Use stat-by-size sort to pick deterministically.
  if command -v gstat &>/dev/null; then
    SAMPLE_SMALL="$(find "${BENCH_DIR}" -type f ! -name '.*' -exec gstat -c '%s %n' {} + 2>/dev/null | sort -n | head -1 | cut -d' ' -f2-)"
    SAMPLE_LARGE="$(find "${BENCH_DIR}" -type f ! -name '.*' -exec gstat -c '%s %n' {} + 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-)"
  else
    SAMPLE_SMALL="$(find "${BENCH_DIR}" -type f ! -name '.*' -exec stat -f '%z %N' {} + 2>/dev/null | sort -n | head -1 | cut -d' ' -f2-)"
    SAMPLE_LARGE="$(find "${BENCH_DIR}" -type f ! -name '.*' -exec stat -f '%z %N' {} + 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-)"
  fi
  SAMPLE_THIRD="$(find "${BENCH_DIR}" -type f ! -name '.*' | sort | awk 'NR==5{print; exit}')"
  if [ -z "${SAMPLE_THIRD}" ]; then
    SAMPLE_THIRD="${SAMPLE_SMALL}"
  fi
  if [ -z "${SAMPLE_SMALL}" ] || [ -z "${SAMPLE_LARGE}" ]; then
    echo "Error: no images found in ${BENCH_DIR}"
    exit 1
  fi
}

register_tasks() {
  _pick_samples

  # ============================================================
  # Fast mode (first 5): cat fast single, cat fast batch, two
  # --semantic greps, and the wc bulk-aggregate smoke test. Only
  # fast-mode tasks remain — accurate-mode runs add a per-task
  # VLM call that dominates wall time and compresses the visible
  # speedup, so they're excluded from this bench.
  # ============================================================

  # 1. cat fast — single image metadata (the canonical "mm cat" call)
  add_task "image_cat_fast_single" \
    "Describe what is shown in this image. Include dimensions, format, and any EXIF metadata." \
    "mm cat '${SAMPLE_SMALL}' --mode fast --format json" \
    "${SAMPLE_SMALL}"

  # 2. cat fast — batch metadata (the bulk pattern)
  add_task "image_cat_fast_batch" \
    "Extract metadata for every image in this directory: name, dimensions, format, and size. Return as JSON." \
    "mm find '${BENCH_DIR}' --kind image --format json | mm cat --mode fast --format json -y"

  # 3. grep --semantic — vector search over image captions (people)
  #    (Plain regex grep is a no-op on image dirs — binary kinds are skipped
  #     unless --semantic is passed, so both grep tasks here exercise the
  #     semantic path with different queries.)
  add_task "image_grep_semantic_people" \
    "Search this image collection for pictures showing a person or people. Return the most relevant matches." \
    "mm grep 'person or people' '${BENCH_DIR}' --kind image --semantic --format json"

  # 4. grep --semantic — vector search over image captions (outdoor scene)
  add_task "image_grep_semantic_outdoor" \
    "Search this image collection for outdoor scenes — landscapes, streets, sky, nature. Return the top matches." \
    "mm grep 'outdoor landscape or street scene' '${BENCH_DIR}' --kind image --semantic --format json"

  # 5. wc — bulk token cost estimate for full collection (#34)
  add_task "image_wc_token_cost" \
    "How many tokens would it cost to process every image in this directory with a vision LLM? Show counts and total." \
    "mm wc '${BENCH_DIR}' --kind image --format json"

  # ============================================================
  # Full mode (6-14): broader coverage of cat fast + find + sql.
  # ============================================================

  # 6. cat fast — different image (stresses cache-cold path)
  add_task "image_cat_fast_large" \
    "What are the dimensions, format, and file size of this image?" \
    "mm cat '${SAMPLE_LARGE}' --mode fast --format json" \
    "${SAMPLE_LARGE}"

  # 7. cat fast — head of stdin pipe (#29 EXIF for organization)
  add_task "image_cat_fast_head" \
    "Extract EXIF metadata for the first 10 images in this directory: camera, capture date, GPS if present." \
    "mm find '${BENCH_DIR}' --kind image --format json | head -10 | mm cat --mode fast --format json -y"

  # 8. cat fast — screenshots vs photos (#35 — split by EXIF presence)
  add_task "image_cat_fast_screenshot_audit" \
    "Identify which images in this directory look like screenshots or synthetic images vs real photographs (e.g. by absence of camera EXIF)." \
    "mm find '${BENCH_DIR}' --kind image --format json | mm cat --mode fast --format json -y"

  # 9. cat fast — content hash inventory for dedup pipeline
  add_task "image_cat_fast_hash_inventory" \
    "Compute a content hash per image in this directory for a deduplication pipeline. Output filename + hash + size." \
    "mm find '${BENCH_DIR}' --kind image --columns name,size,xxh3 --format json"

  # 10. cat fast — dimensions for VLM token cost estimation (#34)
  add_task "image_cat_fast_dimension_inventory" \
    "Per-image dimensions in this directory, so we can estimate VLM token cost for batch processing." \
    "mm find '${BENCH_DIR}' --kind image --columns name,width,height,size --format json"

  # 11. cat fast — third sample (different file, single)
  add_task "image_cat_fast_third" \
    "Print the dimensions and format of this image as JSON." \
    "mm cat '${SAMPLE_THIRD}' --mode fast --format json" \
    "${SAMPLE_THIRD}"

  # 12. cat fast — aspect-ratio audit
  add_task "image_cat_fast_aspect_ratio" \
    "Group the images in this directory by aspect ratio bucket (landscape, portrait, square)." \
    "mm find '${BENCH_DIR}' --kind image --columns name,width,height --format json"

  # ---- Misc: find / sql (wc already in fast mode) ----

  # 13. find — tree overview for onboarding
  add_task "image_find_tree" \
    "Give me a tree of this image directory showing structure, file types, and sizes." \
    "mm find '${BENCH_DIR}' --tree --depth 2 --format json"

  # 14. sql — hi-res filter (#30)
  add_task "image_sql_hires" \
    "Find every image in this directory with width >= 1000 pixels. Show name, dimensions, and size." \
    "mm sql \"SELECT name, width, height, size FROM files WHERE kind='image' AND width >= 1000 ORDER BY width DESC\" --dir '${BENCH_DIR}' --format json"

  # 15. peek — single-image raw metadata (dims + EXIF + hash).
  add_task "image_peek_single" \
    "Extract raw file metadata for this image: exact dimensions, format, content hash, and any EXIF (camera, capture date, GPS) — without describing the contents." \
    "mm peek '${SAMPLE_SMALL}' --format json" \
    "${SAMPLE_SMALL}"
}

bench_main "$@"
