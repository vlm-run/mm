# mm bench recording — vlmgw — 2026-05-01

Run: `mm bench` against `/Users/sudeep/data/mmbench-tiny` (rounds=3, warmup=1, 9 files / 43.1 MB, wall=1025.52s).
Benchfile: `benchmarks/vlmgw_bench_commands.py`.
Host: `Sudeeps-M3-Max.local` · Apple M3 Max (16 threads) · macOS 14.6 · Python 3.12.9 · mm v0.10.0.
Profile: `vlmgw` (`https://26bd-12-30-39-214.ngrok-free.app/v1/openai/`, default model `qwen/qwen3.5-0.8b`).

---

╭────────────┬──────────────┬───────────────────────────────────────────────────┬───────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model        │ Base Command                                      │ Extra Args    │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────┼───────────────────────────────────────────────────┼───────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ noop       │ vlm-run/noop │ mm cat <img> --mode fast --no-cache --format json │ --prompt ping │ 867ms │ 12.6ms │ 858ms │ 882ms │ 1.15x │  0.0 │ 8.50 Mbps │
╰────────────┴──────────────┴───────────────────────────────────────────────────┴───────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Error code: 404 - {'detail': {'error': {'message': \"Model 'vlm-run/noop' not found. Available: ['Qwen/Qwen3.5-0.8B', 'facebook/sam3', 'fastino/gliner2-multi-v1', 'ggml-org/SmolVLM-256M-Instruct-GGUF', 'ggml-org/SmolVLM2-256M-Video-Instruct-GGUF', 'ggml-org/SmolVLM2-500M-Video-Instruct-GGUF', 'ggml-org/smolvlm-256m-instruct-gguf', 'ggml-org/smolvlm2-256m-video-instruct-gguf', 'ggml-org/smolvlm2-500m-video-instruct-gguf', 'microsoft/Florence-2-base-ft', 'microsoft/florence-2-base-ft', 'paddleocr/pp-ocrv5', 'qwen/qwen3.5-0.8b', 'rednote-hilab/dots.ocr', 'roboflow/rfdetr-nano', 'roboflow/rfdetr-seg-nano', 'usyd-community/vitpose-plus-small', 'vikhyatk/moondream2']\", 'type': 'model_not_found', 'code': None, 'param': None}}}]"}]
688ms • 38.2 KB • 55.5 KB/s
```
882ms • 38.2 KB • 43.3 KB/s

╭────────────┬──────────────┬───────────────────────────────────────────────────┬──────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model        │ Base Command                                      │ Extra Args                           │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────┼───────────────────────────────────────────────────┼──────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ noop       │ vlm-run/noop │ mm cat <img> --mode fast --no-cache --format json │ --encode.strategy_opts max_width=512 │ 824ms │ 41.2ms │ 776ms │ 852ms │ 1.21x │  0.0 │ 8.95 Mbps │
╰────────────┴──────────────┴───────────────────────────────────────────────────┴──────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Error code: 404 - {'detail': {'error': {'message': \"Model 'vlm-run/noop' not found. Available: ['Qwen/Qwen3.5-0.8B', 'facebook/sam3', 'fastino/gliner2-multi-v1', 'ggml-org/SmolVLM-256M-Instruct-GGUF', 'ggml-org/SmolVLM2-256M-Video-Instruct-GGUF', 'ggml-org/SmolVLM2-500M-Video-Instruct-GGUF', 'ggml-org/smolvlm-256m-instruct-gguf', 'ggml-org/smolvlm2-256m-video-instruct-gguf', 'ggml-org/smolvlm2-500m-video-instruct-gguf', 'microsoft/Florence-2-base-ft', 'microsoft/florence-2-base-ft', 'paddleocr/pp-ocrv5', 'qwen/qwen3.5-0.8b', 'rednote-hilab/dots.ocr', 'roboflow/rfdetr-nano', 'roboflow/rfdetr-seg-nano', 'usyd-community/vitpose-plus-small', 'vikhyatk/moondream2']\", 'type': 'model_not_found', 'code': None, 'param': None}}}]"}]
628ms • 38.2 KB • 60.7 KB/s
```
776ms • 38.2 KB • 49.2 KB/s

╭────────────┬──────────────┬───────────────────────────────────────────────────┬───────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model        │ Base Command                                      │ Extra Args                            │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────┼───────────────────────────────────────────────────┼───────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ noop       │ vlm-run/noop │ mm cat <img> --mode fast --no-cache --format json │ --encode.strategy_opts max_width=1024 │ 812ms │ 16.9ms │ 798ms │ 831ms │ 1.23x │  0.0 │ 9.08 Mbps │
╰────────────┴──────────────┴───────────────────────────────────────────────────┴───────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Error code: 404 - {'detail': {'error': {'message': \"Model 'vlm-run/noop' not found. Available: ['Qwen/Qwen3.5-0.8B', 'facebook/sam3', 'fastino/gliner2-multi-v1', 'ggml-org/SmolVLM-256M-Instruct-GGUF', 'ggml-org/SmolVLM2-256M-Video-Instruct-GGUF', 'ggml-org/SmolVLM2-500M-Video-Instruct-GGUF', 'ggml-org/smolvlm-256m-instruct-gguf', 'ggml-org/smolvlm2-256m-video-instruct-gguf', 'ggml-org/smolvlm2-500m-video-instruct-gguf', 'microsoft/Florence-2-base-ft', 'microsoft/florence-2-base-ft', 'paddleocr/pp-ocrv5', 'qwen/qwen3.5-0.8b', 'rednote-hilab/dots.ocr', 'roboflow/rfdetr-nano', 'roboflow/rfdetr-seg-nano', 'usyd-community/vitpose-plus-small', 'vikhyatk/moondream2']\", 'type': 'model_not_found', 'code': None, 'param': None}}}]"}]
673ms • 38.2 KB • 56.7 KB/s
```
831ms • 38.2 KB • 45.9 KB/s

╭────────────┬──────────────────────────────┬───────────────────────────────────────────────────┬──────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                        │ Base Command                                      │ Extra Args                                   │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────────────────────┼───────────────────────────────────────────────────┼──────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ microsoft/florence-2-base-ft │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"caption"}' │ 2.04s │ 29.5ms │ 2.01s │ 2.06s │ 0.49x │  0.0 │ 3.61 Mbps │
╰────────────┴──────────────────────────────┴───────────────────────────────────────────────────┴──────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "{\n  \"<CAPTION>\": \"A small green car parked in front of a building.\"\n}"}]
1.9s • 38.2 KB • 20.5 KB/s
```
2.06s • 38.2 KB • 18.5 KB/s

╭────────────┬──────────────────────────────┬───────────────────────────────────────────────────┬──────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                        │ Base Command                                      │ Extra Args                               │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────────────────────┼───────────────────────────────────────────────────┼──────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ microsoft/florence-2-base-ft │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"ocr"}' │ 1.97s │ 29.7ms │ 1.94s │ 2.00s │ 0.51x │  0.0 │ 3.73 Mbps │
╰────────────┴──────────────────────────────┴───────────────────────────────────────────────────┴──────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "{\n  \"<OCR>\": \"0\"\n}"}]
1.7s • 38.2 KB • 22.0 KB/s
```
1.94s • 38.2 KB • 19.7 KB/s

╭────────────┬──────────────────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                        │ Base Command                                      │ Extra Args                              │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ microsoft/florence-2-base-ft │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"od"}' │ 2.12s │ 65.1ms │ 2.06s │ 2.19s │ 0.47x │  0.0 │ 3.47 Mbps │
╰────────────┴──────────────────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "{\n  \"<OD>\": {\n    \"bboxes\": [\n      [\n        27.904001235961914,\n        129.21600341796875,\n        477.4400329589844,\n        296.2560119628906\n      ]\n    ],\n    \"labels\": [\n      \"car\"\n    ]\n  }\n}"}]
1.9s • 38.2 KB • 20.2 KB/s
```
2.12s • 38.2 KB • 18.0 KB/s

