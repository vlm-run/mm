#!/usr/bin/env bash
# Benchmark multi-modal extraction modes (--mode fast vs --mode accurate)
#
# Information-theoretic perspective: measures bits/s throughput —
# how fast we extract semantic information from raw media data.
#
# For each modality, reports:
#   - File size (bytes, bits)
#   - Resolution / duration / pages (modality-specific)
#   - Wall-clock time per mode
#   - Throughput: bits/s, bytes/s, pixels/s or seconds-of-media/s
#
# Usage: bash benchmarks/bench_modes.sh [data_dir]
#
# Requires: hyperfine, vlmctx CLI, ffprobe, identify (ImageMagick) optional

set -euo pipefail

DATA_DIR="${1:-$HOME/data/1-demo}"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  vlmctx multi-modal extraction benchmarks                  ║"
echo "║  Metric: maximize bits/s throughput, minimize latency       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Data directory: $DATA_DIR"
echo ""

# System info
vlmctx cat --help >/dev/null 2>&1 || { echo "vlmctx not found"; exit 1; }
python3 -c "
from vlmctx.sysinfo import collect
info = collect()
print(f'  ffmpeg:      {info.ffmpeg_version or \"not found\"}')
print(f'  GPU:         {info.gpu_name or \"none (CPU only)\"}')
print(f'  CUDA:        {info.cuda_available}')
print(f'  whisper:     {info.whisper_available}')
print(f'  scenedetect: {info.scenedetect_available}')
print(f'  docling:     {info.docling_available}')
" 2>/dev/null || true
echo ""

# --- Helpers ---
file_bits() { echo $(( $(stat -f%z "$1" 2>/dev/null || stat -c%s "$1" 2>/dev/null) * 8 )); }
file_bytes() { stat -f%z "$1" 2>/dev/null || stat -c%s "$1" 2>/dev/null; }

image_info() {
    local f="$1"
    local bytes=$(file_bytes "$f")
    local bits=$(( bytes * 8 ))
    # Get dimensions via vlmctx L1 (fast, uses Rust header-only parsing)
    local dims=$(vlmctx cat "$f" -l 1 2>/dev/null | grep -o '[0-9]*x[0-9]*' | head -1)
    local w=$(echo "$dims" | cut -dx -f1)
    local h=$(echo "$dims" | cut -dx -f2)
    local pixels=$(( ${w:-0} * ${h:-0} ))
    echo "  File:       $(basename "$f")"
    echo "  Size:       ${bytes} bytes ($(( bits )) bits)"
    echo "  Resolution: ${dims:-unknown}"
    echo "  Pixels:     ${pixels}"
    echo "  Bits/pixel: $(python3 -c "print(f'{$bits / max($pixels, 1):.2f}')")"
}

video_info() {
    local f="$1"
    local bytes=$(file_bytes "$f")
    local bits=$(( bytes * 8 ))
    # Get metadata via vlmctx L1
    local meta=$(vlmctx cat "$f" -l 1 2>/dev/null)
    local dims=$(echo "$meta" | grep -o '[0-9]*x[0-9]*' | head -1)
    local duration=$(echo "$meta" | grep -i duration | grep -oE '[0-9]+\.[0-9]+s' | head -1 | tr -d 's')
    local fps=$(echo "$meta" | grep -i fps | grep -oE '[0-9]+\.?[0-9]*' | head -1)
    echo "  File:       $(basename "$f")"
    echo "  Size:       ${bytes} bytes (${bits} bits)"
    echo "  Resolution: ${dims:-unknown}"
    echo "  Duration:   ${duration:-unknown}s"
    echo "  FPS:        ${fps:-unknown}"
    echo "  Bitrate:    $(python3 -c "d=float('${duration:-0}'); print(f'{$bits / max(d,0.01):.0f} bits/s ({$bits / max(d,0.01) / 1e6:.2f} Mbps)') if d > 0 else print('unknown')")"
}

