#!/usr/bin/env bash
# bench_cli_universal_assistant.sh — benchmark universal CLI assistants with/without mm
#
# Measures wall-clock time for AI coding assistants to complete multimodal
# directory tasks. Compares "with mm" (pre-extracted context piped in) vs
# "without mm" (assistant explores on its own via tool calls).
#
# Supported assistants: claude (Claude Code), codex (Codex CLI), gemini (Gemini CLI)
#
# Usage:
#   ./benchmarks/bench_cli_universal_assistant.sh                    # all detected assistants
#   ./benchmarks/bench_cli_universal_assistant.sh --assistant claude  # single assistant
#   BENCH_RUNS=5 ./benchmarks/bench_cli_universal_assistant.sh       # custom run count
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/data"
BENCH_DIR="${DATA_DIR}/universal-bench"
RESULTS_DIR="${SCRIPT_DIR}/universal_cli"
RUNS="${BENCH_RUNS:-3}"
ASSISTANT_FILTER="${1:-}"  # --assistant <name> or empty for all

GCS="https://storage.googleapis.com/vlm-data-public-prod"
TINY_URL="${GCS}/mmbench/mmbench-tiny.tar.gz"

# Parse --assistant flag
SELECTED_ASSISTANT=""
if [ "${ASSISTANT_FILTER}" = "--assistant" ]; then
  SELECTED_ASSISTANT="${2:-}"
  if [ -z "${SELECTED_ASSISTANT}" ]; then
    echo "Error: --assistant requires a value (claude, codex, gemini)"
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------
if ! command -v hyperfine &>/dev/null; then
  echo "Error: hyperfine not found. First install Hyperfine, e.g., on Darwin with: brew install hyperfine"
  exit 1
fi

if ! command -v mm &>/dev/null; then
  echo "Error: mm not found. Install with: uv pip install mm-ctx"
  exit 1
fi

# Detect available assistants
declare -a ASSISTANTS=()
for cmd in claude codex gemini; do
  if [ -n "${SELECTED_ASSISTANT}" ] && [ "${cmd}" != "${SELECTED_ASSISTANT}" ]; then
    continue
  fi
  if command -v "${cmd}" &>/dev/null; then
    ASSISTANTS+=("${cmd}")
  fi
done

if [ ${#ASSISTANTS[@]} -eq 0 ]; then
  echo "Error: no assistants found. Install at least one of: claude, codex, gemini"
  exit 1
fi

echo "Detected assistants: ${ASSISTANTS[*]}"

# ---------------------------------------------------------------------------
# Assistant wrapper: run a prompt in non-interactive mode
# ---------------------------------------------------------------------------
assistant_cmd() {
  local name="$1"
  local prompt="$2"
  local context="${3:-}"  # optional stdin context

  case "${name}" in
    claude)
      if [ -n "${context}" ]; then
        echo "echo '${context}' | claude -p '${prompt}'"
      else
        echo "claude -p '${prompt}'"
      fi
      ;;
    codex)
      if [ -n "${context}" ]; then
        echo "echo '${context}' | codex -q '${prompt}'"
      else
        echo "codex -q '${prompt}'"
      fi
      ;;
    gemini)
      if [ -n "${context}" ]; then
        echo "echo '${context}' | gemini -p '${prompt}'"
      else
        echo "gemini -p '${prompt}'"
      fi
      ;;
  esac
}

# Build the hyperfine command for a task (stdin piped context)
assistant_pipe_cmd() {
  local name="$1"
  local mm_cmd="$2"
  local prompt="$3"

  case "${name}" in
    claude) echo "${mm_cmd} | claude -p '${prompt}'" ;;
    codex)  echo "${mm_cmd} | codex -q '${prompt}'" ;;
    gemini) echo "${mm_cmd} | gemini -p '${prompt}'" ;;
  esac
}