╭────────────┬─────────────────────┬───────────────────────────────────────────────────┬──────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model               │ Base Command                                      │ Extra Args                                   │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼─────────────────────┼───────────────────────────────────────────────────┼──────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ vikhyatk/moondream2 │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"caption"}' │ 4.81s │ 167ms │ 4.66s │ 4.99s │ 0.21x │  0.0 │ 1.53 Mbps │
╰────────────┴─────────────────────┴───────────────────────────────────────────────────┴──────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "A vintage light blue Volkswagen Beetle is parked parallel to a yellow building with a wooden door. The car's roof and side panels are a light green/teal color. The building features a wooden door and two arched windows/doorways. The car has silver hubcaps and a small antenna on top. The ground is made of gray/light brown paving stones."}]
4.5s • 38.2 KB • 8.4 KB/s
```
4.78s • 38.2 KB • 8.0 KB/s

╭────────────┬─────────────────────┬───────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model               │ Base Command                                      │ Extra Args                                                                     │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼─────────────────────┼───────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ vikhyatk/moondream2 │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"detect","method_params":{"object":"bench"}}' │ 3.31s │ 53.7ms │ 3.26s │ 3.37s │ 0.30x │  0.0 │ 2.22 Mbps │
╰────────────┴─────────────────────┴───────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "{\n  \"objects\": []\n}"}]
3.1s • 38.2 KB • 12.2 KB/s
```
3.37s • 38.2 KB • 11.3 KB/s

╭────────────┬─────────────────────┬───────────────────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model               │ Base Command                                      │ Extra Args                                                                                │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼─────────────────────┼───────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼────────────┤
│ model      │ vikhyatk/moondream2 │ mm cat <vid> --mode fast --no-cache --format json │ --generate.extra-body                                                                     │ 2.42s │ 171ms │ 2.28s │ 2.61s │  104x │ 11.6 │ 55.38 Gbps │
│            │                     │                                                   │ '{"video_fps":0.4,"video_max_frames":8,"video_resolution":"448x336","method":"caption"}'  │       │       │       │       │       │      │            │
╰────────────┴─────────────────────┴───────────────────────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴────────────╯
args: {"vid": "bakery.mp4", "mode": "fast"}
```json
[{"path": "bakery.mp4", "mode": "fast", "content": "[LLM error: Error code: 400 - {'detail': {'error': {'message': \"Model 'vikhyatk/moondream2' accepts at most 1 image_url part(s); got 5.  Use qwen/qwen3.5-0.8b for multi-image inference.\", 'type': 'invalid_request_error', 'code': 'capability_violation', 'param': 'messages.content.image_url'}}}]"}]
2.4s • 28.0 MB • 11.5 MB/s
```
2.61s • 28.0 MB • 10.7 MB/s

╭────────────┬───────────────────┬───────────────────────────────────────────────────┬────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model             │ Base Command                                      │ Extra Args                                 │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼───────────────────┼───────────────────────────────────────────────────┼────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ qwen/qwen3.5-0.8b │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'What is 2+2? Reply in one word.' │ 3.02s │ 52.3ms │ 2.96s │ 3.06s │ 0.33x │  0.0 │ 2.44 Mbps │
╰────────────┴───────────────────┴───────────────────────────────────────────────────┴────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "Two."}]
2.8s • 38.2 KB • 13.7 KB/s
```
3.03s • 38.2 KB • 12.6 KB/s

╭────────────┬───────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model             │ Base Command                                      │ Extra Args                              │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼───────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ qwen/qwen3.5-0.8b │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'Describe this image briefly.' │ 3.65s │ 49.2ms │ 3.62s │ 3.71s │ 0.27x │  0.0 │ 2.02 Mbps │
╰────────────┴───────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "This image captures a charming, vintage scene featuring a classic Volkswagen Beetle, painted in a soft, mint-green hue with a white stripe running down its center. The car is parked on a paved street, angled slightly to the left, showcasing its rounded, bulbous body and distinctive round headlights. The wheels are fitted with chrome hubcaps and black tires, adding a touch of retro charm.\n\nThe background consists of a weathered, yellowish wall with two wooden doors set into it. The left door has a simple arched top, while the right door features a more ornate, multi-pane design. The setting appears to be an urban or suburban street, with a textured, light-colored pavement beneath the vehicle. The overall composition is clean and well-lit, emphasizing the car's retro aesthetic against the slightly aged backdrop."}]
3.5s • 38.2 KB • 11.0 KB/s
```
3.71s • 38.2 KB • 10.3 KB/s

╭────────────┬───────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model             │ Base Command                                      │ Extra Args                                                                                  │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼────────────┤
│ model      │ qwen/qwen3.5-0.8b │ mm cat <vid> --mode fast --no-cache --format json │ --prompt 'Summarise what happens in this video in one sentence.' --generate.extra-body      │ 6.13s │ 257ms │ 5.95s │ 6.43s │ 41.2x │  4.6 │ 21.84 Gbps │
│            │                   │                                                   │ '{"video_fps":0.4,"video_max_frames":8,"video_resolution":"448x336"}'                       │       │       │       │       │       │      │            │
╰────────────┴───────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴────────────╯
args: {"vid": "bakery.mp4", "mode": "fast"}
```json
[{"path": "bakery.mp4", "mode": "fast", "content": "Based on the visual evidence across the five images, here is the summary of the video:\n\nThe video chronicles the history of a bakery in a fictional setting, likely based on the real-world history of the \"Baker's House\" bakery in the fictional town of McKees Rocks, Pennsylvania.\n\nThe narrative unfolds in three distinct phases:\n1.  **The Past:** The video begins with a montage of historical photographs and archival footage, showing the bakery's origins, its location, and its past history. It includes scenes of the bakery's exterior, interior, and historical figures, establishing its legacy.\n2.  **The Present:** The video then transitions to the current state of the bakery, showcasing a modern, well-lit, and organized facility. It features contemporary employees in white uniforms and hairnets, working alongside modern technology like computers and digital displays.\n3.  **The Future:** The final segment shows the bakery in a state of transition or expansion, with workers actively working on new products and equipment. A Google logo appears, suggesting a digital or technological integration into the business's future.\n\nIn summary, the video presents a journey from the historical roots of the bakery to its present-day operations and future outlook."}]
6.2s • 28.0 MB • 4.5 MB/s
```
6.43s • 28.0 MB • 4.4 MB/s

