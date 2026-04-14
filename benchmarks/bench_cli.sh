#!/usr/bin/env bash
# mm CLI benchmarks using hyperfine
# Usage: ./benchmarks/bench_cli.sh
set -euo pipefail

DEMO_DIR="${HOME}/data/1-demo"
YOUTUBE_DIR="${HOME}/data/youtube"
SMALL_VIDEO="${YOUTUBE_DIR}/-j1XP2vZsDY.mp4"
LARGE_VIDEO="${YOUTUBE_DIR}/CnxzrX9tNoc.mp4"

echo "=== mm CLI Benchmarks ==="
echo ""

# L0 commands on real multimodal data (249 files)
echo "--- L0: find on ${DEMO_DIR} ---"
hyperfine --warmup 2 --min-runs 10 \
  "mm find ${DEMO_DIR}" \
  "mm find ${DEMO_DIR} --tree --depth 1" \
  "mm wc ${DEMO_DIR}" \
  "mm find ${DEMO_DIR} --kind image" \
  "mm find ${DEMO_DIR} --format json"

echo ""
echo "--- L0: SQL on ${DEMO_DIR} ---"
hyperfine --warmup 2 --min-runs 10 \
  "mm sql 'SELECT kind, COUNT(*) as n FROM files GROUP BY kind' --dir ${DEMO_DIR}" \
  "mm sql 'SELECT ext, SUM(size) as total FROM files GROUP BY ext ORDER BY total DESC LIMIT 10' --dir ${DEMO_DIR}"

echo ""
echo "--- L1: cat on video files ---"
if [ -f "${SMALL_VIDEO}" ]; then
  hyperfine --warmup 1 --min-runs 5 \
    "mm cat '${SMALL_VIDEO}'"
fi

echo ""
echo "--- Keyframe mosaic extraction ---"
if [ -f "${SMALL_VIDEO}" ]; then
  hyperfine --warmup 1 --min-runs 5 \
    "mm cat '${SMALL_VIDEO}' -m accurate"
fi

if [ -f "${LARGE_VIDEO}" ]; then
  hyperfine --warmup 1 --min-runs 3 \
    "mm cat '${LARGE_VIDEO}' -m accurate"
fi

echo ""
echo "--- Audio extraction (2x speed) ---"
if [ -f "${SMALL_VIDEO}" ]; then
  hyperfine --warmup 1 --min-runs 5 \
    "mm cat '${SMALL_VIDEO}' -m accurate"
fi

echo ""
echo "--- Pipe composability ---"
hyperfine --warmup 2 --min-runs 5 \
  "mm find ${DEMO_DIR} --kind image --format json | wc -l" \
  "mm find ${DEMO_DIR} --kind video | wc -l"

echo ""
echo "=== Done ==="
