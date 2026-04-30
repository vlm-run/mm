#!/usr/bin/env bash
# bench_universal_tiny.sh — universal CLI assistant bench on mmbench-tiny.
#
# Like bench_universal.sh, but operates directly on the 4-file mmbench-tiny
# dataset (image / video / PDF / audio) — no synthetic curation step. Differs
# in three ways from the multimodal bench:
#
#   1. Random task sampling. There is no fast/full mode — the script picks
#      `--tasks N` (default 5) tasks uniformly at random from a pool of
#      tiny-compatible tasks. Effective count is
#          min(available, max(5, --tasks)).
#   2. Six assistants supported: claude, codex, gemini, openclaw, opencode,
#      qwencode. Unreachable ones are dropped during preflight.
#   3. Ad-hoc profile override. Pass --base-url / --model / --api-key to
#      benchmark against a one-shot profile that is created, activated, used
#      for the run, then torn down (with the previous active profile
#      restored). Without these flags the active profile is used as-is.
#
# Results are emitted as both run_<ts>.json (canonical) and run_<ts>.yaml
# under benchmarks/bench_universal/run_results/. The visualizer accepts
# either.
#
# Usage:
#   ./benchmarks/bench_universal/bench_universal_tiny.sh
#   ./benchmarks/bench_universal/bench_universal_tiny.sh --tasks 10
#   ./benchmarks/bench_universal/bench_universal_tiny.sh --assistant claude,codex
#   ./benchmarks/bench_universal/bench_universal_tiny.sh --timeout 60
#   ./benchmarks/bench_universal/bench_universal_tiny.sh \
#       --base-url https://openrouter.ai/api/v1 --model qwen3-vl:8b --api-key sk-...
#   BENCH_RUNS=10 ./benchmarks/bench_universal/bench_universal_tiny.sh
set -euo pipefail

# ---------------------------------------------------------------------------
# Static config
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$(cd "${SCRIPT_DIR}/../data" && pwd 2>/dev/null || echo "${SCRIPT_DIR}/../data")"
BENCH_DIR="${DATA_DIR}/mmbench-tiny"
RESULTS_DIR="${SCRIPT_DIR}/run_results"
TINY_URL="https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-tiny.tar.gz"

SUPPORTED_ASSISTANTS="claude codex gemini openclaw opencode qwencode"
RUNS="${BENCH_RUNS:-1}"
TIMEOUT_SEC="${BENCH_TIMEOUT:-120}"

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------
SELECTED_ASSISTANT=""
TASK_COUNT=""
CUSTOM_BASE_URL=""
CUSTOM_MODEL=""
CUSTOM_API_KEY=""

usage() {
  sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --assistant) SELECTED_ASSISTANT="${2:?--assistant requires a value}"; shift 2 ;;
    --tasks)     TASK_COUNT="${2:?--tasks requires a number}"; shift 2 ;;
    --timeout)   TIMEOUT_SEC="${2:?--timeout requires seconds}"; shift 2 ;;
    --base-url)  CUSTOM_BASE_URL="${2:?--base-url requires a URL}"; shift 2 ;;
    --model)     CUSTOM_MODEL="${2:?--model requires a model name}"; shift 2 ;;
    --api-key)   CUSTOM_API_KEY="${2:?--api-key requires a key}"; shift 2 ;;
    -h|--help)   usage 0 ;;
    *)           echo "Unknown flag: $1"; usage 1 ;;
  esac
done

if ! [[ "${TIMEOUT_SEC}" =~ ^[0-9]+$ ]] || [ "${TIMEOUT_SEC}" -lt 1 ]; then
  echo "Error: --timeout must be a positive integer (seconds), got '${TIMEOUT_SEC}'"
  exit 1
fi
if [ -n "${TASK_COUNT}" ] && ! [[ "${TASK_COUNT}" =~ ^[0-9]+$ ]]; then
  echo "Error: --tasks must be a non-negative integer, got '${TASK_COUNT}'"
  exit 1
fi

