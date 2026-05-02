# mm bench recording — vlmgw — 2026-05-01

Run: `mm bench` against `/Users/sudeep/data/mmbench-tiny` (rounds=1, warmup=0, 9 files / 43.1 MB, wall=3.60s).
Benchfile: `benchmarks/vlmgw_bench_commands.py`.
Host: `Sudeeps-M3-Max.local` · Apple M3 Max (16 threads) · macOS 14.6 · Python 3.12.9 · mm v0.10.0.
Profile: `vlmgw` (`https://26bd-12-30-39-214.ngrok-free.app/v1/openai/`, default model `qwen/qwen3.5-0.8b`).

---

╭────────────┬───────────────────┬─────────────────────────────────────────┬──────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model             │ Base Command                            │ Extra Args                           │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────────┼─────────────────────────────────────────┼──────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼────────────┤
│ model      │ qwen/qwen3.5-0.8b │ python _multi_image_call.py <img> <img> │ --prompt 'Compare these two images.' │ 3.52s │ 0.00ms │ 3.52s │ 3.52s │ 0.57x │  0.1 │ 17.70 Mbps │
╰────────────┴───────────────────┴─────────────────────────────────────────┴──────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴────────────╯
args: {"img": ["1-vqa-car.jpg", "invoice.jpg"]}
```text
Of course. Here is a detailed comparison of the two images.

---

### **Image 1: A Vintage Car**

**Description:**
This image displays a classic, two-door Volkswagen Beetle, painted in a light teal or mint green color. The car is parked on a paved street in front of a weathered, yellowish-beige building with two wooden doors. The photograph is taken from a side angle, showcasing the car's rounded, bulbous body and chrome hubcaps. The lighting suggests a sunny day.

---

### **Image 2: A Digital Invoice**

**Description:**
```
3.52s • 182.1 KB • 51.8 KB/s
