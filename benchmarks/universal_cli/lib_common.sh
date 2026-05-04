#!/usr/bin/env bash
# lib_common.sh — shared plumbing for universal CLI assistant benchmarks.
#
# Sourced by per-media bench scripts (e.g. bench_cli_universal_assistant_image.sh).
# Provides argument parsing, preflight, assistant probing, hyperfine wrappers,
# and the YAML-emitting run loop. Each caller supplies:
#
#   - BENCH_DIR              path to the directory under benchmark
#   - BENCH_LABEL            human label (e.g. "Image", "Video") used in headers
#   - setup_data()           function that prepares BENCH_DIR (idempotent)
#   - register_tasks()       function that populates TASK_* arrays via add_task
#   - FAST_TASKS             integer; number of tasks for --mode fast (default 5)
#
# Optional caller-defined globals (defaults supplied here):
#   - SUPPORTED_ASSISTANTS   space-separated list (default: "claude codex gemini")
#   - RESULTS_SUBDIR         results subdirectory name under universal_cli (default: run_results)
#
# After sourcing, call:    bench_main "$@"
#
# This file deliberately mirrors bench_cli_universal_assistant.sh so the YAML
# schema stays compatible with visualize_universal.py.

set -euo pipefail

LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCH_ROOT="$(cd "${LIB_DIR}/.." && pwd)"

: "${SUPPORTED_ASSISTANTS:=claude codex gemini}"
: "${RESULTS_SUBDIR:=run_results}"
: "${FAST_TASKS:=5}"
RESULTS_DIR="${LIB_DIR}/${RESULTS_SUBDIR}"

RUNS="${BENCH_RUNS:-3}"
TIMEOUT_SEC="${BENCH_TIMEOUT:-120}"

SELECTED_ASSISTANT=""
MODE="fast"
TASK_COUNT=""

declare -a TASK_NAMES=()
declare -a TASK_PROMPTS=()
declare -a TASK_MM_CMDS=()
declare -a TASK_TARGET_FILES=()
declare -a ASSISTANTS=()

PROFILE_NAME=""
PROFILE_BASE_URL=""
PROFILE_MODEL=""
TIMEOUT_CMD=""

add_task() {
  TASK_NAMES+=("$1")
  TASK_PROMPTS+=("$2")
  TASK_MM_CMDS+=("$3")
  TASK_TARGET_FILES+=("${4:-}")
}

parse_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --assistant) SELECTED_ASSISTANT="${2:?--assistant requires a value (claude, codex, gemini; comma-separated for multiple)}"; shift 2 ;;
      --mode)      MODE="${2:?--mode requires a value (fast, full)}"; shift 2 ;;
      --tasks)     TASK_COUNT="${2:?--tasks requires a number}"; shift 2 ;;
      --timeout)   TIMEOUT_SEC="${2:?--timeout requires seconds}"; shift 2 ;;
      *)           echo "Unknown flag: $1"; exit 1 ;;
    esac
  done

  if ! [[ "${TIMEOUT_SEC}" =~ ^[0-9]+$ ]] || [ "${TIMEOUT_SEC}" -lt 1 ]; then
    echo "Error: --timeout must be a positive integer (seconds), got '${TIMEOUT_SEC}'"
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
}

# Resolves MAX_TASKS from MODE / TASK_COUNT after register_tasks has populated
# TASK_NAMES — so callers can size FAST_TASKS independently from the registry.
resolve_task_count() {
  local total="${#TASK_NAMES[@]}"
  if [ "${total}" -lt 1 ]; then
    echo "Error: register_tasks produced 0 tasks"
    exit 1
  fi
  if [ -n "${TASK_COUNT}" ]; then
    MAX_TASKS="${TASK_COUNT}"
  elif [ "${MODE}" = "fast" ]; then
    MAX_TASKS="${FAST_TASKS}"
  elif [ "${MODE}" = "full" ]; then
    MAX_TASKS="${total}"
  else
    echo "Error: --mode must be 'fast' or 'full', got '${MODE}'"
    exit 1
  fi
  if [ "${MAX_TASKS}" -lt 1 ] || [ "${MAX_TASKS}" -gt "${total}" ]; then
    echo "Error: --tasks must be between 1 and ${total}, got ${MAX_TASKS}"
    exit 1
  fi
  TOTAL_TASKS="${total}"
}

preflight() {
  if ! command -v hyperfine &>/dev/null; then
    echo "Error: hyperfine not found. First install Hyperfine, e.g., on Darwin with: brew install hyperfine"
    exit 1
  fi
  if ! command -v mm &>/dev/null; then
    echo "Error: mm not found. Install with: uv pip install mm-ctx"
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

check_assistant() {
  local name="$1"
  case "${name}" in
    claude) claude -p 'hi' </dev/null >/dev/null 2>&1 ;;
    codex)  codex -q 'hi' </dev/null >/dev/null 2>&1 ;;
    gemini) gemini -p 'hi' </dev/null >/dev/null 2>&1 ;;
    *)      return 1 ;;
  esac
}

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