# ---------------------------------------------------------------------------
# Download & curate benchmark directory
# ---------------------------------------------------------------------------
setup_data() {
  if [ -f "${BENCH_DIR}/.ready" ]; then
    echo "Benchmark data already prepared at ${BENCH_DIR}"
    return
  fi

  echo "Preparing benchmark data..."
  mkdir -p "${BENCH_DIR}"/{docs,media/samples,reports/schema}

  # Download mmbench-tiny (reuse if exists)
  if [ ! -d "${DATA_DIR}/mmbench-tiny" ]; then
    echo "  Downloading mmbench-tiny (~43MB)..."
    mkdir -p "${DATA_DIR}"
    curl -sL "${TINY_URL}" | tar xzf - -C "${DATA_DIR}"
  fi

  # Helper: download a GCS file to a local path
  dl() {
    local gcs_key="$1"
    local dest="$2"
    if [ ! -f "${dest}" ]; then
      echo "  Downloading $(basename "${dest}")..."
      curl -sL "${GCS}/${gcs_key}" -o "${dest}"
    fi
  }

  # --- Top level (depth 0): mixed types ---
  cp "${DATA_DIR}/mmbench-tiny/1-vqa-car.jpg"          "${BENCH_DIR}/photo.jpg"
  cp "${DATA_DIR}/mmbench-tiny/BillDownload-8pg.pdf"    "${BENCH_DIR}/bill.pdf"
  cp "${DATA_DIR}/mmbench-tiny/bakery.mp4"              "${BENCH_DIR}/bakery.mp4"
  dl "hub/examples/audio.transcription/palantir_q3_2024_earnings_webcast.mp3" \
     "${BENCH_DIR}/earnings-call.mp3"
  dl "hub/examples/mixed-files/basic-data.csv"          "${BENCH_DIR}/data.csv"
  dl "hub/examples/mixed-files/nested-objects.json"     "${BENCH_DIR}/config.json"
  dl "hub/examples/mixed-files/simple.txt"              "${BENCH_DIR}/readme.txt"

  # --- docs/ (depth 1): professional documents ---
  dl "hub/examples/finance.sec-filings/tsla-8k.pdf"    "${BENCH_DIR}/docs/sec-filing.pdf"
  dl "hub/examples/healthcare.patient-intake/fl-intake-form.pdf" \
     "${BENCH_DIR}/docs/patient-intake.pdf"
  dl "hub/examples/mixed-files/complex-nested.xml"      "${BENCH_DIR}/docs/schema.xml"
  dl "hub/examples/document.invoice/sample-invoice.pdf" "${BENCH_DIR}/docs/invoice.pdf"

  # --- media/ (depth 1): images + video ---
  dl "hub/examples/video.dashcam/00895.mp4"             "${BENCH_DIR}/media/dashcam.mp4"
  dl "hub/examples/retail.ecommerce-product-caption/Electronics%20-%20Kindle.webp" \
     "${BENCH_DIR}/media/product.webp"
  dl "hub/examples/image.caption/furniture-colorful.jpg" "${BENCH_DIR}/media/furniture.jpg"

  # --- media/samples/ (depth 2): audio samples ---
  dl "hub/examples/mixed-files/wav_48000Hz_24bit_stereo.wav" \
     "${BENCH_DIR}/media/samples/recording.wav"
  dl "hub/examples/mixed-files/file_example_GIF_1MB.gif" \
     "${BENCH_DIR}/media/samples/animation.gif"

  # --- reports/ (depth 1) + reports/schema/ (depth 2) ---
  dl "hub/examples/finance.sec-filings/nvidia_form_10k.pdf" \
     "${BENCH_DIR}/reports/nvidia-10k.pdf"
  dl "hub/examples/document.invoice/sample_invoice.json" \
     "${BENCH_DIR}/reports/schema/invoice-response.json"

  touch "${BENCH_DIR}/.ready"

  local file_count
  file_count="$(find "${BENCH_DIR}" -type f ! -name '.ready' ! -name '.DS_Store' | wc -l | tr -d ' ')"
  local total_size
  total_size="$(du -sh "${BENCH_DIR}" | awk '{print $1}')"
  echo "  Ready: ${file_count} files, ${total_size}"
}

# ---------------------------------------------------------------------------
# Benchmark tasks
# ---------------------------------------------------------------------------
# Each task tests a realistic AI assistant workflow on multimodal directories.
# "with mm" pipes pre-extracted context; "without mm" lets the assistant explore.

