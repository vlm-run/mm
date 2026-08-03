# mm-bench-260803 — storage write path

4-core VM, Python 3.12, release build. Fixture: 300 x 200-line `.py` +
40 x 640x480 PNG. Baseline = PR #181 head (`a43edfb`).

| Operation | Baseline | Now | Speedup |
| :--- | ---: | ---: | ---: |
| `Context.save()` warm (nothing changed) | 212 ms | 8 ms | 26x |
| `Context.save()` cold (340 files) | 1,220 ms | 175 ms | 7x |
| cat one fresh file, 340-sibling dir | 96 ms | 18 ms | O(dirsize) → O(1) |
| serial 100-file cat extract loop | 736 ms | 162 ms cold / 5 ms warm | 4.5x / 147x |
| `scan_single` vs parent-dir walk (Criterion, 50 siblings) | 1.49 ms | 1.37 µs | ~1,090x |
| `extract_metadata_batch` vs serial loop (200 x 8 KB .py) | 4.39 ms | 1.37 ms | 3.2x (17x on 300 files) |
| `ensure_metadata`, already-indexed row | — | 3.8 µs | — |

`extract_metadata_batch` carries ~3-4 ms fixed rayon dispatch per call:
near-empty-file trees favor the serial loop in isolation; realistic content
amortizes it and end-to-end saves win regardless.

Benchmarks: `cargo bench -p mm-core --bench metadata_extract`,
`pytest tests/python/test_benchmark.py -m slow -k "save or ensure_metadata or ab_"`.