╭────────────┬──────────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                │ Base Command                                      │ Extra Args                                  │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ roboflow/rfdetr-nano │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"detect"}' │ 1.95s │ 53.2ms │ 1.90s │ 2.00s │ 0.51x │  0.0 │ 3.78 Mbps │
╰────────────┴──────────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "{\n  \"detections\": [\n    {\n      \"bbox_xyxy\": [\n        30.117935180664062,\n        128.95452880859375,\n        465.9937744140625,\n        297.7081604003906\n      ],\n      \"label\": \"car\",\n      \"confidence\": 0.9582,\n      \"class_id\": 3\n    }\n  ],\n  \"count\": 1\n}"}]
1.8s • 38.2 KB • 21.8 KB/s
```
2.00s • 38.2 KB • 19.1 KB/s

╭────────────┬──────────────────────────┬───────────────────────────────────────────────────┬──────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                    │ Base Command                                      │ Extra Args                                   │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────────────────┼───────────────────────────────────────────────────┼──────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ roboflow/rfdetr-seg-nano │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"segment"}' │ 2.07s │ 54.6ms │ 2.01s │ 2.11s │ 0.48x │  0.0 │ 3.56 Mbps │
╰────────────┴──────────────────────────┴───────────────────────────────────────────────────┴──────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "{\n  \"detections\": [\n    {\n      \"bbox_xyxy\": [\n        29.113189697265625,\n        129.516845703125,\n        466.54302978515625,\n        297.9302978515625\n      ],\n      \"label\": \"car\",\n      \"confidence\": 0.9626,\n      \"class_id\": 3,\n      \"mask_png\": \"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAgAAAAGACAAAAAD+S4VjAAAF9ElEQVR4nO3dy3LbOBAFUHgq///LmcXY5UlFFkmwAXSD56yysCWg7yVEy4+0BgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACwzMfqBcT7ffLjNtx6h02mcDb09zYZxiWV9xyT+g8qD+aKkvscmvyfSs7nimobnJj9l2ojuqbS7haE/6XSmK6psrOF4X+qMqmLKmxrffj/qTCry9JvKkv6rbUC07ou+ZZSxd/Sj6tD5h1lS7+13PPqknZDGdNvLfHAOiXdT9b4W9qJ9fq1egEvJE5/P/+sXsDfkueffHlXpTvQCsw33czuSLaZAvG3dEO7JdVeasTfkk3tnkQ3gWXi30qem8BK+Vda64EsJ8BGI60lyQlQLf9q6/1ZituZiuNMMbgAGU6AivlvI0EBauZfc9V/W1+AXSZZ1OqXssLxrx5djMUnQOH8S6/929oC7DHD0pYWoHj+xZf/n5UF2GKA1S0sQP386+9g4a3sDsPb4SuBVSfAHvlvYFEBdsm//j7WFKD+3L6U38mSApSf2kYW3MVsFn/x+8D5J8Bm+Vffz/QCFJ/XC7V3NLsAtaf1Wuk9zX0FKz2qNwrfB0xd+q75t8IVmLnwjfNvZSswb9l7x99a0QpMW/T++X8qVoNJy31M/F/K1GDOQh+X/7fsTZixvgfH/4NErZiwFPn/IEUNxi9C/u8trsHopxf/GQtLMPip5X/aohKMfVr5X7OgBEOfUv4dJpdg5NPJv9PMDgx8LvnfMasE455H/ndN6cCoJxF/hAkVGPQU8g8yvAJjnkD+gcZ2YMijyz/WyAqs/yNRHPo98IoaUS4HwACjToEBjyv/McZUIP5R5T/MiAqEP6b8R4qvQPQjyn+w6MCCH0/+48VGFvto8p8iMrTQAsh/lrjYIgsg/5mCkosrgPhnC8kurADyXyAgvagCyH+N2/kFFUD+y9xMMKYA8l/pVoYh3w6W/1K3xh9xAsh/uf4YA04A+a/Xn8HtE0D8OfQGefcEkH8SvUHcLID80+iM4l4B5F/erQLIP5O+NO4UQP4buFEA+e+gvwDyz6YrEb8Z9HDdBXAA7MEJ8HAK8HC9BfAKsAknwEZ6rkoFeDgFeDgFeDgFeLjOAvgiYBdOgJ10XJcK8HAK8HB9BXALsA0nwFauX5ldBXAA7MMJ8HA9BXAA5HU5m44CyH8n1wsg/61c/J1C6ad3MdFfFz5W+hs6WwDhb+pcAcS/rTMFEP/Gjgsg/q0dfhko/70dFUD+xVz9W0EHBZD/7nwz6OEU4OEU4OEUYC+X/16kAjzcQQGG//f1LOYE2Mr1C/aoAFce0XGx2EdHAk6AfXRdgMefdPrNwA9vHK7Uef5e+YmgIQvgtluTP/HJ5y7rj/MfSpzbl13QCeDyX+P+3EMKIP5FAgZ/4quAw2f5ePEvJogY9/0TQOilnXkf4F3EPe89ECNk9KdOgI8fbu+FX9/Jl4AXFZD+Fi7E+F2BN5/knYBpYq7ACzeBLvkdxb0VPM+7JiY+gXJ+r6RSAc4cQUOPqa78kh+c4csLLnny8b3e78+LDpxO0GSSFyB9/p9O3SD/+YF3BY0m9UtAlfi/X9/rrPhL/IrTdXya32cWHDWeqOEk/pGwavnXW3BrIwoQNYaS4zyWbVtpT4BsgwoTs7Gw8QwowLbRBck1n6wnQK4pxQrYW9x4RhQg1QZ5L+sJsLXb9Q68PoYUINMGU7q5v8jxjDkBEm1wQ6HjyfgS8ID882xxUAHubDDPcAa6scnY+Qybdvd73o/Iv7XuCQXPZ9hLQO86H5N/506j5zPuHiDH/jLr2Wv4fHL9CNWT4m+tXZ7QgPmMHfm1/T0u/nZxQiMGNHroFzb4xPzbtb/AMsDwqZ/d30Pjb62dnNGgAU2Y+/H2nhz+p4MhjZvQnNm/2Z7w/+flnMZOaN78/XYpAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPn8C4/epSjmC2VnAAAAAElFTkSuQmCC\"\n    }\n  ],\n  \"count\": 1\n}"}]
1.8s • 38.2 KB • 21.2 KB/s
```
2.01s • 38.2 KB • 19.0 KB/s

╭────────────┬───────────────────────────────────┬───────────────────────────────────────────────────┬───────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                             │ Base Command                                      │ Extra Args                                │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼───────────────────────────────────┼───────────────────────────────────────────────────┼───────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ usyd-community/vitpose-plus-small │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"pose"}' │ 1.97s │ 11.7ms │ 1.96s │ 1.98s │ 0.51x │  0.0 │ 3.74 Mbps │
╰────────────┴───────────────────────────────────┴───────────────────────────────────────────────────┴───────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "{\n  \"persons\": [],\n  \"person_count\": 0\n}"}]
1.7s • 38.2 KB • 22.1 KB/s
```
1.98s • 38.2 KB • 19.3 KB/s

╭────────────┬───────────────┬───────────────────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model         │ Base Command                                      │ Extra Args                                                                            │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼───────────────┼───────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ facebook/sam3 │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"segment","method_params":{"prompt":"soccer ball"}}' │ 2.74s │ 119ms │ 2.64s │ 2.87s │ 0.37x │  0.0 │ 2.69 Mbps │
╰────────────┴───────────────┴───────────────────────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Deployment(name='sam3', app='default') is unavailable because it failed to deploy.]"}]
2.7s • 38.2 KB • 14.0 KB/s
```
2.87s • 38.2 KB • 13.3 KB/s