run_benchmarks() {
  local ts
  ts="$(date +%Y%m%d_%H%M%S)"
  mkdir -p "${RESULTS_DIR}"
  local result_file="${RESULTS_DIR}/run_${ts}.yaml"

  echo ""
  echo "=== Universal CLI Assistant Benchmark ==="
  echo "Data: ${BENCH_DIR}"
  echo "Assistants: ${ASSISTANTS[*]}"
  echo "Runs per command: ${RUNS}"
  echo "Results: ${result_file}"
  echo ""

  # Write YAML header
  cat > "${result_file}" <<EOF
# Universal CLI Assistant Benchmark
# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
# Assistants: ${ASSISTANTS[*]}
# Runs: ${RUNS}
# Data: ${BENCH_DIR}
---
meta:
  timestamp: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  assistants: [$(printf '"%s",' "${ASSISTANTS[@]}" | sed 's/,$//')]
  runs: ${RUNS}
  data_dir: "${BENCH_DIR}"
  file_count: $(find "${BENCH_DIR}" -type f ! -name '.ready' ! -name '.DS_Store' | wc -l | tr -d ' ')
  total_size_bytes: $(find "${BENCH_DIR}" -type f ! -name '.ready' ! -name '.DS_Store' -exec stat -f '%z' {} + 2>/dev/null | awk '{s+=$1}END{print s}' || find "${BENCH_DIR}" -type f ! -name '.ready' ! -name '.DS_Store' -exec stat -c '%s' {} + 2>/dev/null | awk '{s+=$1}END{print s}')

tasks:
EOF

  # -----------------------------------------------------------------------
  # Cross-modal tasks (USE_CASES.md #47, #49, #51, #52, #53)
  # -----------------------------------------------------------------------

  # 1. Directory survey — triage a mixed folder by media type (#47)
  run_task_log 1 "directory_survey" \
    "List every file in this directory tree with its type, size, and path. Group by file type." \
    "mm find ${BENCH_DIR} --format json" \
    "${result_file}"

  # 2. Cross-file analysis — estimate LLM cost for mixed-media (#51)
  run_task_log 2 "token_cost_estimate" \
    "Analyze this directory: how many files per type, total size per type, and which are the 3 largest files? Estimate total LLM token cost." \
    "mm wc ${BENCH_DIR} --by-kind --format json" \
    "${result_file}"

  # 3. Find files modified today — recent activity audit (#52)
  run_task_log 3 "recent_files" \
    "Find all files modified in the last 7 days, sorted by modification time. Show name, type, size, and date." \
    "mm sql \"SELECT name, kind, size, modified FROM files ORDER BY modified DESC\" --dir ${BENCH_DIR} --format json" \
    "${result_file}"

  # 4. Batch metadata extraction — digital asset manager (#53)
  run_task_log 4 "batch_metadata" \
    "Extract structured metadata for every file in this directory: name, type, size, dimensions (if image/video), duration (if audio/video), and content hash." \
    "mm find ${BENCH_DIR} --format json" \
    "${result_file}"

  # 5. Build a multimodal evidence package (#49)
  run_task_log 5 "evidence_package" \
    "Create an inventory of this directory as an evidence package: list every file with its hash, size, type, and modification date. Flag any files that are unusually large." \
    "mm find ${BENCH_DIR} --columns name,kind,size,modified --format json" \
    "${result_file}"

  # -----------------------------------------------------------------------
  # Document tasks (USE_CASES.md #21, #22, #24, #25, #28)
  # -----------------------------------------------------------------------

  # 6. PDF content extraction — full text for RAG (#24)
  run_task_log 6 "pdf_extraction" \
    "Extract the text from this PDF and provide a structured summary of its contents." \
    "mm cat '${BENCH_DIR}/docs/sec-filing.pdf' --mode fast" \
    "${result_file}" \
    "${BENCH_DIR}/docs/sec-filing.pdf"

  # 7. Full-text search across documents (#21)
  run_task_log 7 "document_search" \
    "Search all document files for mentions of financial amounts or dollar values and list where they appear." \
    "mm grep '\\\$[0-9]' ${BENCH_DIR} --kind document --format json" \
    "${result_file}"

  # 8. Estimate LLM ingestion cost for documents (#22)
  run_task_log 8 "document_token_cost" \
    "How many tokens would it cost to ingest all documents in this directory into an LLM? Count files and estimate tokens." \
    "mm wc ${BENCH_DIR} --kind document --format json" \
    "${result_file}"

  # 9. Compare document volume across subdirectories (#25)
  run_task_log 9 "document_volume_by_dir" \
    "Compare document volume across subdirectories: how many documents and total MB in each folder?" \
    "mm sql \"SELECT parent, COUNT(*) as docs, ROUND(SUM(size)/1e6,1) as mb FROM files WHERE kind='document' GROUP BY parent ORDER BY mb DESC\" --dir ${BENCH_DIR} --format json" \
    "${result_file}"

  # 10. Audit document formats (#28)
  run_task_log 10 "document_format_audit" \
    "What document formats exist in this directory? Show extension, count, and total size for each format." \
    "mm sql \"SELECT ext, COUNT(*) as n, ROUND(SUM(size)/1e6,1) as mb FROM files WHERE kind='document' GROUP BY ext ORDER BY n DESC\" --dir ${BENCH_DIR} --format json" \
    "${result_file}"

  # -----------------------------------------------------------------------
  # Image tasks (USE_CASES.md #29, #30, #33, #34)
  # -----------------------------------------------------------------------

  # 11. Image metadata extraction — EXIF for organization (#29)
  run_task_log 11 "image_metadata" \
    "Describe what is shown in this image. Include dimensions, format, and any EXIF metadata." \
    "mm cat '${BENCH_DIR}/photo.jpg' --mode fast --format json" \
    "${result_file}" \
    "${BENCH_DIR}/photo.jpg"

  # 12. Find high-resolution images (#30)
  run_task_log 12 "hires_images" \
    "Find all images in this directory with width >= 1000 pixels. Show name, dimensions, and size." \
    "mm sql \"SELECT name, width, height, size FROM files WHERE kind='image' AND width >= 1000 ORDER BY width DESC\" --dir ${BENCH_DIR} --format json" \
    "${result_file}"

  # 13. Audit image formats (#33)
  run_task_log 13 "image_format_audit" \
    "What image formats are used in this directory? Show format, count, and total size. Suggest which could be converted to WebP for size savings." \
    "mm sql \"SELECT ext, COUNT(*) as n, ROUND(SUM(size)/1e6,1) as mb FROM files WHERE kind='image' GROUP BY ext ORDER BY mb DESC\" --dir ${BENCH_DIR} --format json" \
    "${result_file}"

  # 14. Estimate token cost for batch image processing (#34)
  run_task_log 14 "image_token_cost" \
    "How many tokens would it cost to process all images in this directory with a vision LLM? List each image with its dimensions and estimated tokens." \
    "mm wc ${BENCH_DIR} --kind image --format json" \
    "${result_file}"

  # -----------------------------------------------------------------------
  # Video tasks (USE_CASES.md #3, #5, #8, #10)
  # -----------------------------------------------------------------------

  # 15. Video metadata extraction — catalog without playback (#5)
  run_task_log 15 "video_metadata" \
    "Extract metadata from this video: resolution, duration, codec, and file size." \
    "mm cat '${BENCH_DIR}/bakery.mp4' --mode fast --format json" \
    "${result_file}" \
    "${BENCH_DIR}/bakery.mp4"

  # 16. Identify HD vs SD recordings (#3)
  run_task_log 16 "video_resolution_check" \
    "List all video files and their resolution. Which are HD (>=720p) and which are SD?" \
    "mm sql \"SELECT name, width, height, size FROM files WHERE kind='video'\" --dir ${BENCH_DIR} --format json" \
    "${result_file}"

  # 17. Compare codec usage across videos (#8)
  run_task_log 17 "video_codec_audit" \
    "What video codecs and containers are used in this directory? Show per-file codec info." \
    "mm find ${BENCH_DIR} --kind video --format json" \
    "${result_file}"

  # -----------------------------------------------------------------------
  # Audio tasks (USE_CASES.md #37, #38)
  # -----------------------------------------------------------------------

  # 18. Audio metadata — catalog by duration (#37)
  run_task_log 18 "audio_metadata" \
    "Extract metadata from this audio file: duration, codec, sample rate, and file size." \
    "mm cat '${BENCH_DIR}/earnings-call.mp3' --mode fast --format json" \
    "${result_file}" \
    "${BENCH_DIR}/earnings-call.mp3"

  # -----------------------------------------------------------------------
  # Code/dev tasks (USE_CASES.md #42, #46)
  # -----------------------------------------------------------------------

  # 19. Tree overview for onboarding (#46)
  run_task_log 19 "tree_overview" \
    "Generate a directory tree of this folder showing structure, file types, and sizes at each level. This is for onboarding a new team member." \
    "mm find ${BENCH_DIR} --tree --depth 3 --format json" \
    "${result_file}"

  # 20. Codebase/project token budget (#42)
  run_task_log 20 "project_token_budget" \
    "Does the content of this directory fit in a 200K token LLM context window? Show total tokens, breakdown by file type, and list files that are too large to include." \
    "mm wc ${BENCH_DIR} --by-kind --format json" \
    "${result_file}"

  echo ""
  echo "=== Results written to ${result_file} ==="
}

