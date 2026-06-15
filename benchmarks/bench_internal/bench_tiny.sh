#!/usr/bin/env bash
# mm CLI benchmarks (tiny dataset) — 4 files, ~42MB
# Usage: ./benchmarks/bench_internal/bench_tiny.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$(cd "${SCRIPT_DIR}/../data" && pwd 2>/dev/null || echo "${SCRIPT_DIR}/../data")"
TINY_URL="https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-tiny.tar.gz"

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------
if ! command -v hyperfine &>/dev/null; then
  echo "Error: hyperfine not found. Install with: brew install hyperfine"
  exit 1
fi

# Portable stat format: macOS uses -f, Linux uses -c
if stat -f '%z %N' /dev/null &>/dev/null; then
  STAT_FMT="-f '%z %N'"
else
  STAT_FMT="-c '%s %n'"
fi

# ---------------------------------------------------------------------------
# Download benchmark data if missing
# ---------------------------------------------------------------------------
if [ ! -d "${DATA_DIR}/mmbench-tiny" ]; then
  echo "Downloading mmbench-tiny (~43MB)..."
  mkdir -p "${DATA_DIR}"
  curl -sL "${TINY_URL}" | tar xzf - -C "${DATA_DIR}"
  echo "  → ${DATA_DIR}/mmbench-tiny"
fi

DIR="${DATA_DIR}/mmbench-tiny"
PDF="${DIR}/BillDownload-8pg.pdf"
IMG="${DIR}/1-vqa-car.jpg"
VID="${DIR}/bakery.mp4"
AUD="${DIR}/how_to_build_an_mvp.mp3"

FILE_COUNT="$(find "${DIR}" -type f ! -name '.DS_Store' | wc -l | tr -d ' ')"
echo "=== mm CLI Benchmarks (tiny) ==="
echo "Data: ${DIR} (${FILE_COUNT} files, $(du -sh "${DIR}" | awk '{print $1}'))"
echo ""

# ===========================================================================
# L0: find
# ===========================================================================
echo "--- L0: mm find ---"
hyperfine --warmup 2 --min-runs 10 \
  "mm find ${DIR}" \
  "mm find ${DIR} --tree --depth 1" \
  "mm find ${DIR} --format json"

echo ""
echo "--- L0: mm find vs find ---"
hyperfine --warmup 2 --min-runs 10 \
  --command-name "mm find (tsv)" \
    "mm find ${DIR} --format tsv" \
  --command-name "mm find (json)" \
    "mm find ${DIR} --format json" \
  --command-name "find" \
    "find ${DIR} -type f" \
  --command-name "find + stat (size)" \
    "find ${DIR} -type f -exec stat ${STAT_FMT} {} +" \
  --command-name "find + file (mime)" \
    "find ${DIR} -type f -exec file --brief --mime-type {} +"

# ===========================================================================
# L0: wc
# ===========================================================================
echo ""
echo "--- L0: mm wc vs wc/du ---"
hyperfine --warmup 2 --min-runs 10 \
  --command-name "mm wc" \
    "mm wc ${DIR}" \
  --command-name "mm wc --by-kind" \
    "mm wc ${DIR} --by-kind" \
  --command-name "wc -l (line count)" \
    "find ${DIR} -type f -exec wc -l {} +" \
  --command-name "du -sh" \
    "du -sh ${DIR}"

# ===========================================================================
# L0: SQL
# ===========================================================================
echo ""
echo "--- L0: SQL ---"
hyperfine --warmup 2 --min-runs 10 \
  "mm sql 'SELECT kind, COUNT(*) as n FROM files GROUP BY kind' --dir ${DIR}" \
  "mm sql 'SELECT ext, SUM(size) as total FROM files GROUP BY ext ORDER BY total DESC' --dir ${DIR}"

# ===========================================================================
# peek — raw per-file metadata
# ===========================================================================
echo ""
echo "--- mm peek pdf vs file/stat ---"
hyperfine --warmup 2 --min-runs 10 \
  --command-name "mm peek pdf" \
    "mm peek '${PDF}' --format json" \
  --command-name "file pdf" \
    "file '${PDF}'" \
  --command-name "stat pdf" \
    "stat ${STAT_FMT} '${PDF}'"

echo ""
echo "--- mm peek image vs file ---"
hyperfine --warmup 2 --min-runs 10 \
  --command-name "mm peek image" \
    "mm peek '${IMG}' --format json" \
  --command-name "file image" \
    "file '${IMG}'"

echo ""
echo "--- mm peek video vs file/ffprobe ---"
if command -v ffprobe &>/dev/null; then
  hyperfine --warmup 2 --min-runs 10 \
    --command-name "mm peek video" \
      "mm peek '${VID}' --format json" \
    --command-name "file video" \
      "file '${VID}'" \
    --command-name "ffprobe video" \
      "ffprobe -v quiet -print_format json -show_format -show_streams '${VID}'"
else
  hyperfine --warmup 2 --min-runs 10 \
    --command-name "mm peek video" \
      "mm peek '${VID}' --format json" \
    --command-name "file video" \
      "file '${VID}'"
fi