assistant_cmd() {
  local name="$1"
  local prompt="$2"
  local context="${3:-}"
  local tcap="${TIMEOUT_CMD} ${TIMEOUT_SEC}s"
  case "${name}" in
    claude) [ -n "${context}" ] && echo "echo '${context}' | ${tcap} claude -p '${prompt}'" || echo "${tcap} claude -p '${prompt}'" ;;
    codex)  [ -n "${context}" ] && echo "echo '${context}' | ${tcap} codex -q '${prompt}'"  || echo "${tcap} codex -q '${prompt}'" ;;
    gemini) [ -n "${context}" ] && echo "echo '${context}' | ${tcap} gemini -p '${prompt}'" || echo "${tcap} gemini -p '${prompt}'" ;;
  esac
}

assistant_pipe_cmd() {
  local name="$1"
  local mm_cmd="$2"
  local prompt="$3"
  local tcap="${TIMEOUT_CMD} ${TIMEOUT_SEC}s"
  case "${name}" in
    claude) echo "${mm_cmd} | ${tcap} claude -p '${prompt}'" ;;
    codex)  echo "${mm_cmd} | ${tcap} codex -q '${prompt}'" ;;
    gemini) echo "${mm_cmd} | ${tcap} gemini -p '${prompt}'" ;;
  esac
}

# Files counted/sized for the YAML header — shared by image/video/audio runs.
_count_files() {
  find "${BENCH_DIR}" -type f ! -name '.ready' ! -name '.DS_Store' ! -name '.source.parquet' | wc -l | tr -d ' '
}

_sum_bytes() {
  find "${BENCH_DIR}" -type f ! -name '.ready' ! -name '.DS_Store' ! -name '.source.parquet' \
    -exec stat -f '%z' {} + 2>/dev/null \
    | awk '{s+=$1}END{print s+0}' \
    || find "${BENCH_DIR}" -type f ! -name '.ready' ! -name '.DS_Store' ! -name '.source.parquet' \
        -exec stat -c '%s' {} + 2>/dev/null | awk '{s+=$1}END{print s+0}'
}

run_task() {
  local task_name="$1"
  local prompt="$2"
  local mm_cmd="$3"
  local result_file="$4"
  local target_file="${5:-}"

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

run_benchmarks() {
  local ts
  ts="$(date +%Y%m%d_%H%M%S)"
  mkdir -p "${RESULTS_DIR}"
  local result_file="${RESULTS_DIR}/run_${ts}.yaml"

  local mode_label
  if [ -n "${TASK_COUNT}" ]; then
    mode_label="custom (${MAX_TASKS} tasks)"
  else
    mode_label="${MODE} (${MAX_TASKS} tasks)"
  fi

  echo ""
  echo "=== Universal CLI Assistant Benchmark — ${BENCH_LABEL} ==="
  echo "Mode: ${mode_label}"
  echo "Data: ${BENCH_DIR}"
  echo "Assistants: ${ASSISTANTS[*]}"
  echo "Runs per command: ${RUNS}"
  echo "Timeout per attempt: ${TIMEOUT_SEC}s"
  echo "Profile: ${PROFILE_NAME:-<none>} (${PROFILE_BASE_URL:-n/a} / ${PROFILE_MODEL:-n/a})"
  echo "Results: ${result_file}"
  echo ""

  cat > "${result_file}" <<EOF
# Universal CLI Assistant Benchmark — ${BENCH_LABEL}
# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
# Assistants: ${ASSISTANTS[*]}
# Mode: ${mode_label}
# Runs: ${RUNS}
# Data: ${BENCH_DIR}
---
meta:
  timestamp: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  bench_label: "${BENCH_LABEL}"
  assistants: [$(printf '"%s",' "${ASSISTANTS[@]}" | sed 's/,$//')]
  mode: "${MODE}"
  tasks_run: ${MAX_TASKS}
  tasks_total: ${TOTAL_TASKS}
  runs: ${RUNS}
  timeout_s: ${TIMEOUT_SEC}
  profile_name: "${PROFILE_NAME}"
  profile_base_url: "${PROFILE_BASE_URL}"
  profile_model: "${PROFILE_MODEL}"
  data_dir: "${BENCH_DIR}"
  file_count: $(_count_files)
  total_size_bytes: $(_sum_bytes)

tasks:
EOF

  local ran=0
  for i in $(seq 0 $((${#TASK_NAMES[@]} - 1))); do
    [ "${ran}" -ge "${MAX_TASKS}" ] && break
    ran=$((ran + 1))
    echo ""
    echo "--- Task ${ran}/${MAX_TASKS}: ${TASK_NAMES[$i]} ---"
    run_task "${TASK_NAMES[$i]}" "${TASK_PROMPTS[$i]}" "${TASK_MM_CMDS[$i]}" \
             "${result_file}" "${TASK_TARGET_FILES[$i]}"
  done

  echo ""
  echo "=== Results written to ${result_file} ==="
}

bench_main() {
  parse_args "$@"
  preflight
  capture_profile
  probe_assistants
  setup_data
  register_tasks
  resolve_task_count
  run_benchmarks
}