╭────────────┬───────────────┬───────────────────────────────────────────────────┬──────────────────────────────────────────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model         │ Base Command                                      │ Extra Args                                                                               │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼───────────────┼───────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ facebook/sam3 │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"segment_box","method_params":{"box":[50,50,400,400]}}' │ 2.80s │ 68.0ms │ 2.72s │ 2.85s │ 0.36x │  0.0 │ 2.64 Mbps │
╰────────────┴───────────────┴───────────────────────────────────────────────────┴──────────────────────────────────────────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Deployment(name='sam3', app='default') is unavailable because it failed to deploy.]"}]
2.7s • 38.2 KB • 14.1 KB/s
```
2.85s • 38.2 KB • 13.4 KB/s

╭────────────┬───────────────┬───────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model         │ Base Command                                      │ Extra Args                                                                                     │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────┼───────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼────────────┤
│ model      │ facebook/sam3 │ mm cat <vid> --mode fast --no-cache --format json │ --generate.extra-body                                                                          │ 2.21s │ 22.1ms │ 2.19s │ 2.23s │  114x │ 12.7 │ 60.65 Gbps │
│            │               │                                                   │ '{"video_fps":2.0,"video_max_frames":30,"method":"track","method_params":{"prompt":"soccer     │       │        │       │       │       │      │            │
│            │               │                                                   │ ball","skip":1,"max_frames":30}}'                                                              │       │        │       │       │       │      │            │
╰────────────┴───────────────┴───────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴────────────╯
args: {"vid": "bakery.mp4", "mode": "fast"}
```json
[{"path": "bakery.mp4", "mode": "fast", "content": "[LLM error: Error code: 400 - {'detail': {'error': {'message': \"Model 'facebook/sam3' accepts at most 1 image_url part(s); got 5.  Use qwen/qwen3.5-0.8b for multi-image inference.\", 'type': 'invalid_request_error', 'code': 'capability_violation', 'param': 'messages.content.image_url'}}}]"}]
2.1s • 28.0 MB • 13.6 MB/s
```
2.23s • 28.0 MB • 12.5 MB/s

╭────────────┬────────────────────────┬───────────────────────────────────────────────────┬───────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                  │ Base Command                                      │ Extra Args                                        │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼────────────────────────┼───────────────────────────────────────────────────┼───────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ rednote-hilab/dots.ocr │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"parse_layout"}' │ 2.82s │ 38.7ms │ 2.79s │ 2.86s │ 0.35x │  0.0 │ 2.61 Mbps │
╰────────────┴────────────────────────┴───────────────────────────────────────────────────┴───────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Deployment(name='dots_ocr', app='default') is unavailable because it failed to deploy.]"}]
2.6s • 38.2 KB • 14.4 KB/s
```
2.81s • 38.2 KB • 13.6 KB/s

╭────────────┬────────────────────────┬───────────────────────────────────────────────────┬────────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                  │ Base Command                                      │ Extra Args                                             │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼────────────────────────┼───────────────────────────────────────────────────┼────────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ rednote-hilab/dots.ocr │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"parse_layout_only"}' │ 2.69s │ 67.8ms │ 2.62s │ 2.76s │ 0.37x │  0.0 │ 2.74 Mbps │
╰────────────┴────────────────────────┴───────────────────────────────────────────────────┴────────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Deployment(name='dots_ocr', app='default') is unavailable because it failed to deploy.]"}]
2.6s • 38.2 KB • 14.6 KB/s
```
2.76s • 38.2 KB • 13.8 KB/s

╭────────────┬────────────────────────┬───────────────────────────────────────────────────┬──────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                  │ Base Command                                      │ Extra Args                               │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼────────────────────────┼───────────────────────────────────────────────────┼──────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ rednote-hilab/dots.ocr │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"ocr"}' │ 2.81s │ 27.0ms │ 2.80s │ 2.84s │ 0.36x │  0.0 │ 2.62 Mbps │
╰────────────┴────────────────────────┴───────────────────────────────────────────────────┴──────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Deployment(name='dots_ocr', app='default') is unavailable because it failed to deploy.]"}]
2.7s • 38.2 KB • 14.1 KB/s
```
2.84s • 38.2 KB • 13.4 KB/s

╭────────────┬────────────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                  │ Base Command                                      │ Extra Args                                                                              │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼────────────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ rednote-hilab/dots.ocr │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body                                                                   │ 2.75s │ 132ms │ 2.60s │ 2.85s │ 0.36x │  0.0 │ 2.68 Mbps │
│            │                        │                                                   │ '{"method":"grounding_ocr","method_params":{"box":[120,200,900,400]}}'                  │       │       │       │       │       │      │           │
╰────────────┴────────────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Deployment(name='dots_ocr', app='default') is unavailable because it failed to deploy.]"}]
2.7s • 38.2 KB • 14.1 KB/s
```
2.85s • 38.2 KB • 13.4 KB/s

╭────────────┬────────────────────┬───────────────────────────────────────────────────┬──────────────────────────────────────────┬────────┬───────┬────────┬────────┬───────┬──────┬─────────────╮
│ Group      │ Model              │ Base Command                                      │ Extra Args                               │   Mean │  ±Std │    Min │    Max │ Speed │ MB/s │         bps │
├────────────┼────────────────────┼───────────────────────────────────────────────────┼──────────────────────────────────────────┼────────┼───────┼────────┼────────┼───────┼──────┼─────────────┤
│ model      │ paddleocr/pp-ocrv5 │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"ocr"}' │ 33.85s │ 126ms │ 33.78s │ 34.00s │ 0.03x │  0.0 │ 217.80 kbps │
╰────────────┴────────────────────┴───────────────────────────────────────────────────┴──────────────────────────────────────────┴────────┴───────┴────────┴────────┴───────┴──────┴─────────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Internal Server Error]"}]
33.6s • 38.2 KB • 1.1 KB/s
```
33.78s • 38.2 KB • 1.1 KB/s

╭────────────┬────────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────┬────────┬────────┬────────┬────────┬───────┬──────┬─────────────╮
│ Group      │ Model              │ Base Command                                      │ Extra Args                                  │   Mean │   ±Std │    Min │    Max │ Speed │ MB/s │         bps │
├────────────┼────────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────┼────────┼────────┼────────┼────────┼───────┼──────┼─────────────┤
│ model      │ paddleocr/pp-ocrv5 │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"detect"}' │ 33.77s │ 35.0ms │ 33.73s │ 33.80s │ 0.03x │  0.0 │ 218.35 kbps │
╰────────────┴────────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────┴────────┴────────┴────────┴────────┴───────┴──────┴─────────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Internal Server Error]"}]
33.6s • 38.2 KB • 1.1 KB/s
```
33.80s • 38.2 KB • 1.1 KB/s

╭────────────┬──────────────────────────┬───────────────────────────────────────────────────┬──────────────────────────────────────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                    │ Base Command                                      │ Extra Args                                                                           │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────────────────┼───────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ fastino/gliner2-multi-v1 │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'Vlm Run is hiring engineers in San Francisco.' --generate.extra-body       │ 851ms │ 40.2ms │ 815ms │ 895ms │ 1.17x │  0.0 │ 8.66 Mbps │
│            │                          │                                                   │ '{"method":"extract_entities"}'                                                      │       │        │       │       │       │      │           │
╰────────────┴──────────────────────────┴───────────────────────────────────────────────────┴──────────────────────────────────────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Error code: 400 - {'detail': {'error': {'message': \"Model 'fastino/gliner2-multi-v1' is text-only and does not accept image inputs.\", 'type': 'invalid_request_error', 'code': 'capability_violation', 'param': 'messages.content.image_url'}}}]"}]
631ms • 38.2 KB • 60.5 KB/s
```
815ms • 38.2 KB • 46.8 KB/s