echo ""
echo "--- mm peek audio vs file/ffprobe ---"
if command -v ffprobe &>/dev/null; then
  hyperfine --warmup 2 --min-runs 10 \
    --command-name "mm peek audio" \
      "mm peek '${AUD}' --format json" \
    --command-name "file audio" \
      "file '${AUD}'" \
    --command-name "ffprobe audio" \
      "ffprobe -v quiet -print_format json -show_format -show_streams '${AUD}'"
else
  hyperfine --warmup 2 --min-runs 10 \
    --command-name "mm peek audio" \
      "mm peek '${AUD}' --format json" \
    --command-name "file audio" \
      "file '${AUD}'"
fi

# ===========================================================================
# mode=fast: cat — PDF text extraction
# ===========================================================================
echo ""
echo "--- mode=fast: mm cat PDF vs cat/strings ---"
hyperfine --warmup 1 --min-runs 10 \
  --command-name "mm cat pdf (fast,text)" \
    "mm cat '${PDF}' --mode fast" \
  --command-name "cat pdf > /dev/null" \
    "cat '${PDF}' > /dev/null" \
  --command-name "strings pdf" \
    "strings '${PDF}'"

# ===========================================================================
# mode=fast: cat — image metadata
# ===========================================================================
echo ""
echo "--- mode=fast mm cat image vs file ---"
hyperfine --warmup 1 --min-runs 10 \
  --command-name "mm cat image (fast)" \
    "mm cat '${IMG}' --mode fast" \
  --command-name "file image" \
    "file '${IMG}'"

# ===========================================================================
# mode=fast: cat — video metadata
# ===========================================================================
echo ""
echo "--- mode=fast: mm cat video vs file/ffprobe ---"
if command -v ffprobe &>/dev/null; then
  hyperfine --warmup 1 --min-runs 5 \
    --command-name "mm cat video (fast)" \
      "mm cat '${VID}' --mode fast" \
    --command-name "file video" \
      "file '${VID}'" \
    --command-name "ffprobe video" \
      "ffprobe -v quiet -print_format json -show_format -show_streams '${VID}'"
else
  hyperfine --warmup 1 --min-runs 5 \
    --command-name "mm cat video (fast)" \
      "mm cat '${VID}' --mode fast" \
    --command-name "file video" \
      "file '${VID}'"
fi

# ===========================================================================
# mode=fast: cat — audio metadata
# ===========================================================================
echo ""
echo "--- mode=fast: mm cat audio vs file/ffprobe ---"
if command -v ffprobe &>/dev/null; then
  hyperfine --warmup 1 --min-runs 5 \
    --command-name "mm cat audio (fast)" \
      "mm cat '${AUD}' --mode fast" \
    --command-name "file audio" \
      "file '${AUD}'" \
    --command-name "ffprobe audio" \
      "ffprobe -v quiet -print_format json -show_format -show_streams '${AUD}'"
else
  hyperfine --warmup 1 --min-runs 5 \
    --command-name "mm cat audio (fast)" \
      "mm cat '${AUD}' --mode fast" \
    --command-name "file audio" \
      "file '${AUD}'"
fi

# ===========================================================================
# cat head/tail — PDF text extraction with line limits
# ===========================================================================
echo ""
echo "--- mm cat -n (head/tail) vs head/tail on raw PDF ---"
hyperfine --warmup 2 --min-runs 10 \
  --command-name "mm cat -n 10 (head, extracts text)" \
    "mm cat '${PDF}' -n 10" \
  --command-name "mm cat -n -10 (tail, extracts text)" \
    "mm cat '${PDF}' -n -10" \
  --command-name "head -10 (raw bytes)" \
    "head -10 '${PDF}'" \
  --command-name "tail -10 (raw bytes)" \
    "tail -10 '${PDF}'"

# ===========================================================================
# Grep
# ===========================================================================
echo ""
echo "--- mm grep vs grep -r ---"
hyperfine --warmup 2 --min-runs 10 \
  --command-name "mm grep" \
    "mm grep 'TECO' ${DIR}" \
  --command-name "grep -r" \
    "grep -r 'TECO' ${DIR} || true" \
  --command-name "grep -rl (files only)" \
    "grep -rl 'TECO' ${DIR} || true"

# ===========================================================================
# Pipe composability
# ===========================================================================
echo ""
echo "--- Pipe: mm find | wc -l vs find | wc -l ---"
hyperfine --warmup 2 --min-runs 10 \
  --command-name "mm find (json) | wc -l" \
    "mm find ${DIR} --format json | wc -l" \
  --command-name "find | wc -l" \
    "find ${DIR} -type f | wc -l"

# ===========================================================================
# mode=accurate benchmarks (opt-in, requires LLM server)
# ===========================================================================
if [ "${BENCH_ACCURATE:-0}" = "1" ]; then
  echo ""
  echo "--- mode=accurate: keyframe mosaic + LLM ---"
  hyperfine --warmup 1 --min-runs 3 \
    "mm cat '${VID}' -m accurate"

  echo ""
  echo "--- mode=accurate: audio extraction ---"
  hyperfine --warmup 1 --min-runs 3 \
    "mm cat '${AUD}' -m accurate"
else
  echo ""
  echo "(accurate benchmarks skipped — set BENCH_ACCURATE=1 to enable, requires LLM server)"
fi

echo ""
echo "=== Done ==="
