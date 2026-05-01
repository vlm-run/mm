#!/usr/bin/env python
"""Benchmark all 19 video encoders against bakery.mp4.

Measures wall time, peak RSS, and message/part counts per encoder. Each
encoder runs with a single warmup round followed by 3 timed rounds; we
report mean / std / min / max in milliseconds.

Output: rich console table + JSON dump suitable for archival.
"""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import time
import tracemalloc
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

VIDEO_ENCODERS: list[str] = [
    "video-frames",
    "video-frames-w-transcript",
    "video-mosaic",
    "video-mosaic-w-transcript",
    "video-shots",
    "video-shots-w-transcript",
    "video-shot-mosaic",
    "video-shot-mosaic-w-transcript",
    "video-keyframes",
    "video-keyframes-w-transcript",
    "video-summary",
    "video-summary-w-transcript",
    "video-clips",
    "video-clips-w-transcript",
    "video-chunks",
    "video-captions",
    "video-transcript",
]


@dataclass
class EncoderRun:
    encoder: str
    elapsed_ms: list[float] = field(default_factory=list)
    n_messages: int = 0
    n_parts: int = 0
    n_text_parts: int = 0
    n_image_parts: int = 0
    bytes_payload: int = 0
    peak_alloc_b: int = 0
    error: str | None = None

    @property
    def mean_ms(self) -> float:
        return statistics.mean(self.elapsed_ms) if self.elapsed_ms else 0.0

    @property
    def std_ms(self) -> float:
        return statistics.stdev(self.elapsed_ms) if len(self.elapsed_ms) > 1 else 0.0

    @property
    def min_ms(self) -> float:
        return min(self.elapsed_ms) if self.elapsed_ms else 0.0

    @property
    def max_ms(self) -> float:
        return max(self.elapsed_ms) if self.elapsed_ms else 0.0


def _summarize_messages(messages: list[dict[str, Any]]) -> dict[str, int]:
    n_msgs = len(messages)
    n_parts = 0
    n_text = 0
    n_image = 0
    bytes_payload = 0
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            for p in content:
                n_parts += 1
                ptype = p.get("type")
                if ptype == "text":
                    n_text += 1
                    bytes_payload += len(p.get("text", "").encode("utf-8"))
                elif ptype == "image_url":
                    n_image += 1
                    url = p.get("image_url", {}).get("url", "")
                    bytes_payload += len(url)
                elif ptype == "input_image":
                    n_image += 1
                    bytes_payload += (
                        len(p.get("image", "")) if isinstance(p.get("image"), str) else 0
                    )
                else:
                    bytes_payload += len(json.dumps(p))
        elif isinstance(content, str):
            n_parts += 1
            n_text += 1
            bytes_payload += len(content.encode("utf-8"))
    return {
        "n_messages": n_msgs,
        "n_parts": n_parts,
        "n_text_parts": n_text,
        "n_image_parts": n_image,
        "bytes_payload": bytes_payload,
    }


def _clear_caches() -> None:
    """Drop all process-local mm video caches so each round runs cold.

    Each function decorated with :func:`mm.cache.memoize_file` exposes a
    ``cache_clear`` attribute; we just call them in turn.
    """
    try:
        from mm.video import probe

        probe.cache_clear()
    except (ImportError, AttributeError):
        pass
    try:
        from mm.common.video.shot_detection import detect_scenes

        detect_scenes.cache_clear()
    except (ImportError, AttributeError):
        pass
    try:
        from mm.encoders.video._transcript import transcript_messages

        transcript_messages.cache_clear()
    except (ImportError, AttributeError):
        pass