if [ -n "${SELECTED_ASSISTANT}" ]; then
  IFS=',' read -r -a _SEL_ARR <<< "${SELECTED_ASSISTANT}"
  for _name in "${_SEL_ARR[@]}"; do
    case " ${SUPPORTED_ASSISTANTS} " in
      *" ${_name} "*) ;;
      *) echo "Error: --assistant '${_name}' not supported (expected: ${SUPPORTED_ASSISTANTS// /, })"; exit 1 ;;
    esac
  done
  unset _SEL_ARR _name
fi

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
if ! command -v hyperfine &>/dev/null; then
  echo "Error: hyperfine not found. Install with: brew install hyperfine"
  exit 1
fi
if ! command -v mm &>/dev/null; then
  echo "Error: mm not found. Install with: uv pip install mm-ctx"
  exit 1
fi
if ! command -v jq &>/dev/null; then
  echo "Error: jq not found. Install with: brew install jq"
  exit 1
fi
if command -v timeout &>/dev/null; then
  TIMEOUT_CMD="timeout"
elif command -v gtimeout &>/dev/null; then
  TIMEOUT_CMD="gtimeout"
else
  echo "Error: timeout (or gtimeout) not found. On macOS: brew install coreutils"
  exit 1
fi

# Random index sampler. Prefers shuf, falls back to gshuf (coreutils on
# macOS), then awk Fisher–Yates if neither is installed.
sample_indices() {
  local count="$1" total="$2"
  if command -v shuf &>/dev/null; then
    shuf -i 0-$((total - 1)) -n "${count}"
  elif command -v gshuf &>/dev/null; then
    gshuf -i 0-$((total - 1)) -n "${count}"
  else
    awk -v n="${total}" -v k="${count}" -v seed="$$$(date +%s)" 'BEGIN {
      srand(seed);
      for (i=0; i<n; i++) a[i]=i;
      for (i=n-1; i>0; i--) { j=int(rand()*(i+1)); t=a[i]; a[i]=a[j]; a[j]=t }
      for (i=0; i<k; i++) print a[i];
    }'
  fi
}

# YAML→JSON converter. The script writes YAML during the run (heredoc-friendly),
# then derives the canonical JSON in one pass at the end. uv-managed pyyaml is
# already a project dep; fall back to bare python3 if uv is unavailable.
yaml_to_json() {
  local yaml="$1" json="$2"
  if command -v uv &>/dev/null; then
    uv run --quiet python - "${yaml}" "${json}" <<'PY'
import json, sys
import yaml
with open(sys.argv[1]) as f:
    data = yaml.safe_load(f)
with open(sys.argv[2], "w") as f:
    json.dump(data, f, indent=2, default=str)
PY
  else
    python3 - "${yaml}" "${json}" <<'PY'
import json, sys
import yaml
with open(sys.argv[1]) as f:
    data = yaml.safe_load(f)
with open(sys.argv[2], "w") as f:
    json.dump(data, f, indent=2, default=str)
PY
  fi
}

# ---------------------------------------------------------------------------
# Profile management — capture active, optionally swap in a temporary one,
# always restore on exit.
# ---------------------------------------------------------------------------
PREVIOUS_PROFILE=""
TMP_PROFILE_NAME=""
PROFILE_NAME=""
PROFILE_BASE_URL=""
PROFILE_MODEL=""

restore_profile() {
  # Idempotent: safe to call multiple times via trap.
  if [ -n "${TMP_PROFILE_NAME}" ]; then
    if [ -n "${PREVIOUS_PROFILE}" ] && [ "${PREVIOUS_PROFILE}" != "${TMP_PROFILE_NAME}" ]; then
      mm profile use "${PREVIOUS_PROFILE}" >/dev/null 2>&1 || true
    fi
    mm profile remove "${TMP_PROFILE_NAME}" >/dev/null 2>&1 || true
    TMP_PROFILE_NAME=""
  fi
}