╭────────────┬──────────────────────────┬───────────────────────────────────────────────────┬──────────────────────────────────────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                    │ Base Command                                      │ Extra Args                                                                           │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────────────────┼───────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ fastino/gliner2-multi-v1 │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'The fourth quarter earnings exceeded analyst expectations.'                │ 798ms │ 26.8ms │ 767ms │ 816ms │ 1.25x │  0.0 │ 9.24 Mbps │
│            │                          │                                                   │ --generate.extra-body '{"method":"classify_text"}'                                   │       │        │       │       │       │      │           │
╰────────────┴──────────────────────────┴───────────────────────────────────────────────────┴──────────────────────────────────────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Error code: 400 - {'detail': {'error': {'message': \"Model 'fastino/gliner2-multi-v1' is text-only and does not accept image inputs.\", 'type': 'invalid_request_error', 'code': 'capability_violation', 'param': 'messages.content.image_url'}}}]"}]
632ms • 38.2 KB • 60.4 KB/s
```
816ms • 38.2 KB • 46.8 KB/s

╭────────────┬─────────────────────────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                               │ Base Command                                      │ Extra Args                              │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼─────────────────────────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ ggml-org/smolvlm-256m-instruct-gguf │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'Describe this image briefly.' │ 2.60s │ 75.8ms │ 2.51s │ 2.65s │ 0.38x │  0.0 │ 2.83 Mbps │
╰────────────┴─────────────────────────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "The image depicts a blue vintage car parked on a paved road in front of a beige wall. The car is painted in a bright, pastel blue color, which stands out against the darker background of the wall. The car has a sleek, aerodynamic design, with a streamlined body and a rounded front end. The tires are large and have a smooth tread, which helps to reduce the risk of damage to the car's wheels. The car is parked facing the camera, and its front end is visible, indicating that it is in good condition.\n\nThe wall behind the car is made of a light-colored material, possibly beige or off-white, and has a simple, clean appearance. The wall has a few wooden doors, which are dark brown in color, and they are evenly spaced. The doors are closed, and there are no visible signs of damage or wear.\n\nThe ground in front of the car is paved, and it appears to be made of concrete or a similar material. The pavement is clean and well-maintained, and there are no visible signs of wear or damage.\n\nThe image is taken from a slightly low angle, which makes the car appear larger and more imposing. The lighting in the image is natural, coming"}]
2.4s • 38.2 KB • 16.1 KB/s
```
2.64s • 38.2 KB • 14.5 KB/s

╭────────────┬────────────────────────────────────────────┬───────────────────────────────────────────────────┬───────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                                      │ Base Command                                      │ Extra Args                        │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼────────────────────────────────────────────┼───────────────────────────────────────────────────┼───────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ ggml-org/smolvlm2-256m-video-instruct-gguf │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'What is in this image?' │ 2.26s │ 16.6ms │ 2.25s │ 2.28s │ 0.44x │  0.0 │ 3.27 Mbps │
╰────────────┴────────────────────────────────────────────┴───────────────────────────────────────────────────┴───────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "The image depicts a vintage car parked on a street, with a yellow building in the background. The car is a light blue color, and it has a distinctive design with a rounded front end and a long hood. The car is parked on the side of the street, and there are no people or other vehicles in the scene. The building in the background is a simple, one-story structure with a wooden door and a window. The car is positioned in the center of the image, and it is facing the camera."}]
2.0s • 38.2 KB • 18.9 KB/s
```
2.25s • 38.2 KB • 17.0 KB/s

╭────────────┬────────────────────────────────────────────┬───────────────────────────────────────────────────┬───────────────────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model                                      │ Base Command                                      │ Extra Args                                                        │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼────────────────────────────────────────────┼───────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼────────────┤
│ model      │ ggml-org/smolvlm2-256m-video-instruct-gguf │ mm cat <vid> --mode fast --no-cache --format json │ --prompt 'Summarise the video in one sentence.'                   │ 2.22s │ 71.4ms │ 2.15s │ 2.29s │  114x │ 12.6 │ 60.45 Gbps │
│            │                                            │                                                   │ --generate.extra-body                                             │       │        │       │       │       │      │            │
│            │                                            │                                                   │ '{"video_fps":0.4,"video_max_frames":8,"video_resolution":"448x33 │       │        │       │       │       │      │            │
│            │                                            │                                                   │ 6"}'                                                              │       │        │       │       │       │      │            │
╰────────────┴────────────────────────────────────────────┴───────────────────────────────────────────────────┴───────────────────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴────────────╯
args: {"vid": "bakery.mp4", "mode": "fast"}
```json
[{"path": "bakery.mp4", "mode": "fast", "content": "[LLM error: Error code: 400 - {'detail': {'error': {'message': \"Model 'ggml-org/smolvlm2-256m-video-instruct-gguf' accepts at most 1 image_url part(s); got 5.  Use qwen/qwen3.5-0.8b for multi-image inference.\", 'type': 'invalid_request_error', 'code': 'capability_violation', 'param': 'messages.content.image_url'}}}]"}]
2.1s • 28.0 MB • 13.1 MB/s
```
2.29s • 28.0 MB • 12.2 MB/s

╭────────────┬────────────────────────────────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                                      │ Base Command                                      │ Extra Args                              │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼────────────────────────────────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ ggml-org/smolvlm2-500m-video-instruct-gguf │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'Describe this image briefly.' │ 2.36s │ 10.2ms │ 2.35s │ 2.37s │ 0.42x │  0.0 │ 3.12 Mbps │
╰────────────┴────────────────────────────────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "The image captures a classic Volkswagen Beetle, a renowned car model, parked on a cobblestone street. The car, painted in a light blue hue, is adorned with white-wall tires and a white roof. The building behind the car is painted in a light yellow color, contrasting with the blue of the car. The building's facade is adorned with a wooden door and a window, adding a touch of rustic charm to the scene. The car is facing towards the right side of the image, as if ready to embark on a journey."}]
2.1s • 38.2 KB • 18.3 KB/s
```
2.35s • 38.2 KB • 16.3 KB/s

