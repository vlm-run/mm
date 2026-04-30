#!/usr/bin/env bash
# mm CLI benchmarks (mini dataset) — ~249 files, ~1.4GB multimodal
# Usage: ./benchmarks/bench_cli_mini.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/data"
MINI_URL="https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-mini.tar.gz"

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
if [ ! -d "${DATA_DIR}/mmbench-mini" ]; then
  echo "Downloading mmbench-mini (~1.4GB)..."
  mkdir -p "${DATA_DIR}"
  curl -sL "${MINI_URL}" | tar xzf - -C "${DATA_DIR}"
  echo "  → ${DATA_DIR}/mmbench-mini"
fi

DIR="${DATA_DIR}/mmbench-mini"

FILE_COUNT="$(find "${DIR}" -type f ! -name '.DS_Store' | wc -l | tr -d ' ')"
TOTAL_SIZE="$(du -sh "${DIR}" | awk '{print $1}')"
echo "=== mm CLI Benchmarks (mini) ==="
echo "Data: ${DIR} (${FILE_COUNT} files, ${TOTAL_SIZE})"
echo ""

# Pick representative files from each subdirectory
PDF="${DIR}/documents/research-paper.pdf"
PDF2="${DIR}/documents/construction-plan-set.pdf"
HTML="${DIR}/documents/10k-example.html"

# Discover first available video/audio/image if present
VID="$(find "${DIR}/video" -type f 2>/dev/null | head -1 || true)"
AUD="$(find "${DIR}/audio" -type f 2>/dev/null | head -1 || true)"
IMG="$(find "${DIR}/images" -type f 2>/dev/null | head -1 || true)"

# ===========================================================================
# L0: find
# ===========================================================================
echo "--- L0: mm find vs find ---"
hyperfine --warmup 2 --min-runs 10 \
  --command-name "mm find" \
    "mm find ${DIR}" \
  --command-name "mm find (json)" \
    "mm find ${DIR} --format json" \
  --command-name "find" \
    "find ${DIR} -type f" \
  --command-name "find + stat (size)" \
    "find ${DIR} -type f -exec stat ${STAT_FMT} {} +" \
  --command-name "find + file (mime)" \
    "find ${DIR} -type f -exec file --brief --mime-type {} +"

echo ""
echo "--- L0: mm find with filters ---"
hyperfine --warmup 2 --min-runs 10 \
  "mm find ${DIR} --tree --depth 2" \
  "mm find ${DIR} --kind document" \
  "mm find ${DIR} --kind image" \
  "mm find ${DIR} --kind video" \
  "mm find ${DIR} --ext .pdf"

echo ""
echo "--- L0: mm find vs find (filtered) ---"
hyperfine --warmup 2 --min-runs 10 \
  --command-name "mm find --kind document" \
    "mm find ${DIR} --kind document --format tsv" \
  --command-name "find -name '*.pdf'" \
    "find ${DIR} -type f -name '*.pdf'" \
  --command-name "mm find --ext .pdf" \
    "mm find ${DIR} --ext .pdf --format tsv" \
  --command-name "find (pdf+docx+html)" \
    "find ${DIR} -type f \\( -name '*.pdf' -o -name '*.docx' -o -name '*.html' \\)"

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
    "du -sh ${DIR}" \
  --command-name "find | wc -l + du -sh" \
    "echo \$(find ${DIR} -type f | wc -l) files, \$(du -sh ${DIR} | awk '{print \$1}')"

# ===========================================================================
# L0: SQL
# ===========================================================================
echo ""
echo "--- L0: SQL ---"
hyperfine --warmup 2 --min-runs 10 \
  "mm sql 'SELECT kind, COUNT(*) as n FROM files GROUP BY kind ORDER BY n DESC' --dir ${DIR}" \
  "mm sql 'SELECT ext, SUM(size) as total FROM files GROUP BY ext ORDER BY total DESC LIMIT 10' --dir ${DIR}" \
  "mm sql 'SELECT kind, COUNT(*) as n, SUM(size) as bytes FROM files GROUP BY kind ORDER BY bytes DESC' --dir ${DIR}"

# ===========================================================================
# mode=fast: cat — PDF text extraction
# ===========================================================================
echo ""
echo "--- mode=fast: mm cat PDF vs cat/strings ---"
hyperfine --warmup 1 --min-runs 5 \
  --command-name "mm cat pdf (L1 text)" \
    "mm cat '${PDF}' --mode fast" \
  --command-name "cat pdf > /dev/null" \
    "cat '${PDF}' > /dev/null" \
  --command-name "strings pdf" \
    "strings '${PDF}'"

