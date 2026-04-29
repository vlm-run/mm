#!/usr/bin/env bash
# mm CLI Group-1 benchmarks (mini dataset) — ~249 files, ~1.4GB
#
# Group 1 = the Unix-comparable surface: find / wc / grep (plain, no
# --semantic) and sql. The point is to show how mm matches (or beats) its
# native Unix counterparts on speed across a larger directory.
#
# For multimodal extraction (cat, grep --semantic), see bench_cli_mini.sh.
#
# Usage: ./benchmarks/bench_cli_mini_metadata.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/data"
MINI_URL="https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-mini.tar.gz"

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

if [ ! -d "${DATA_DIR}/mmbench-mini" ]; then
  echo "Downloading mmbench-mini (~1.4GB)..."
  mkdir -p "${DATA_DIR}"
  curl -sL "${MINI_URL}" | tar xzf - -C "${DATA_DIR}"
  echo "  → ${DATA_DIR}/mmbench-mini"
fi

DIR="${DATA_DIR}/mmbench-mini"

FILE_COUNT="$(find "${DIR}" -type f ! -name '.DS_Store' | wc -l | tr -d ' ')"
TOTAL_SIZE="$(du -sh "${DIR}" | awk '{print $1}')"
echo "=== mm CLI Group-1 Benchmarks (mini) ==="
echo "Data: ${DIR} (${FILE_COUNT} files, ${TOTAL_SIZE})"
echo "Group 1: find / wc / grep / sql vs native Unix counterparts"
echo ""

# ===========================================================================
# find — discovery + listing
# ===========================================================================
echo "--- mm find vs find ---"
hyperfine --warmup 2 --min-runs 10 \
  --command-name "mm find" \
    ".venv/bin/mm find ${DIR}" \
  --command-name "mm find (json)" \
    ".venv/bin/mm find ${DIR} --format json" \
  --command-name "find" \
    "find ${DIR} -type f" \
  --command-name "find + stat (size)" \
    "find ${DIR} -type f -exec stat ${STAT_FMT} {} +" \
  --command-name "find + file (mime)" \
    "find ${DIR} -type f -exec file --brief --mime-type {} +"

echo ""
echo "--- mm find with kind filters (no Unix equivalent) ---"
hyperfine --warmup 2 --min-runs 10 \
  ".venv/bin/mm find ${DIR} --kind document" \
  ".venv/bin/mm find ${DIR} --kind image" \
  ".venv/bin/mm find ${DIR} --kind video" \
  ".venv/bin/mm find ${DIR} --ext .pdf"

echo ""
echo "--- mm find vs find (ext-filtered) ---"
hyperfine --warmup 2 --min-runs 10 \
  --command-name "mm find --kind document" \
    ".venv/bin/mm find ${DIR} --kind document --format tsv" \
  --command-name "find -name '*.pdf'" \
    "find ${DIR} -type f -name '*.pdf'" \
  --command-name "mm find --ext .pdf" \
    ".venv/bin/mm find ${DIR} --ext .pdf --format tsv" \
  --command-name "find (pdf+docx+html)" \
    "find ${DIR} -type f \\( -name '*.pdf' -o -name '*.docx' -o -name '*.html' \\)"

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
    "du -sh ${DIR}" \
  --command-name "find | wc -l + du -sh" \
    "echo \$(find ${DIR} -type f | wc -l) files, \$(du -sh ${DIR} | awk '{print \$1}')"

# ===========================================================================
# sql — analytical queries on the file index
# ===========================================================================
echo ""
echo "--- mm sql ---"
hyperfine --warmup 2 --min-runs 10 \
  ".venv/bin/mm sql 'SELECT kind, COUNT(*) as n FROM files GROUP BY kind ORDER BY n DESC' --dir ${DIR} --pre-index" \
  ".venv/bin/mm sql 'SELECT ext, SUM(size) as total FROM files GROUP BY ext ORDER BY total DESC LIMIT 10' --dir ${DIR} --pre-index" \
  ".venv/bin/mm sql 'SELECT kind, COUNT(*) as n, SUM(size) as bytes FROM files GROUP BY kind ORDER BY bytes DESC' --dir ${DIR} --pre-index"

# ===========================================================================
# grep — plain text search (no --semantic)
#
# All three commands tolerate exit-code 1 ("no matches") via ``|| true`` so
# hyperfine's pre-warmup check doesn't abort when the search term isn't
# present in the dataset. The work is still performed — we're timing the
# scan, not the match count.
# ===========================================================================
echo ""
echo "--- mm grep vs grep -r ---"
hyperfine --warmup 2 --min-runs 10 \
  --command-name "mm grep 'invoice'" \
    ".venv/bin/mm grep 'invoice' ${DIR} || true" \
  --command-name "grep -r 'invoice'" \
    "grep -r 'invoice' ${DIR} || true" \
  --command-name "grep -rl 'invoice'" \
    "grep -rl 'invoice' ${DIR} || true"

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