╭────────────┬────────────────────────────────────────────┬───────────────────────────────────────────────────┬───────────────────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model                                      │ Base Command                                      │ Extra Args                                                        │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼────────────────────────────────────────────┼───────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼────────────┤
│ model      │ ggml-org/smolvlm2-500m-video-instruct-gguf │ mm cat <vid> --mode fast --no-cache --format json │ --prompt 'Summarise the video in one sentence.'                   │ 2.32s │ 60.8ms │ 2.27s │ 2.39s │  109x │ 12.0 │ 57.70 Gbps │
│            │                                            │                                                   │ --generate.extra-body                                             │       │        │       │       │       │      │            │
│            │                                            │                                                   │ '{"video_fps":0.4,"video_max_frames":8,"video_resolution":"448x33 │       │        │       │       │       │      │            │
│            │                                            │                                                   │ 6"}'                                                              │       │        │       │       │       │      │            │
╰────────────┴────────────────────────────────────────────┴───────────────────────────────────────────────────┴───────────────────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴────────────╯
args: {"vid": "bakery.mp4", "mode": "fast"}
```json
[{"path": "bakery.mp4", "mode": "fast", "content": "[LLM error: Error code: 400 - {'detail': {'error': {'message': \"Model 'ggml-org/smolvlm2-500m-video-instruct-gguf' accepts at most 1 image_url part(s); got 5.  Use qwen/qwen3.5-0.8b for multi-image inference.\", 'type': 'invalid_request_error', 'code': 'capability_violation', 'param': 'messages.content.image_url'}}}]"}]
2.1s • 28.0 MB • 13.2 MB/s
```
2.31s • 28.0 MB • 12.1 MB/s

╭────────────┬─────────────────────┬───────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model               │ Base Command                                      │ Extra Args                                                             │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼─────────────────────┼───────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼───────────┤
│ model+llm  │ vikhyatk/moondream2 │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"caption","llm":"qwen/qwen3.5-0.8b"}' │ 2.76s │ 122ms │ 2.68s │ 2.90s │ 0.36x │  0.0 │ 2.67 Mbps │
╰────────────┴─────────────────────┴───────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Internal Server Error]"}]
2.5s • 38.2 KB • 15.0 KB/s
```
2.68s • 38.2 KB • 14.2 KB/s

╭────────────┬───────────────────┬─────────────────────────────────────────┬──────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model             │ Base Command                            │ Extra Args                           │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────────┼─────────────────────────────────────────┼──────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼────────────┤
│ model      │ qwen/qwen3.5-0.8b │ python _multi_image_call.py <img> <img> │ --prompt 'Compare these two images.' │ 3.35s │ 7.39ms │ 3.34s │ 3.36s │ 0.60x │  0.1 │ 18.58 Mbps │
╰────────────┴───────────────────┴─────────────────────────────────────────┴──────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴────────────╯
args: {"img": ["1-vqa-car.jpg", "invoice.jpg"]}
```text
<think>
The user wants a comparison between two images.
**Image 1 Analysis:**
- **Subject:** A vintage teal Volkswagen Beetle parked on a paved street.
- **Setting:** A yellow stucco wall with two wooden doors (one double, one single) and a white frame.
- **Details:** The car has chrome bumpers and hubcaps. The paint is a light, minty green. The background is slightly weathered.
- **Vibe:** Classic, nostalgic, urban, slightly rustic.

**Image 2 Analysis:**
- **Subject:** A Google Invoice.
- **Header
```
3.34s • 182.1 KB • 54.5 KB/s

╭────────────┬───────────────────┬───────────────────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model             │ Base Command                                      │ Extra Args                                                                        │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼───────────────────┼───────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼───────────┤
│ image-res  │ qwen/qwen3.5-0.8b │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'Describe the image in 1 sentence.' --encode.strategy_opts max_width=512 │ 3.20s │ 472ms │ 2.90s │ 3.75s │ 0.31x │  0.0 │ 2.30 Mbps │
╰────────────┴───────────────────┴───────────────────────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "This image captures a vintage teal Volkswagen Beetle parked on a cobblestone street in front of a weathered yellow wall with two wooden doors."}]
3.5s • 38.2 KB • 10.8 KB/s
```
3.75s • 38.2 KB • 10.2 KB/s

╭────────────┬───────────────────┬───────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model             │ Base Command                                      │ Extra Args                                                                         │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼───────────────────┼───────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ image-res  │ qwen/qwen3.5-0.8b │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'Describe the image in 1 sentence.' --encode.strategy_opts max_width=1024 │ 3.11s │ 67.7ms │ 3.04s │ 3.17s │ 0.32x │  0.0 │ 2.37 Mbps │
╰────────────┴───────────────────┴───────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "This image captures a classic Volkswagen Beetle parked in front of a weathered, yellow-stucco building with two wooden doors. The car, painted in a soft mint green, is positioned on a paved street, its chrome hubcaps and rounded body reflecting the ambient light."}]
3.0s • 38.2 KB • 12.8 KB/s
```
3.17s • 38.2 KB • 12.0 KB/s

╭────────────┬───────────────────┬───────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model             │ Base Command                                      │ Extra Args                                                                         │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼───────────────────┼───────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼───────────┤
│ image-res  │ qwen/qwen3.5-0.8b │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'Describe the image in 1 sentence.' --encode.strategy_opts max_width=1536 │ 3.39s │ 313ms │ 3.20s │ 3.75s │ 0.30x │  0.0 │ 2.18 Mbps │
╰────────────┴───────────────────┴───────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "This image captures a classic Volkswagen Beetle parked on a paved street in front of a weathered, yellow-stucco building with two wooden doors. The car, painted in a soft mint green, stands out against the muted tones of the wall and the surrounding environment."}]
3.0s • 38.2 KB • 12.7 KB/s
```
3.20s • 38.2 KB • 11.9 KB/s

╭────────────┬───────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model             │ Base Command                                      │ Extra Args                                                                                  │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼────────────┤
│ video-fra… │ qwen/qwen3.5-0.8b │ mm cat <vid> --mode fast --no-cache --format json │ --prompt 'Summarise what happens in this video in one sentence.' --generate.extra-body      │ 5.77s │ 125ms │ 5.67s │ 5.91s │ 43.8x │  4.9 │ 23.24 Gbps │
│            │                   │                                                   │ '{"video_fps":0.5,"video_max_frames":4}'                                                    │       │       │       │       │       │      │            │
╰────────────┴───────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴────────────╯
args: {"vid": "bakery.mp4", "mode": "fast"}
```json
[{"path": "bakery.mp4", "mode": "fast", "content": "Based on the visual evidence across the five images, here is the summary of the video's content:\n\nThe video is a montage of scenes from a bakery, focusing on its history, operations, and community. It begins with a collage of historical photos showing the bakery's past, including its location in the city of Baken, its fire damage, and its founding. The video then transitions to a modern, contemporary view of the bakery's interior, where staff in white uniforms and protective gear are seen working in a factory-like environment. The final shot shows the bakery's logo on a Google search result, indicating the video's purpose is to provide information about the bakery's history and location."}]
5.5s • 28.0 MB • 5.1 MB/s
```
5.67s • 28.0 MB • 4.9 MB/s