echo ""
echo "--- mode/fast: mm cat across document types ---"
hyperfine --warmup 1 --min-runs 5 \
  --command-name "mm cat pdf" \
    "mm cat '${PDF}' --mode fast" \
  --command-name "mm cat large pdf" \
    "mm cat '${PDF2}' --mode fast" \
  --command-name "mm cat html" \
    "mm cat '${HTML}' --mode fast"

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
# mode=fast: cat — video metadata (if available)
# ===========================================================================
if [ -n "${VID}" ]; then
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
fi

# ===========================================================================
# mode=fast: cat — audio metadata (if available)
# ===========================================================================
if [ -n "${AUD}" ]; then
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
fi

# ===========================================================================
# mode=fast: cat — image metadata (if available)
# ===========================================================================
if [ -n "${IMG}" ]; then
  echo ""
  echo "--- mode=fast: mm cat image vs file/mdls ---"
  if command -v mdls &>/dev/null; then
    hyperfine --warmup 1 --min-runs 10 \
      --command-name "mm cat image (fast)" \
        "mm cat '${IMG}' --mode fast" \
      --command-name "file image" \
        "file '${IMG}'" \
      --command-name "mdls image (dimensions)" \
        "mdls -name kMDItemPixelWidth -name kMDItemPixelHeight '${IMG}'"
  else
    hyperfine --warmup 1 --min-runs 10 \
      --command-name "mm cat image (fast)" \
        "mm cat '${IMG}' --mode fast" \
      --command-name "file image" \
        "file '${IMG}'"
  fi
fi

# ===========================================================================
# Grep
# ===========================================================================
echo ""
echo "--- mm grep vs grep -r ---"
hyperfine --warmup 2 --min-runs 10 \
  --command-name "mm grep" \
    "mm grep 'financial' ${DIR}" \
  --command-name "grep -r" \
    "grep -r 'financial' ${DIR} || true" \
  --command-name "grep -rl (files only)" \
    "grep -rl 'financial' ${DIR} || true"

echo ""
echo "--- mm grep vs grep (filtered by kind) ---"
hyperfine --warmup 2 --min-runs 10 \
  --command-name "mm grep --kind document" \
    "mm grep 'financial' ${DIR} --kind document" \
  --command-name "find *.pdf | xargs grep -l" \
    "find ${DIR} -name '*.pdf' -exec grep -l 'financial' {} + 2>/dev/null || true"

# ===========================================================================
# Pipe composability
# ===========================================================================
echo ""
echo "--- Pipe: mm find | wc -l vs find | wc -l ---"
hyperfine --warmup 2 --min-runs 10 \
  --command-name "mm find --kind image (json) | wc -l" \
    "mm find ${DIR} --kind image --format json | wc -l" \
  --command-name "find (image exts) | wc -l" \
    "find ${DIR} -type f \\( -name '*.jpg' -o -name '*.png' -o -name '*.gif' -o -name '*.webp' \\) | wc -l" \
  --command-name "mm find --kind video (json) | wc -l" \
    "mm find ${DIR} --kind video --format json | wc -l" \
  --command-name "find (video exts) | wc -l" \
    "find ${DIR} -type f \\( -name '*.mp4' -o -name '*.mkv' -o -name '*.webm' -o -name '*.avi' \\) | wc -l" \
  --command-name "mm find (json) | wc -l" \
    "mm find ${DIR} --format json | wc -l" \
  --command-name "find | wc -l" \
    "find ${DIR} -type f | wc -l"

# ===========================================================================
# mode=accurate benchmarks (opt-in, requires LLM server)
# ===========================================================================
if [ "${BENCH_ACCURATE:-0}" = "1" ]; then
  if [ -n "${VID}" ]; then
    echo ""
    echo "--- mode=accurate: keyframe mosaic + LLM ---"
    hyperfine --warmup 1 --min-runs 3 \
      "mm cat '${VID}' -m accurate"
  fi

  if [ -n "${AUD}" ]; then
    echo ""
    echo "--- mode=accurate: audio extraction ---"
    hyperfine --warmup 1 --min-runs 3 \
      "mm cat '${AUD}' -m accurate"
  fi
else
  echo ""
  echo "(mode=accurate benchmarks skipped — set BENCH_ACCURATE=1 to enable, requires LLM server)"
fi

echo ""
echo "=== Done ==="