apply_custom_profile() {
  local has_any=0
  [ -n "${CUSTOM_BASE_URL}" ] && has_any=1
  [ -n "${CUSTOM_MODEL}" ] && has_any=1
  [ -n "${CUSTOM_API_KEY}" ] && has_any=1
  [ "${has_any}" -eq 0 ] && return 0

  if [ -z "${CUSTOM_BASE_URL}" ] || [ -z "${CUSTOM_MODEL}" ]; then
    echo "Error: --base-url and --model are both required when overriding the profile (--api-key is optional)"
    exit 1
  fi

  PREVIOUS_PROFILE="$(mm profile list --format json 2>/dev/null | jq -r '.active // ""')"
  TMP_PROFILE_NAME="mmbench-tmp-$(date +%s)-$$"
  trap restore_profile EXIT INT TERM

  local add_args=( --base-url "${CUSTOM_BASE_URL}" --model "${CUSTOM_MODEL}" )
  [ -n "${CUSTOM_API_KEY}" ] && add_args+=( --api-key "${CUSTOM_API_KEY}" )
  mm profile add "${TMP_PROFILE_NAME}" "${add_args[@]}" >/dev/null
  mm profile use "${TMP_PROFILE_NAME}" >/dev/null
  echo "Using temporary profile ${TMP_PROFILE_NAME} (will be removed on exit)"
}

capture_profile() {
  local json
  json="$(mm profile list --format json 2>/dev/null || echo '{}')"
  PROFILE_NAME="$(echo "${json}" | jq -r '.active // ""')"
  if [ -n "${PROFILE_NAME}" ]; then
    PROFILE_BASE_URL="$(echo "${json}" | jq -r --arg n "${PROFILE_NAME}" '.profiles[$n].base_url // ""')"
    PROFILE_MODEL="$(echo "${json}" | jq -r --arg n "${PROFILE_NAME}" '.profiles[$n].model // ""')"
  fi
}

# ---------------------------------------------------------------------------
# Assistant probing — six assistants supported. New ones (openclaw, opencode,
# qwencode) follow Claude's `-p PROMPT` convention until proven otherwise; the
# probe will mark anything unreachable as skipped.
# ---------------------------------------------------------------------------
check_assistant() {
  local name="$1"
  case "${name}" in
    claude)    claude    -p 'hi' </dev/null >/dev/null 2>&1 ;;
    codex)     codex     -q 'hi' </dev/null >/dev/null 2>&1 ;;
    gemini)    gemini    -p 'hi' </dev/null >/dev/null 2>&1 ;;
    openclaw)  openclaw  -p 'hi' </dev/null >/dev/null 2>&1 ;;
    opencode)  opencode  -p 'hi' </dev/null >/dev/null 2>&1 ;;
    qwencode)  qwencode  -p 'hi' </dev/null >/dev/null 2>&1 ;;
    *)         return 1 ;;
  esac
}