╭────────────┬───────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model             │ Base Command                                      │ Extra Args                                                                                  │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼────────────┤
│ video-fra… │ qwen/qwen3.5-0.8b │ mm cat <vid> --mode fast --no-cache --format json │ --prompt 'Summarise what happens in this video in one sentence.' --generate.extra-body      │ 5.97s │ 472ms │ 5.61s │ 6.50s │ 42.4x │  4.7 │ 22.46 Gbps │
│            │                   │                                                   │ '{"video_fps":1.0,"video_max_frames":8}'                                                    │       │       │       │       │       │      │            │
╰────────────┴───────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴────────────╯
args: {"vid": "bakery.mp4", "mode": "fast"}
```json
[{"path": "bakery.mp4", "mode": "fast", "content": "Based on the visual evidence in the provided images, here is the summary of the video's content:\n\nThe video is a montage of scenes from a bakery, specifically focusing on the history and operations of a historic establishment. It begins with a collage of historical photographs and modern footage, establishing the site's long-standing presence. The narrative then shifts to the current day, showing the active work of the bakery's staff. The final segment features a Google search result for \"Baker's Bakery,\" confirming the location and providing context to the historical footage."}]
5.4s • 28.0 MB • 5.2 MB/s
```
5.61s • 28.0 MB • 5.0 MB/s

╭────────────┬───────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model             │ Base Command                                      │ Extra Args                                                                                  │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼────────────┤
│ video-fra… │ qwen/qwen3.5-0.8b │ mm cat <vid> --mode fast --no-cache --format json │ --prompt 'Summarise what happens in this video in one sentence.' --generate.extra-body      │ 5.97s │ 124ms │ 5.83s │ 6.07s │ 42.3x │  4.7 │ 22.43 Gbps │
│            │                   │                                                   │ '{"video_fps":2.0,"video_max_frames":16}'                                                   │       │       │       │       │       │      │            │
╰────────────┴───────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴────────────╯
args: {"vid": "bakery.mp4", "mode": "fast"}
```json
[{"path": "bakery.mp4", "mode": "fast", "content": "Based on the visual evidence across the five images, here is the summary of the video:\n\nThe video chronicles the history of a bakery in a specific location, focusing on its evolution and its current status.\n\n*   **Historical Context:** The video begins with a montage of black-and-white historical photos, establishing the site's past. These images show the bakery's origins, including a fire that damaged the complex and a historical map of the area.\n*   **Modern Operations:** The video then transitions to a modern setting, showing the current state of the bakery. It features contemporary footage of staff in white coats and protective gear working in a clean, organized environment.\n*   **Conclusion:** The final shot displays the Google logo, indicating that the video was likely generated using the Google search engine."}]
5.6s • 28.0 MB • 5.0 MB/s
```
5.83s • 28.0 MB • 4.8 MB/s

╭────────────┬───────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────────────┬────────┬───────┬────────┬────────┬───────┬──────┬─────────────╮
│ Group      │ Model             │ Base Command                                      │ Extra Args                                          │   Mean │  ±Std │    Min │    Max │ Speed │ MB/s │         bps │
├────────────┼───────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────┼────────┼───────┼────────┼────────┼───────┼──────┼─────────────┤
│ cache      │ qwen/qwen3.5-0.8b │ mm cat <doc> --mode fast --no-cache --format json │ --prompt 'Summarize this document in one sentence.' │ 12.80s │ 972ms │ 12.17s │ 13.92s │ 0.08x │  0.0 │ 218.06 kbps │
╰────────────┴───────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────────────┴────────┴───────┴────────┴────────┴───────┴──────┴─────────────╯
args: {"doc": "BillDownload-8pg.pdf", "mode": "fast"}
```json
[{"path": "BillDownload-8pg.pdf", "mode": "fast", "content": "This document is a monthly electricity bill from SEAWORLD PARKS & ENTERTAINMENT LLC for October 2024, detailing a charge of $342,775.48 due on October 18, 2024, with a credit balance of $0.00 and a monthly usage of 3,900,000 kWh.\n\n---\n\nThis document summarizes the charges for three service addresses (33806 SAINT JOE RD, GILMORE/#578/.2S, and another unspecified address) for the billing period of September 10, 2024, detailing the current and previous meter readings, total kWh usage, and corresponding amounts billed.\n\n---\n\nThis document summarizes the electricity charges for three service addresses in GILMORE, Florida, detailing their account numbers, meter readings, billing periods, and amounts for the current month, with the last page continuing the energy usage data from the previous month.\n\n---\n\nThis document summarizes the charges for three service addresses, detailing the specific meter readings, kWh usage, and billing amounts for each account.\n\n---\n\nThis document summarizes the charges for three service addresses in Tampa, FL, detailing the specific meter readings, kWh usage, and billing amounts for each account.\n\n---\n\nThis document summarizes the charges for three service addresses in Tampa, FL, detailing their specific meter readings, usage amounts, and billing periods, with a total current month's charges of $342,775.48.\n\n---\n\nThis document summarizes a utility bill for a residential service account (Sub-Account #211008435284) in the 33rd month of 2024, detailing a monthly electric charge of $32.40 including daily basic service, Florida Gross Receipt Tax, and other fees, with a billing period spanning from August 9, 2024, to September 10, 2024.\n\n---\n\nThis document summarizes a 33-day billing period for a residential pump meter in Daede City, FL, where the user paid $27.54 in total electric charges including daily service, energy, fuel, and storm protection fees, with a late payment fee of $5.00 applied."}]
12.1s • 340.8 KB • 28.2 KB/s
```
12.32s • 340.8 KB • 27.7 KB/s

╭────────────┬───────────────────┬────────────────────────────────────────┬─────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model             │ Base Command                           │ Extra Args                                          │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────────┼────────────────────────────────────────┼─────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼────────────┤
│ cache      │ qwen/qwen3.5-0.8b │ mm cat <doc> --mode fast --format json │ --prompt 'Summarize this document in one sentence.' │ 122ms │ 0.73ms │ 121ms │ 123ms │ 8.18x │  2.7 │ 22.85 Mbps │
╰────────────┴───────────────────┴────────────────────────────────────────┴─────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴────────────╯
args: {"doc": "BillDownload-8pg.pdf", "mode": "fast"}
```json
[{"path": "BillDownload-8pg.pdf", "mode": "fast", "content": "This document is a monthly electricity bill from SEAWORLD PARKS & ENTERTAINMENT LLC for October 2024, detailing a charge of $342,775.48 due on October 18, 2024, with a credit balance of $0.00 and a monthly usage of 3,900,000 kWh.\n\n---\n\nThis document summarizes the charges for three service addresses (33806 SAINT JOE RD, GILMORE/#578/.2S, and another unspecified address) for the billing period of September 10, 2024, detailing the current and previous meter readings, total kWh usage, and corresponding amounts billed.\n\n---\n\nThis document summarizes the electricity charges for three service addresses in GILMORE, Florida, detailing their account numbers, meter readings, billing periods, and amounts for the current month, with the last page continuing the energy usage data from the previous month.\n\n---\n\nThis document summarizes the charges for three service addresses, detailing the specific meter readings, kWh usage, and billing amounts for each account.\n\n---\n\nThis document summarizes the charges for three service addresses in Tampa, FL, detailing the specific meter readings, kWh usage, and billing amounts for each account.\n\n---\n\nThis document summarizes the charges for three service addresses in Tampa, FL, detailing their specific meter readings, usage amounts, and billing periods, with a total current month's charges of $342,775.48.\n\n---\n\nThis document summarizes a utility bill for a residential service account (Sub-Account #211008435284) in the 33rd month of 2024, detailing a monthly electric charge of $32.40 including daily basic service, Florida Gross Receipt Tax, and other fees, with a billing period spanning from August 9, 2024, to September 10, 2024.\n\n---\n\nThis document summarizes a 33-day billing period for a residential pump meter in Daede City, FL, where the user paid $27.54 in total electric charges including daily service, energy, fuel, and storm protection fees, with a late payment fee of $5.00 applied."}]
cached • 27ms • 340.8 KB • 12.3 MB/s
```
123ms • 340.8 KB • 2.7 MB/s