audio_info() {
    local f="$1"
    local bytes=$(file_bytes "$f")
    local bits=$(( bytes * 8 ))
    local duration=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$f" 2>/dev/null | head -1)
    echo "  File:       $(basename "$f")"
    echo "  Size:       ${bytes} bytes (${bits} bits)"
    echo "  Duration:   ${duration:-unknown}s"
    echo "  Bitrate:    $(python3 -c "d=float('${duration:-0}'); print(f'{$bits / max(d,0.01):.0f} bits/s ({$bits / max(d,0.01) / 1e3:.0f} kbps)') if d > 0 else print('unknown')")"
}

pdf_info() {
    local f="$1"
    local bytes=$(file_bytes "$f")
    local bits=$(( bytes * 8 ))
    local pages=$(python3 -c "
try:
    import pypdfium2 as p; pdf=p.PdfDocument('$f'); print(len(pdf)); pdf.close()
except: print('?')
" 2>/dev/null)
    echo "  File:       $(basename "$f")"
    echo "  Size:       ${bytes} bytes (${bits} bits)"
    echo "  Pages:      ${pages}"
    echo "  Bits/page:  $(python3 -c "p=int('${pages:-0}') if '${pages}' != '?' else 1; print(f'{$bits / max(p,1):.0f}')")"
}

throughput_report() {
    # $1=label $2=bits $3=time_s $4=extra_unit $5=extra_value
    local bits=$2
    local time_s=$3
    python3 -c "
bits = $bits
t = $time_s
if t > 0:
    bps = bits / t
    Bps = bps / 8
    units = [('Gbps', 1e9), ('Mbps', 1e6), ('kbps', 1e3), ('bps', 1)]
    for name, div in units:
        if bps >= div:
            print(f'  Throughput:  {bps/div:.2f} {name} ({Bps/1e6:.2f} MB/s)')
            break
    print(f'  Latency:    {t*1000:.0f}ms')
"
    if [ -n "${4:-}" ] && [ -n "${5:-}" ]; then
        python3 -c "
v = float('${5}')
t = $time_s
if t > 0 and v > 0:
    print(f'  ${4}:  {v/t:.1f}/s')
"
    fi
}

# Find sample files
IMAGE=$(find "$DATA_DIR" -maxdepth 3 -type f \( -name "*.jpg" -o -name "*.png" \) | head -1)
VIDEO=$(find "$DATA_DIR" -maxdepth 3 -type f \( -name "*.mp4" -o -name "*.mkv" \) | head -1)
AUDIO=$(find "$DATA_DIR" -maxdepth 3 -type f \( -name "*.mp3" -o -name "*.wav" -o -name "*.m4a" \) | head -1)
PDF=$(find "$DATA_DIR" -maxdepth 3 -type f -name "*.pdf" | head -1)

# ============================================================
# IMAGE
# ============================================================
if [ -n "$IMAGE" ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "IMAGE"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    image_info "$IMAGE"
    echo ""

    IBITS=$(file_bits "$IMAGE")

    echo "  --- mode=fast ---"
    hyperfine --warmup 1 --min-runs 3 --export-json /tmp/vlmctx_bench_img_fast.json \
        "vlmctx cat '$IMAGE' -l 2 --mode fast --json 2>/dev/null" 2>&1 | grep -E 'Time|Range'
    IFAST=$(python3 -c "import json; print(json.load(open('/tmp/vlmctx_bench_img_fast.json'))['results'][0]['mean'])")
    throughput_report "image_fast" "$IBITS" "$IFAST"
    echo ""

    echo "  --- mode=accurate ---"
    hyperfine --warmup 1 --min-runs 3 --export-json /tmp/vlmctx_bench_img_acc.json \
        "vlmctx cat '$IMAGE' -l 2 --mode accurate --json 2>/dev/null" 2>&1 | grep -E 'Time|Range'
    IACC=$(python3 -c "import json; print(json.load(open('/tmp/vlmctx_bench_img_acc.json'))['results'][0]['mean'])")
    throughput_report "image_accurate" "$IBITS" "$IACC"
    echo ""
fi

# ============================================================
# VIDEO
# ============================================================
if [ -n "$VIDEO" ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "VIDEO"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    video_info "$VIDEO"
    echo ""

    VBITS=$(file_bits "$VIDEO")
    VDUR=$(vlmctx cat "$VIDEO" -l 1 2>/dev/null | grep -i duration | grep -oE '[0-9]+\.[0-9]+s' | head -1 | tr -d 's')

    echo "  --- mode=fast ---"
    hyperfine --warmup 1 --min-runs 2 --export-json /tmp/vlmctx_bench_vid_fast.json \
        "vlmctx cat '$VIDEO' -l 2 --mode fast --json 2>/dev/null" 2>&1 | grep -E 'Time|Range'
    VFAST=$(python3 -c "import json; print(json.load(open('/tmp/vlmctx_bench_vid_fast.json'))['results'][0]['mean'])")
    throughput_report "video_fast" "$VBITS" "$VFAST" "Media seconds" "${VDUR:-0}"
    echo ""

    echo "  --- mode=accurate ---"
    hyperfine --warmup 1 --min-runs 2 --export-json /tmp/vlmctx_bench_vid_acc.json \
        "vlmctx cat '$VIDEO' -l 2 --mode accurate --json 2>/dev/null" 2>&1 | grep -E 'Time|Range'
    VACC=$(python3 -c "import json; print(json.load(open('/tmp/vlmctx_bench_vid_acc.json'))['results'][0]['mean'])")
    throughput_report "video_accurate" "$VBITS" "$VACC" "Media seconds" "${VDUR:-0}"
    echo ""
fi

# ============================================================
# AUDIO
# ============================================================
if [ -n "$AUDIO" ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "AUDIO"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    audio_info "$AUDIO"
    echo ""

    ABITS=$(file_bits "$AUDIO")
    ADUR=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$AUDIO" 2>/dev/null | head -1)

    echo "  --- mode=fast ---"
    hyperfine --warmup 1 --min-runs 3 --export-json /tmp/vlmctx_bench_aud_fast.json \
        "vlmctx cat '$AUDIO' -l 2 --mode fast --json 2>/dev/null" 2>&1 | grep -E 'Time|Range'
    AFAST=$(python3 -c "import json; print(json.load(open('/tmp/vlmctx_bench_aud_fast.json'))['results'][0]['mean'])")
    throughput_report "audio_fast" "$ABITS" "$AFAST" "Media seconds" "${ADUR:-0}"
    echo ""

    echo "  --- mode=accurate ---"
    hyperfine --warmup 1 --min-runs 3 --export-json /tmp/vlmctx_bench_aud_acc.json \
        "vlmctx cat '$AUDIO' -l 2 --mode accurate --json 2>/dev/null" 2>&1 | grep -E 'Time|Range'
    AACC=$(python3 -c "import json; print(json.load(open('/tmp/vlmctx_bench_aud_acc.json'))['results'][0]['mean'])")
    throughput_report "audio_accurate" "$ABITS" "$AACC" "Media seconds" "${ADUR:-0}"
    echo ""
fi

# ============================================================
# PDF / DOCUMENT
# ============================================================
if [ -n "$PDF" ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "DOCUMENT (PDF)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    pdf_info "$PDF"
    echo ""

    PBITS=$(file_bits "$PDF")
    PPAGES=$(python3 -c "
try:
    import pypdfium2 as p; pdf=p.PdfDocument('$PDF'); print(len(pdf)); pdf.close()
except: print('1')
" 2>/dev/null)

    echo "  --- L1 extraction ---"
    hyperfine --warmup 1 --min-runs 5 --export-json /tmp/vlmctx_bench_pdf.json \
        "vlmctx cat '$PDF' -l 1 --json 2>/dev/null" 2>&1 | grep -E 'Time|Range'
    PTIME=$(python3 -c "import json; print(json.load(open('/tmp/vlmctx_bench_pdf.json'))['results'][0]['mean'])")
    throughput_report "pdf_l1" "$PBITS" "$PTIME" "Pages" "${PPAGES:-1}"
    echo ""
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Done. Key metric: bits/s = information extraction rate     ║"
echo "║  Higher bits/s = more efficient semantic extraction         ║"
echo "╚══════════════════════════════════════════════════════════════╝"