declare -a ASSISTANTS=()
probe_assistants() {
  for cmd in ${SUPPORTED_ASSISTANTS}; do
    if [ -n "${SELECTED_ASSISTANT}" ]; then
      case ",${SELECTED_ASSISTANT}," in
        *",${cmd},"*) ;;
        *) continue ;;
      esac
    fi
    if ! command -v "${cmd}" &>/dev/null; then
      [ -n "${SELECTED_ASSISTANT}" ] && echo "  ${cmd}: not installed (skipping)"
      continue
    fi
    printf "  %s: probing..." "${cmd}"
    if check_assistant "${cmd}"; then
      printf " ok\n"
      ASSISTANTS+=("${cmd}")
    else
      printf " unreachable (skipping)\n"
    fi
  done

  if [ ${#ASSISTANTS[@]} -eq 0 ]; then
    echo "Error: no reachable assistants. Install and authenticate at least one of: ${SUPPORTED_ASSISTANTS}"
    exit 1
  fi
  echo "Detected assistants: ${ASSISTANTS[*]}"
}

# Build the shell command to call an assistant on a prompt (with optional
# stdin context). Mirrors bench_universal.sh exactly so the visualizer YAML
# schema stays compatible.
assistant_cmd() {
  local name="$1" prompt="$2" context="${3:-}"
  local tcap="${TIMEOUT_CMD} ${TIMEOUT_SEC}s"
  case "${name}" in
    claude)   [ -n "${context}" ] && echo "echo '${context}' | ${tcap} claude -p '${prompt}'"   || echo "${tcap} claude -p '${prompt}'" ;;
    codex)    [ -n "${context}" ] && echo "echo '${context}' | ${tcap} codex -q '${prompt}'"    || echo "${tcap} codex -q '${prompt}'" ;;
    gemini)   [ -n "${context}" ] && echo "echo '${context}' | ${tcap} gemini -p '${prompt}'"   || echo "${tcap} gemini -p '${prompt}'" ;;
    openclaw) [ -n "${context}" ] && echo "echo '${context}' | ${tcap} openclaw -p '${prompt}'" || echo "${tcap} openclaw -p '${prompt}'" ;;
    opencode) [ -n "${context}" ] && echo "echo '${context}' | ${tcap} opencode -p '${prompt}'" || echo "${tcap} opencode -p '${prompt}'" ;;
    qwencode) [ -n "${context}" ] && echo "echo '${context}' | ${tcap} qwencode -p '${prompt}'" || echo "${tcap} qwencode -p '${prompt}'" ;;
  esac
}

assistant_pipe_cmd() {
  local name="$1" mm_cmd="$2" prompt="$3"
  local tcap="${TIMEOUT_CMD} ${TIMEOUT_SEC}s"
  case "${name}" in
    claude)   echo "${mm_cmd} | ${tcap} claude -p '${prompt}'" ;;
    codex)    echo "${mm_cmd} | ${tcap} codex -q '${prompt}'" ;;
    gemini)   echo "${mm_cmd} | ${tcap} gemini -p '${prompt}'" ;;
    openclaw) echo "${mm_cmd} | ${tcap} openclaw -p '${prompt}'" ;;
    opencode) echo "${mm_cmd} | ${tcap} opencode -p '${prompt}'" ;;
    qwencode) echo "${mm_cmd} | ${tcap} qwencode -p '${prompt}'" ;;
  esac
}