run_task_log() {
  local n="$1"; shift
  echo ""
  echo "--- Task ${n}/20: $1 ---"
  run_task "$@"
}

run_task() {
  local task_name="$1"
  local prompt="$2"
  local mm_cmd="$3"
  local result_file="$4"
  local target_file="${5:-}"  # optional specific file for "without mm"

  cat >> "${result_file}" <<EOF

  - name: "${task_name}"
    prompt: "$(echo "${prompt}" | sed 's/"/\\"/g')"
    mm_cmd: "$(echo "${mm_cmd}" | sed 's/"/\\"/g')"
    results:
EOF

  for asst in "${ASSISTANTS[@]}"; do
    echo "  [${asst}] ${task_name}"

    # --- With mm ---
    local with_cmd
    with_cmd="$(assistant_pipe_cmd "${asst}" "${mm_cmd}" "${prompt}")"

    local with_json="${RESULTS_DIR}/.tmp_with_${asst}_${task_name}.json"
    echo "    with mm: ${with_cmd}"
    hyperfine --warmup 1 --min-runs "${RUNS}" --export-json "${with_json}" \
      --command-name "${asst}+mm" \
      "${with_cmd}" 2>&1 | tail -1 || true

    # --- Without mm ---
    local without_prompt
    if [ -n "${target_file}" ]; then
      without_prompt="Given the file at ${target_file}: ${prompt}"
    else
      without_prompt="Given the directory at ${BENCH_DIR}: ${prompt}"
    fi
    local without_cmd
    without_cmd="$(assistant_cmd "${asst}" "${without_prompt}")"

    local without_json="${RESULTS_DIR}/.tmp_without_${asst}_${task_name}.json"
    echo "    without mm: ${without_cmd}"
    hyperfine --warmup 1 --min-runs "${RUNS}" --export-json "${without_json}" \
      --command-name "${asst}" \
      "${without_cmd}" 2>&1 | tail -1 || true

    # Extract timings and append to YAML
    local with_mean with_stddev without_mean without_stddev speedup
    with_mean="$(jq -r '.results[0].mean // 0' "${with_json}" 2>/dev/null || echo 0)"
    with_stddev="$(jq -r '.results[0].stddev // 0' "${with_json}" 2>/dev/null || echo 0)"
    without_mean="$(jq -r '.results[0].mean // 0' "${without_json}" 2>/dev/null || echo 0)"
    without_stddev="$(jq -r '.results[0].stddev // 0' "${without_json}" 2>/dev/null || echo 0)"

    if [ "$(echo "${with_mean} > 0" | bc -l 2>/dev/null || echo 0)" = "1" ]; then
      speedup="$(echo "scale=2; ${without_mean} / ${with_mean}" | bc -l 2>/dev/null || echo "n/a")"
    else
      speedup="n/a"
    fi

    cat >> "${result_file}" <<EOF
      - assistant: "${asst}"
        with_mm:
          mean_s: ${with_mean}
          stddev_s: ${with_stddev}
        without_mm:
          mean_s: ${without_mean}
          stddev_s: ${without_stddev}
        speedup: "${speedup}x"
EOF

    rm -f "${with_json}" "${without_json}"
  done
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
setup_data
run_benchmarks
