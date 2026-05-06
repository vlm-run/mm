#!/usr/bin/env bash
# mm CLI Group-1 benchmarks (tiny dataset) — 4 files, ~42MB
#
# Group 1 = the Unix-comparable surface: find / wc / grep (plain, no
# --semantic) and sql. The point is to show how mm matches (or beats) its
# native Unix counterparts on speed.
#
# For multimodal extraction (cat, grep --semantic), see bench_cli_tiny.sh.
#
# Usage: ./benchmarks/bench_cli_tiny_metadata.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/data"
TINY_URL="https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-tiny.tar.gz"

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
AUD="${DIR}/audio.mp3"

FILE_COUNT="$(find "${DIR}" -type f ! -name '.DS_Store' | wc -l | tr -d ' ')"
echo "=== mm CLI Group-1 Benchmarks (tiny) ==="
echo "Data: ${DIR} (${FILE_COUNT} files, $(du -sh "${DIR}" | awk '{print $1}'))"
echo "Group 1: find / wc / grep / sql vs native Unix counterparts"
echo ""

# ===========================================================================
# find — discovery + listing
# ===========================================================================
echo "--- mm find vs find ---"
hyperfine --warmup 2 --min-runs 10 \
  --command-name "mm find (tsv)" \
    ".venv/bin/mm find ${DIR} --format tsv" \
  --command-name "mm find (json)" \
    ".venv/bin/mm find ${DIR} --format json" \
  --command-name "find" \
    "find ${DIR} -type f" \
  --command-name "find + stat (size)" \
    "find ${DIR} -type f -exec stat ${STAT_FMT} {} +" \
  --command-name "find + file (mime)" \
    "find ${DIR} -type f -exec file --brief --mime-type {} +"

# ===========================================================================
# peek — raw per-file metadata
# ===========================================================================
echo ""
echo "--- mm peek vs file/stat/ffprobe ---"
PEEK_CMDS=(
  --command-name "mm peek pdf"     ".venv/bin/mm peek '${PDF}' --format json"
  --command-name "mm peek image"   ".venv/bin/mm peek '${IMG}' --format json"
  --command-name "mm peek video"   ".venv/bin/mm peek '${VID}' --format json"
  --command-name "mm peek audio"   ".venv/bin/mm peek '${AUD}' --format json"
  --command-name "file (4 files)"  "file '${PDF}' '${IMG}' '${VID}' '${AUD}'"
  --command-name "stat (4 files)"  "stat ${STAT_FMT} '${PDF}' '${IMG}' '${VID}' '${AUD}'"
)
if command -v ffprobe &>/dev/null; then
  PEEK_CMDS+=(--command-name "ffprobe video" \
    "ffprobe -v quiet -print_format json -show_format -show_streams '${VID}'")
fi
hyperfine --warmup 2 --min-runs 10 "${PEEK_CMDS[@]}"

# ===========================================================================
# wc — counting
# ===========================================================================
echo ""
echo "--- mm wc vs wc/du ---"
hyperfine --warmup 2 --min-runs 10 \
  --command-name "mm wc" \
    ".venv/bin/mm wc ${DIR}" \
  --command-name "mm wc --by-kind" \
    ".venv/bin/mm wc ${DIR} --by-kind" \
  --command-name "wc -l (line count)" \
    "find ${DIR} -type f -exec wc -l {} +" \
  --command-name "du -sh" \
    "du -sh ${DIR}"

# ===========================================================================
# sql — analytical queries on the file index
# ===========================================================================
echo ""
echo "--- mm sql ---"
hyperfine --warmup 2 --min-runs 10 \
  ".venv/bin/mm sql 'SELECT kind, COUNT(*) as n FROM files GROUP BY kind' --dir ${DIR} --pre-index" \
  ".venv/bin/mm sql 'SELECT ext, SUM(size) as total FROM files GROUP BY ext ORDER BY total DESC' --dir ${DIR} --pre-index"

# ===========================================================================
# grep — plain text search (no --semantic)
#
# All three commands tolerate exit-code 1 ("no matches") via ``|| true`` so
# hyperfine's pre-warmup check doesn't abort when the search term isn't
# present. The work is still performed — we're timing the scan, not the
# match count.
# ===========================================================================
echo ""
echo "--- mm grep vs grep -r ---"
hyperfine --warmup 2 --min-runs 10 \
  --command-name "mm grep" \
    ".venv/bin/mm grep 'TECO' ${DIR} || true" \
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
    ".venv/bin/mm find ${DIR} --format json | wc -l" \
  --command-name "find | wc -l" \
    "find ${DIR} -type f | wc -l"

echo ""
echo "=== Done ==="