def run_encoder(
    name: str,
    path: Path,
    rounds: int,
    warmup: bool,
    *,
    cold: bool = False,
) -> EncoderRun:
    from mm.encoders import get

    run = EncoderRun(encoder=name)
    try:
        encoder = get(name)
    except KeyError as e:
        run.error = f"encoder not found: {e}"
        return run

    if warmup:
        if cold:
            _clear_caches()
        try:
            list(encoder.encode(path))
        except Exception as e:
            run.error = f"warmup failed: {type(e).__name__}: {e}"
            return run

    last_messages: list[dict[str, Any]] = []
    peak_alloc = 0
    for _ in range(rounds):
        if cold:
            _clear_caches()
        gc.collect()
        tracemalloc.start()
        t0 = time.monotonic()
        try:
            messages = list(encoder.encode(path))
        except Exception as e:
            tracemalloc.stop()
            run.error = f"{type(e).__name__}: {e}"
            return run
        elapsed = (time.monotonic() - t0) * 1000.0
        _, this_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        run.elapsed_ms.append(elapsed)
        peak_alloc = max(peak_alloc, this_peak)
        last_messages = messages

    summary = _summarize_messages(last_messages)
    run.n_messages = summary["n_messages"]
    run.n_parts = summary["n_parts"]
    run.n_text_parts = summary["n_text_parts"]
    run.n_image_parts = summary["n_image_parts"]
    run.bytes_payload = summary["bytes_payload"]
    run.peak_alloc_b = peak_alloc
    return run


def render_table(runs: list[EncoderRun], out: Path) -> None:
    """Render a Rich table summarizing the runs and write a markdown report."""
    from rich.console import Console
    from rich.table import Table

    table = Table(title=f"Video encoder benchmarks — {out.parent.name}", show_lines=False)
    table.add_column("Encoder", style="cyan", no_wrap=True)
    table.add_column("Mean ms", justify="right")
    table.add_column("Std", justify="right")
    table.add_column("Min", justify="right")
    table.add_column("Max", justify="right")
    table.add_column("Msgs", justify="right")
    table.add_column("Parts", justify="right")
    table.add_column("Imgs", justify="right")
    table.add_column("Payload", justify="right")
    table.add_column("Peak alloc", justify="right")
    table.add_column("Error", style="red")

    runs_sorted = sorted(runs, key=lambda r: r.mean_ms or float("inf"))
    for r in runs_sorted:
        row = [
            r.encoder,
            f"{r.mean_ms:,.0f}",
            f"{r.std_ms:,.0f}",
            f"{r.min_ms:,.0f}",
            f"{r.max_ms:,.0f}",
            str(r.n_messages),
            str(r.n_parts),
            str(r.n_image_parts),
            _fmt_bytes(r.bytes_payload),
            _fmt_bytes(r.peak_alloc_b),
            r.error or "",
        ]
        table.add_row(*row)

    console = Console(record=True, width=180)
    console.print(table)


def _fmt_bytes(b: int) -> str:
    if b < 1024:
        return f"{b}B"
    if b < 1024 * 1024:
        return f"{b / 1024:,.1f}K"
    if b < 1024 * 1024 * 1024:
        return f"{b / 1024 / 1024:,.1f}M"
    return f"{b / 1024 / 1024 / 1024:,.2f}G"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--no-warmup", action="store_true")
    ap.add_argument(
        "--cold",
        action="store_true",
        help="Clear process-local mm caches before each round (apples-to-apples with pre-cache numbers).",
    )
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--encoders", nargs="+", default=None)
    args = ap.parse_args()

    encoders = args.encoders or VIDEO_ENCODERS

    runs: list[EncoderRun] = []
    for name in encoders:
        print(f"  -> {name} ...", flush=True)
        run = run_encoder(name, args.video, args.rounds, warmup=not args.no_warmup, cold=args.cold)
        if run.error:
            print(f"     [error] {run.error}")
        else:
            print(
                f"     mean={run.mean_ms:,.0f}ms "
                f"min={run.min_ms:,.0f}ms "
                f"max={run.max_ms:,.0f}ms "
                f"msgs={run.n_messages} parts={r if (r := run.n_parts) else 0}",
                flush=True,
            )
        runs.append(run)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "video": str(args.video.resolve()),
                "rounds": args.rounds,
                "warmup": not args.no_warmup,
                "cold": args.cold,
                "runs": [asdict(r) for r in runs],
            },
            indent=2,
        )
    )

    render_table(runs, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