╭────────────┬────────────────────────┬───────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                  │ Base Command                                      │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼────────────────────────┼───────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ 404        │ vlm-run/nonexistent-v0 │ mm cat <img> --mode fast --no-cache --format json │ 751ms │ 17.1ms │ 734ms │ 768ms │ 1.33x │  0.0 │ 9.82 Mbps │
╰────────────┴────────────────────────┴───────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Error code: 404 - {'detail': {'error': {'message': \"Model 'vlm-run/nonexistent-v0' not found. Available: ['Qwen/Qwen3.5-0.8B', 'facebook/sam3', 'fastino/gliner2-multi-v1', 'ggml-org/SmolVLM-256M-Instruct-GGUF', 'ggml-org/SmolVLM2-256M-Video-Instruct-GGUF', 'ggml-org/SmolVLM2-500M-Video-Instruct-GGUF', 'ggml-org/smolvlm-256m-instruct-gguf', 'ggml-org/smolvlm2-256m-video-instruct-gguf', 'ggml-org/smolvlm2-500m-video-instruct-gguf', 'microsoft/Florence-2-base-ft', 'microsoft/florence-2-base-ft', 'paddleocr/pp-ocrv5', 'qwen/qwen3.5-0.8b', 'rednote-hilab/dots.ocr', 'roboflow/rfdetr-nano', 'roboflow/rfdetr-seg-nano', 'usyd-community/vitpose-plus-small', 'vikhyatk/moondream2']\", 'type': 'model_not_found', 'code': None, 'param': None}}}]"}]
590ms • 38.2 KB • 64.7 KB/s
```
734ms • 38.2 KB • 52.0 KB/s

╭────────────┬──────────────────────────────────┬───────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                            │ Base Command                                      │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────────────────────────┼───────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ 404        │ microsoft/florence-2-NONEXISTENT │ mm cat <img> --mode fast --no-cache --format json │ 790ms │ 27.4ms │ 758ms │ 806ms │ 1.27x │  0.0 │ 9.34 Mbps │
╰────────────┴──────────────────────────────────┴───────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Error code: 404 - {'detail': {'error': {'message': \"Model 'microsoft/florence-2-NONEXISTENT' not found. Available: ['Qwen/Qwen3.5-0.8B', 'facebook/sam3', 'fastino/gliner2-multi-v1', 'ggml-org/SmolVLM-256M-Instruct-GGUF', 'ggml-org/SmolVLM2-256M-Video-Instruct-GGUF', 'ggml-org/SmolVLM2-500M-Video-Instruct-GGUF', 'ggml-org/smolvlm-256m-instruct-gguf', 'ggml-org/smolvlm2-256m-video-instruct-gguf', 'ggml-org/smolvlm2-500m-video-instruct-gguf', 'microsoft/Florence-2-base-ft', 'microsoft/florence-2-base-ft', 'paddleocr/pp-ocrv5', 'qwen/qwen3.5-0.8b', 'rednote-hilab/dots.ocr', 'roboflow/rfdetr-nano', 'roboflow/rfdetr-seg-nano', 'usyd-community/vitpose-plus-small', 'vikhyatk/moondream2']\", 'type': 'model_not_found', 'code': None, 'param': None}}}]"}]
663ms • 38.2 KB • 57.6 KB/s
```
805ms • 38.2 KB • 47.4 KB/s

╭────────────┬─────────────────────────────┬───────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                       │ Base Command                                      │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼─────────────────────────────┼───────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ 404        │ paddlepaddle/paddleocr-v999 │ mm cat <img> --mode fast --no-cache --format json │ 771ms │ 44.6ms │ 732ms │ 820ms │ 1.30x │  0.0 │ 9.57 Mbps │
╰────────────┴─────────────────────────────┴───────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Error code: 404 - {'detail': {'error': {'message': \"Model 'paddlepaddle/paddleocr-v999' not found. Available: ['Qwen/Qwen3.5-0.8B', 'facebook/sam3', 'fastino/gliner2-multi-v1', 'ggml-org/SmolVLM-256M-Instruct-GGUF', 'ggml-org/SmolVLM2-256M-Video-Instruct-GGUF', 'ggml-org/SmolVLM2-500M-Video-Instruct-GGUF', 'ggml-org/smolvlm-256m-instruct-gguf', 'ggml-org/smolvlm2-256m-video-instruct-gguf', 'ggml-org/smolvlm2-500m-video-instruct-gguf', 'microsoft/Florence-2-base-ft', 'microsoft/florence-2-base-ft', 'paddleocr/pp-ocrv5', 'qwen/qwen3.5-0.8b', 'rednote-hilab/dots.ocr', 'roboflow/rfdetr-nano', 'roboflow/rfdetr-seg-nano', 'usyd-community/vitpose-plus-small', 'vikhyatk/moondream2']\", 'type': 'model_not_found', 'code': None, 'param': None}}}]"}]
666ms • 38.2 KB • 57.3 KB/s
```
820ms • 38.2 KB • 46.6 KB/s

╭────────────┬───────────┬───────────────────────────────────────────────────┬────────────────────────────────────┬────────┬────────┬────────┬────────┬───────┬──────┬─────────────╮
│ Group      │ Model     │ Base Command                                      │ Extra Args                         │   Mean │   ±Std │    Min │    Max │ Speed │ MB/s │         bps │
├────────────┼───────────┼───────────────────────────────────────────────────┼────────────────────────────────────┼────────┼────────┼────────┼────────┼───────┼──────┼─────────────┤
│ validation │ (default) │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{not json}' │ 72.1ms │ 3.10ms │ 68.5ms │ 74.0ms │ 13.9x │  0.5 │ 102.29 Mbps │
╰────────────┴───────────┴───────────────────────────────────────────────────┴────────────────────────────────────┴────────┴────────┴────────┴────────┴───────┴──────┴─────────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```text
[exit 1]
Error: --generate.extra-body must be a JSON object: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
```
74.0ms • 38.2 KB • 516.1 KB/s

╭────────────┬───────────┬───────────────────────────────────────────────────┬─────────────────────────────────┬────────┬────────┬────────┬────────┬───────┬──────┬─────────────╮
│ Group      │ Model     │ Base Command                                      │ Extra Args                      │   Mean │   ±Std │    Min │    Max │ Speed │ MB/s │         bps │
├────────────┼───────────┼───────────────────────────────────────────────────┼─────────────────────────────────┼────────┼────────┼────────┼────────┼───────┼──────┼─────────────┤
│ validation │ (default) │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '[1,2,3]' │ 71.4ms │ 1.17ms │ 70.0ms │ 72.1ms │ 14.0x │  0.5 │ 103.31 Mbps │
╰────────────┴───────────┴───────────────────────────────────────────────────┴─────────────────────────────────┴────────┴────────┴────────┴────────┴───────┴──────┴─────────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```text
[exit 1]
Error: --generate.extra-body must decode to a JSON object, got list
```
70.0ms • 38.2 KB • 545.1 KB/s