# ---------------------------------------------------------------------------
# Dataset: download mmbench-tiny if missing
# ---------------------------------------------------------------------------
setup_data() {
  if [ -d "${BENCH_DIR}" ] && [ -f "${BENCH_DIR}/1-vqa-car.jpg" ]; then
    echo "Tiny dataset ready: ${BENCH_DIR}"
    return
  fi
  echo "Downloading mmbench-tiny (~43MB)..."
  mkdir -p "${DATA_DIR}"
  curl -sL "${TINY_URL}" | tar xzf - -C "${DATA_DIR}"
  if [ ! -f "${BENCH_DIR}/1-vqa-car.jpg" ]; then
    echo "Error: download did not produce ${BENCH_DIR}/1-vqa-car.jpg"
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Task pool — 17 tiny-compatible tasks. These mirror the original 20-task
# multimodal pool, retargeted at the four files in mmbench-tiny:
#   IMG = 1-vqa-car.jpg
#   VID = bakery.mp4
#   PDF = BillDownload-8pg.pdf
#   AUD = how_to_build_an_mvp.mp3
# Tasks that referenced subdirs (docs/, media/) in the original pool are
# omitted, since tiny is a flat directory.
# ---------------------------------------------------------------------------
declare -a TASK_NAMES=()
declare -a TASK_PROMPTS=()
declare -a TASK_MM_CMDS=()
declare -a TASK_TARGET_FILES=()

add_task() {
  TASK_NAMES+=("$1")
  TASK_PROMPTS+=("$2")
  TASK_MM_CMDS+=("$3")
  TASK_TARGET_FILES+=("${4:-}")
}

register_tasks() {
  local IMG="${BENCH_DIR}/1-vqa-car.jpg"
  local VID="${BENCH_DIR}/bakery.mp4"
  local PDF="${BENCH_DIR}/BillDownload-8pg.pdf"
  local AUD="${BENCH_DIR}/how_to_build_an_mvp.mp3"

  add_task "directory_survey" \
    "List every file in this directory tree with its type, size, and path. Group by file type." \
    "mm find ${BENCH_DIR} --format json"

  add_task "pdf_extraction" \
    "Extract the text from this PDF and provide a structured summary of its contents." \
    "mm cat '${PDF}' --mode fast" \
    "${PDF}"

  add_task "image_metadata" \
    "Describe what is shown in this image. Include dimensions, format, and any EXIF metadata." \
    "mm cat '${IMG}' --mode fast --format json" \
    "${IMG}"

  add_task "video_metadata" \
    "Extract metadata from this video: resolution, duration, codec, and file size." \
    "mm cat '${VID}' --mode fast --format json" \
    "${VID}"

  add_task "audio_metadata" \
    "Extract metadata from this audio file: duration, codec, sample rate, and file size." \
    "mm cat '${AUD}' --mode fast --format json" \
    "${AUD}"

  add_task "token_cost_estimate" \
    "Analyze this directory: how many files per type, total size per type, and which are the largest? Estimate total LLM token cost." \
    "mm wc ${BENCH_DIR} --by-kind --format json"

  add_task "recent_files" \
    "List all files sorted by modification time (most recent first). Show name, type, size, and date." \
    "mm sql \"SELECT name, kind, size, modified FROM files ORDER BY modified DESC\" --dir ${BENCH_DIR} --format json"

  add_task "batch_metadata" \
    "Extract structured metadata for every file in this directory: name, type, size, dimensions (if image/video), duration (if audio/video), and content hash." \
    "mm find ${BENCH_DIR} --format json"

  add_task "evidence_package" \
    "Create an inventory of this directory as an evidence package: list every file with its hash, size, type, and modification date. Flag any files that are unusually large." \
    "mm find ${BENCH_DIR} --columns name,kind,size,modified --format json"

  add_task "document_search" \
    "Search all document files for mentions of dollar amounts and list where they appear." \
    "mm grep '\\\$[0-9]' ${BENCH_DIR} --kind document --format json"

  add_task "document_token_cost" \
    "How many tokens would it cost to ingest all documents in this directory into an LLM? Count files and estimate tokens." \
    "mm wc ${BENCH_DIR} --kind document --format json"

  add_task "document_format_audit" \
    "What document formats exist in this directory? Show extension, count, and total size for each format." \
    "mm sql \"SELECT ext, COUNT(*) as n, ROUND(SUM(size)/1e6,1) as mb FROM files WHERE kind='document' GROUP BY ext ORDER BY n DESC\" --dir ${BENCH_DIR} --format json"

  add_task "hires_images" \
    "Find all images in this directory with width >= 1000 pixels. Show name, dimensions, and size." \
    "mm sql \"SELECT name, width, height, size FROM files WHERE kind='image' AND width >= 1000 ORDER BY width DESC\" --dir ${BENCH_DIR} --format json"

  add_task "image_format_audit" \
    "What image formats are used in this directory? Show format, count, and total size." \
    "mm sql \"SELECT ext, COUNT(*) as n, ROUND(SUM(size)/1e6,1) as mb FROM files WHERE kind='image' GROUP BY ext ORDER BY mb DESC\" --dir ${BENCH_DIR} --format json"

  add_task "image_token_cost" \
    "How many tokens would it cost to process all images in this directory with a vision LLM? List each image with its dimensions and estimated tokens." \
    "mm wc ${BENCH_DIR} --kind image --format json"

  add_task "video_resolution_check" \
    "List all video files and their resolution. Which are HD (>=720p) and which are SD?" \
    "mm sql \"SELECT name, width, height, size FROM files WHERE kind='video'\" --dir ${BENCH_DIR} --format json"

  add_task "tree_overview" \
    "Generate a directory tree of this folder showing structure, file types, and sizes at each level." \
    "mm find ${BENCH_DIR} --tree --depth 3 --format json"

  add_task "project_token_budget" \
    "Does the content of this directory fit in a 200K token LLM context window? Show total tokens, breakdown by file type, and list files that are too large to include." \
    "mm wc ${BENCH_DIR} --by-kind --format json"
}

resolve_task_count() {
  local total="${#TASK_NAMES[@]}"
  if [ "${total}" -lt 1 ]; then
    echo "Error: register_tasks produced 0 tasks"
    exit 1
  fi
  local desired="${TASK_COUNT:-5}"
  local floor=5
  # max(5, min(available, specified)), then capped at available so the formula
  # is well-defined even when the pool itself has < 5 tasks.
  local clamped=$(( desired < total ? desired : total ))
  local picked=$(( clamped > floor ? clamped : floor ))
  if [ "${picked}" -gt "${total}" ]; then
    picked="${total}"
  fi
  MAX_TASKS="${picked}"
  TOTAL_TASKS="${total}"
}

# ---------------------------------------------------------------------------
# Single-task hyperfine runner. Identical YAML schema to bench_universal.sh
# so the visualizer continues to work unchanged.
# ---------------------------------------------------------------------------
run_task() {
  local task_name="$1" prompt="$2" mm_cmd="$3" result_file="$4" target_file="${5:-}"

  local budget_note=" (Time budget: ${TIMEOUT_SEC}s — be concise and do not over-explore.)"
  local prompt_with_budget="${prompt}${budget_note}"

  cat >> "${result_file}" <<EOF

  - name: "${task_name}"
    prompt: "$(echo "${prompt}" | sed 's/"/\\"/g')"
    mm_cmd: "$(echo "${mm_cmd}" | sed 's/"/\\"/g')"
    timeout_s: ${TIMEOUT_SEC}
    results:
EOF

  for asst in "${ASSISTANTS[@]}"; do
    echo "  [${asst}] ${task_name}"

    local with_cmd
    with_cmd="$(assistant_pipe_cmd "${asst}" "${mm_cmd}" "${prompt_with_budget}")"
    local with_json="${RESULTS_DIR}/.tmp_with_${asst}_${task_name}.json"
    echo "    with mm: ${with_cmd}"
    hyperfine --ignore-failure --warmup 1 --min-runs "${RUNS}" --export-json "${with_json}" \
      --command-name "${asst}+mm" \
      "${with_cmd}" 2>&1 | tail -1 || true

    local without_prompt
    if [ -n "${target_file}" ]; then
      without_prompt="Given the file at ${target_file}: ${prompt_with_budget}"
    else
      without_prompt="Given the directory at ${BENCH_DIR}: ${prompt_with_budget}"
    fi
    local without_cmd
    without_cmd="$(assistant_cmd "${asst}" "${without_prompt}")"
    local without_json="${RESULTS_DIR}/.tmp_without_${asst}_${task_name}.json"
    echo "    without mm: ${without_cmd}"
    hyperfine --ignore-failure --warmup 1 --min-runs "${RUNS}" --export-json "${without_json}" \
      --command-name "${asst}" \
      "${without_cmd}" 2>&1 | tail -1 || true

    local with_mean with_stddev without_mean without_stddev speedup
    if [ -f "${with_json}" ]; then
      with_mean="$(jq -r '.results[0].mean // "null"' "${with_json}")"
      with_stddev="$(jq -r '.results[0].stddev // "null"' "${with_json}")"
    else
      with_mean="null"; with_stddev="null"
    fi
    if [ -f "${without_json}" ]; then
      without_mean="$(jq -r '.results[0].mean // "null"' "${without_json}")"
      without_stddev="$(jq -r '.results[0].stddev // "null"' "${without_json}")"
    else
      without_mean="null"; without_stddev="null"
    fi

    if [ "${with_mean}" != "null" ] && [ "${without_mean}" != "null" ] \
        && [ "$(echo "${with_mean} > 0" | bc -l 2>/dev/null || echo 0)" = "1" ]; then
      speedup="$(printf '%.2fx' "$(echo "scale=4; ${without_mean} / ${with_mean}" | bc -l)")"
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
        speedup: "${speedup}"
EOF
    rm -f "${with_json}" "${without_json}"
  done
}

# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
run_benchmarks() {
  local ts
  ts="$(date +%Y%m%d_%H%M%S)"
  mkdir -p "${RESULTS_DIR}"
  local base="${RESULTS_DIR}/run_${ts}"
  local yaml_file="${base}.yaml"
  local json_file="${base}.json"

  # Pick the random sample once, in display order — the YAML records both
  # the count and the names so a reader can reproduce the run.
  local -a sampled_indices=()
  while IFS= read -r idx; do
    sampled_indices+=("${idx}")
  done < <(sample_indices "${MAX_TASKS}" "${TOTAL_TASKS}")

  local sampled_names=""
  for i in "${sampled_indices[@]}"; do
    sampled_names+="\"${TASK_NAMES[$i]}\","
  done
  sampled_names="${sampled_names%,}"

  echo ""
  echo "=== Universal CLI Assistant Benchmark — Tiny ==="
  echo "Data: ${BENCH_DIR}"
  echo "Tasks: ${MAX_TASKS} of ${TOTAL_TASKS} (random sample)"
  echo "Assistants: ${ASSISTANTS[*]}"
  echo "Runs per command: ${RUNS}"
  echo "Timeout per attempt: ${TIMEOUT_SEC}s"
  echo "Profile: ${PROFILE_NAME:-<none>} (${PROFILE_BASE_URL:-n/a} / ${PROFILE_MODEL:-n/a})"
  echo "Results: ${json_file} (+ ${yaml_file})"
  echo ""

  cat > "${yaml_file}" <<EOF
# Universal CLI Assistant Benchmark — Tiny
# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
# Assistants: ${ASSISTANTS[*]}
# Tasks: ${MAX_TASKS}/${TOTAL_TASKS} (random sample)
# Runs: ${RUNS}
# Data: ${BENCH_DIR}
---
meta:
  timestamp: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  bench_label: "Tiny"
  assistants: [$(printf '"%s",' "${ASSISTANTS[@]}" | sed 's/,$//')]
  mode: "random"
  tasks_run: ${MAX_TASKS}
  tasks_total: ${TOTAL_TASKS}
  sampled_tasks: [${sampled_names}]
  runs: ${RUNS}
  timeout_s: ${TIMEOUT_SEC}
  profile_name: "${PROFILE_NAME}"
  profile_base_url: "${PROFILE_BASE_URL}"
  profile_model: "${PROFILE_MODEL}"
  data_dir: "${BENCH_DIR}"
  file_count: $(find "${BENCH_DIR}" -type f ! -name '.DS_Store' | wc -l | tr -d ' ')
  total_size_bytes: $(find "${BENCH_DIR}" -type f ! -name '.DS_Store' -exec stat -f '%z' {} + 2>/dev/null | awk '{s+=$1}END{print s+0}' || find "${BENCH_DIR}" -type f ! -name '.DS_Store' -exec stat -c '%s' {} + 2>/dev/null | awk '{s+=$1}END{print s+0}')

tasks:
EOF

  local pos=0
  for i in "${sampled_indices[@]}"; do
    pos=$((pos + 1))
    echo ""
    echo "--- Task ${pos}/${MAX_TASKS}: ${TASK_NAMES[$i]} ---"
    run_task "${TASK_NAMES[$i]}" "${TASK_PROMPTS[$i]}" "${TASK_MM_CMDS[$i]}" \
             "${yaml_file}" "${TASK_TARGET_FILES[$i]}"
  done

  yaml_to_json "${yaml_file}" "${json_file}"

  echo ""
  echo "=== Results ==="
  echo "  JSON: ${json_file}"
  echo "  YAML: ${yaml_file}"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
apply_custom_profile
capture_profile
echo "Probing assistants..."
probe_assistants
setup_data
register_tasks
resolve_task_count
run_benchmarks
