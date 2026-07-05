# mm bench recording — vlmgw — 2026-05-02

Run: `mm bench` against `/Users/user/data/mmbench-tiny` (rounds=3, warmup=1, 9 files / 43.1 MB, wall=373.79s).
Benchfile: `benchmarks/vlmgw_bench_commands.py`.
Host: `dev-macbook.local` · Apple M3 Max (16 threads) · macOS 14.6 · Python 3.12.9 · mm v0.10.0.
Profile: `vlmgw` (`https://<redacted>.run.app/v1/openai/`, default model `qwen/qwen3.5-0.8b`).

## Disabled (18)

- `noop/ping` — `vlm-run/noop`
- `noop/image-512` — `vlm-run/noop`
- `noop/image-1024` — `vlm-run/noop`
- `qwen/text` — `qwen/qwen3.5-0.8b`
- `sam3/segment` — `facebook/sam3`
- `sam3/segment_box` — `facebook/sam3`
- `sam3/track` — `facebook/sam3`
- `dots-ocr/parse_layout` — `rednote-hilab/dots.ocr`
- `dots-ocr/parse_layout_only` — `rednote-hilab/dots.ocr`
- `dots-ocr/ocr` — `rednote-hilab/dots.ocr`
- `dots-ocr/grounding_ocr` — `rednote-hilab/dots.ocr`
- `paddleocr/ocr` — `paddleocr/pp-ocrv5`
- `paddleocr/detect` — `paddleocr/pp-ocrv5`
- `gliner/extract_entities` — `fastino/gliner2-multi-v1`
- `gliner/classify_text` — `fastino/gliner2-multi-v1`
- `smolvlm2/256m-video` — `ggml-org/smolvlm2-256m-video-instruct-gguf`
- `smolvlm2/500m-video` — `ggml-org/smolvlm2-500m-video-instruct-gguf`
- `moondream/caption+llm` — `vikhyatk/moondream2`

---

╭────────────┬──────────────────────────────┬───────────────────────────────────────────────────┬──────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                        │ Base Command                                      │ Extra Args                                   │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────────────────────┼───────────────────────────────────────────────────┼──────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ microsoft/florence-2-base-ft │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"caption"}' │ 1.83s │ 76.9ms │ 1.75s │ 1.90s │ 0.55x │  0.0 │ 4.03 Mbps │
╰────────────┴──────────────────────────────┴───────────────────────────────────────────────────┴──────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "{\n  \"<CAPTION>\": \"A small green car parked in front of a building.\"\n}"}]
1.7s • 38.2 KB • 22.9 KB/s
```
1.90s • 38.2 KB • 20.0 KB/s

╭────────────┬──────────────────────────────┬────────────────────────────────────────────────────┬──────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬─────╮
│ Group      │ Model                        │ Base Command                                       │ Extra Args                               │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │ bps │
├────────────┼──────────────────────────────┼────────────────────────────────────────────────────┼──────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼─────┤
│ model      │ microsoft/florence-2-base-ft │ mm cat <file> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"ocr"}' │ 2.13s │ 59.2ms │ 2.07s │ 2.19s │     — │    — │   — │
╰────────────┴──────────────────────────────┴────────────────────────────────────────────────────┴──────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴─────╯
args: {"mode": "fast"}
```json
[{"path": "image-ocr.jpg", "mode": "fast", "content": "{\n  \"<OCR>\": \"Today is Thursday, October 20th-But itdefnifly feels like a friday. I'm alreadyconsarding making a glend cup ofcoffee-and I have a problem?Somitimes I'll flip through older notes livetalkin and my handwning is unrecognutable,perhaps it depends on the type of per I use?I've thied writing in all caps But IT LOOKS soFORCED AND UNNATURALCopen times, I'm just take notes on myLaptops, but I still seem to gramtate towardpen and paper. Amy advance on what toI'm prune? I already feel stressed at 100kingbank at what I've just written-it looks like3 different people wrote this !!\"\n}"}]
1.8s • 147.0 KB • 80.0 KB/s
```
2.07s

╭────────────┬──────────────────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                        │ Base Command                                      │ Extra Args                              │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ microsoft/florence-2-base-ft │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"od"}' │ 1.83s │ 64.2ms │ 1.77s │ 1.90s │ 0.55x │  0.0 │ 4.03 Mbps │
╰────────────┴──────────────────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "{\n  \"<OD>\": {\n    \"bboxes\": [\n      [\n        27.904001235961914,\n        129.21600341796875,\n        477.4400329589844,\n        296.2560119628906\n      ]\n    ],\n    \"labels\": [\n      \"car\"\n    ]\n  }\n}"}]
1.5s • 38.2 KB • 25.0 KB/s
```
1.77s • 38.2 KB • 21.5 KB/s

╭────────────┬─────────────────────┬───────────────────────────────────────────────────┬──────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model               │ Base Command                                      │ Extra Args                                   │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼─────────────────────┼───────────────────────────────────────────────────┼──────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ vikhyatk/moondream2 │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"caption"}' │ 2.46s │ 38.3ms │ 2.42s │ 2.50s │ 0.41x │  0.0 │ 3.00 Mbps │
╰────────────┴─────────────────────┴───────────────────────────────────────────────────┴──────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "A vintage light blue Volkswagen Beetle is parked parallel to a yellow building with a wooden door. The car's roof and side panels are a slightly darker shade of blue/teal. The building features a brown wooden door and has light beige or cream colored stucco or plaster. The street is paved with grey/light brown stone or brick.  There is a small patch of green vegetation visible behind the building."}]
2.2s • 38.2 KB • 17.5 KB/s
```
2.42s • 38.2 KB • 15.8 KB/s

╭────────────┬─────────────────────┬───────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model               │ Base Command                                      │ Extra Args                                                                     │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼─────────────────────┼───────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ vikhyatk/moondream2 │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"detect","method_params":{"object":"bench"}}' │ 1.77s │ 80.4ms │ 1.70s │ 1.86s │ 0.57x │  0.0 │ 4.17 Mbps │
╰────────────┴─────────────────────┴───────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "{\n  \"objects\": []\n}"}]
1.5s • 38.2 KB • 25.4 KB/s
```
1.74s • 38.2 KB • 22.0 KB/s

╭────────────┬───────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model             │ Base Command                                      │ Extra Args                              │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼───────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ qwen/qwen3.5-0.8b │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'Describe this image briefly.' │ 2.57s │ 62.5ms │ 2.51s │ 2.64s │ 0.39x │  0.0 │ 2.87 Mbps │
╰────────────┴───────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "This image captures a charming, vintage-style scene featuring a classic Volkswagen Beetle, painted in a soft mint green with a white stripe running down its center. The car is parked on a paved street, angled slightly toward the left, showcasing its rounded, bulbous body and distinctive round headlights. The wheels are fitted with chrome hubcaps and black tires, adding a touch of retro elegance.\n\nThe background consists of a weathered, yellowish wall with two wooden doors: one on the left featuring arched panels, and another on the right with vertical planks. Both doors are framed in white, creating a striking contrast against the warm tones of the wall. The overall composition is clean and well-lit, emphasizing the car's vintage charm and the rustic setting."}]
2.4s • 38.2 KB • 16.1 KB/s
```
2.64s • 38.2 KB • 14.5 KB/s

╭────────────┬───────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model             │ Base Command                                      │ Extra Args                                                                                  │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼────────────┤
│ model      │ qwen/qwen3.5-0.8b │ mm cat <vid> --mode fast --no-cache --format json │ --prompt 'Summarise what happens in this video in one sentence.' --generate.extra-body      │ 4.91s │ 182ms │ 4.76s │ 5.11s │ 51.4x │  5.7 │ 27.27 Gbps │
│            │                   │                                                   │ '{"video_fps":0.4,"video_max_frames":8,"video_resolution":"448x336"}'                       │       │       │       │       │       │      │            │
╰────────────┴───────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴────────────╯
args: {"vid": "bakery.mp4", "mode": "fast"}
```json
[{"path": "bakery.mp4", "mode": "fast", "content": "Based on the visual evidence across the five images, here is the summary of the video's content:\n\nThe video is a montage of scenes from a bakery, focusing on its history and operations. It begins with a collage of historical photos showing the bakery's past, including its location in McKees Rocks, Pennsylvania, and its name \"Bakery.\" The central theme is the bakery's current state, where staff in white uniforms and hairnets are seen working in a clean, organized environment. The video highlights the bakery's role as a hub for baking and food production, with shots of finished goods like bread and cakes, as well as the bakery's name appearing on product packaging. The final frame displays the Google logo, suggesting the video was likely generated by an AI model."}]
4.5s • 28.0 MB • 6.2 MB/s
```
4.76s • 28.0 MB • 5.9 MB/s

╭────────────┬───────────────────┬─────────────────────────────────────────────────────────┬──────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model             │ Base Command                                            │ Extra Args                           │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────────┼─────────────────────────────────────────────────────────┼──────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼────────────┤
│ model      │ qwen/qwen3.5-0.8b │ mm cat <img> <img> --mode fast --no-cache --format json │ --prompt 'Compare these two images.' │ 4.84s │ 67.2ms │ 4.77s │ 4.91s │ 0.41x │  0.0 │ 12.87 Mbps │
╰────────────┴───────────────────┴─────────────────────────────────────────────────────────┴──────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴────────────╯
args: {"img": ["1-vqa-car.jpg", "invoice.jpg"], "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "Picture 1:\nThis image displays a classic, light teal Volkswagen Beetle parked on a paved street. The car is positioned in profile, showcasing its rounded, vintage design with chrome bumpers and whitewall tires. The setting appears to be an urban or suburban street, with a yellow wall featuring two wooden doors in the background. The lighting suggests a bright, possibly overcast day, giving the scene a warm and nostalgic atmosphere.\n\nPicture 2:\nThis image features a single, large, light blue Volkswagen Beetle parked on a paved road. The car is shown from a slightly elevated angle, emphasizing its sleek, elongated body and the prominent chrome grille and headlights. The background consists of a blurred, multi-colored building with a mix of red, yellow, and blue hues, creating a vibrant and dynamic backdrop. The overall composition highlights the car's modern, sleek lines against a more complex and colorful urban environment.\n\n---\n\n**Comparison:**\n\
... [1,305 bytes truncated]
```
4.91s • 182.1 KB • 37.1 KB/s

╭────────────┬──────────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                │ Base Command                                      │ Extra Args                                  │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ roboflow/rfdetr-nano │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"detect"}' │ 1.99s │ 133ms │ 1.92s │ 2.15s │ 0.50x │  0.0 │ 3.70 Mbps │
╰────────────┴──────────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "{\n  \"detections\": [\n    {\n      \"bbox_xyxy\": [\n        30.127044677734375,\n        128.95506286621094,\n        465.9603271484375,\n        297.70526123046875\n      ],\n      \"label\": \"car\",\n      \"confidence\": 0.9583,\n      \"class_id\": 3\n    }\n  ],\n  \"count\": 1\n}"}]
1.9s • 38.2 KB • 20.2 KB/s
```
2.15s • 38.2 KB • 17.8 KB/s

╭────────────┬──────────────────────────┬───────────────────────────────────────────────────┬──────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                    │ Base Command                                      │ Extra Args                                   │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────────────────┼───────────────────────────────────────────────────┼──────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ roboflow/rfdetr-seg-nano │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"segment"}' │ 2.12s │ 274ms │ 1.94s │ 2.43s │ 0.47x │  0.0 │ 3.49 Mbps │
╰────────────┴──────────────────────────┴───────────────────────────────────────────────────┴──────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "{\n  \"detections\": [\n    {\n      \"bbox_xyxy\": [\n        29.09161376953125,\n        129.51760864257812,\n        466.57952880859375,\n        297.937744140625\n      ],\n      \"label\": \"car\",\n      \"confidence\": 0.9628,\n      \"class_id\": 3,\n      \"mask_png\": \"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAgAAAAGACAAAAAD+S4VjAAAF9klEQVR4nO3dy3LbOBAFUHgq///LnkXsclLRgwQbQDd4zmoWtgT0vYQoxfa0BgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACwzMfqBcT7PPh1G269wyZTOBr6a5sM45TKe45J/YnKgzmj5D6HJv+3kvM5o9oGJ2b/rdqIzqm0uwXhf6s0pnOq7Gxh+F+qTOqkCttaH/5vFWZ1WvpNZUm/tVZgWucl31Kq+Fv6cXXIvKNs6beWe15d0m4oY/qtJR5Yp6T7yRp/SzuxXr9WL+CBxOnv57/VC/hX8vyTL++sdAdagfmmm9kVyTZTIP6WbmiXpNpLjfhbsqldk+gmsEz8W8lzE1gp/0prfSPLCbDRSGtJcgJUy7/aep9LcTtTcZwpBhcgwwlQMf9tJChAzfxrrvpf6wuwyySLWv1SVjj+1aOLsfgEKJx/6bX/WFuAPWZY2tICFM+/+PJ/W1mALQZY3cIC1M+//g4W3sruMLwd3gmsOgH2yH8DiwqwS/7197GmAPXn9q38TpYUoPzUNrLgLmaz+IvfB84/ATbLv/p+pheg+LweqL2j2Q
... [1,514 bytes truncated]
```
1.98s • 38.2 KB • 19.3 KB/s

╭────────────┬───────────────────────────────────┬────────────────────────────────────────────────────┬───────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬─────╮
│ Group      │ Model                             │ Base Command                                       │ Extra Args                                │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │ bps │
├────────────┼───────────────────────────────────┼────────────────────────────────────────────────────┼───────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼─────┤
│ model      │ usyd-community/vitpose-plus-small │ mm cat <file> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"pose"}' │ 2.17s │ 60.3ms │ 2.10s │ 2.22s │     — │    — │   — │
╰────────────┴───────────────────────────────────┴────────────────────────────────────────────────────┴───────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴─────╯
args: {"mode": "fast"}
```json
[{"path": "2.1-detect-count-tennis.jpg", "mode": "fast", "content": "{\n  \"persons\": [\n    {\n      \"bbox_xyxy\": [\n        305.6180419921875,\n        160.8521728515625,\n        375.07598876953125,\n        313.5617980957031\n      ],\n      \"keypoints\": [\n        {\n          \"name\": \"nose\",\n          \"xy\": [\n            346.0057373046875,\n            206.3638916015625\n          ],\n          \"score\": 0.8838\n        },\n        {\n          \"name\": \"left_eye\",\n          \"xy\": [\n            347.92462158203125,\n            207.47018432617188\n          ],\n          \"score\": 0.9236\n        },\n        {\n          \"name\": \"right_eye\",\n          \"xy\": [\n            347.52655029296875,\n            206.01318359375\n          ],\n          \"score\": 0.997\n        },\n        {\n          \"name\": \"left_ear\",\n          \"xy\": [\n            349.5863037109375,\n            214.61541748046875\n          ],\n          \"score\": 0.9123\n        },\n        {\n
... [22,769 bytes truncated]
```
2.18s

╭────────────┬─────────────────────────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                               │ Base Command                                      │ Extra Args                              │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼─────────────────────────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ ggml-org/smolvlm-256m-instruct-gguf │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'Describe this image briefly.' │ 2.24s │ 49.5ms │ 2.19s │ 2.29s │ 0.45x │  0.0 │ 3.30 Mbps │
╰────────────┴─────────────────────────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "The image depicts a blue vintage car parked on a paved road. The car is painted in a bright, pastel green color, which contrasts sharply with the darker background of the wall behind it. The car has a sleek, aerodynamic design, with a streamlined body and a rounded front end. The tires are large, and the car appears to be well-maintained.\n\nThe wall behind the car is made of a light-colored material, possibly beige or off-white, and has a simple, clean appearance. The wall has a few wooden doors, which are brown in color, and they are evenly spaced and aligned. The doors are closed, and there are no visible signs of any damage or wear.\n\nThe ground in front of the car is paved with a smooth, light-colored material, which appears to be concrete or a similar material. There is a small patch of grass or a small patch of dirt visible on the ground, which is not very noticeable.\n\nThe image does not contain any people, animals, or other objects that are typ
... [184 bytes truncated]
```
2.23s • 38.2 KB • 17.1 KB/s

╭────────────┬────────────────────────────────────────────┬───────────────────────────────────────────────────┬───────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                                      │ Base Command                                      │ Extra Args                        │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼────────────────────────────────────────────┼───────────────────────────────────────────────────┼───────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ ggml-org/smolvlm2-256m-video-instruct-gguf │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'What is in this image?' │ 2.02s │ 82.1ms │ 1.95s │ 2.11s │ 0.49x │  0.0 │ 3.64 Mbps │
╰────────────┴────────────────────────────────────────────┴───────────────────────────────────────────────────┴───────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "The image depicts a vintage car parked on a street. The car is painted in a light blue color, and it has a distinctive design. The car is positioned in the center of the image, with the front of the car facing towards the left side of the image. The car is relatively small, with a long hood and a short trunk. The front of the car is facing towards the right side of the image, and the back of the car is facing towards the left side of the image. The car is parked on a cobblestone street, with a building in the background. The building has a white facade, and it has a wooden door on the right side."}]
1.9s • 38.2 KB • 20.4 KB/s
```
2.11s • 38.2 KB • 18.1 KB/s

╭────────────┬────────────────────────────────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                                      │ Base Command                                      │ Extra Args                              │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼────────────────────────────────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ ggml-org/smolvlm2-500m-video-instruct-gguf │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'Describe this image briefly.' │ 2.08s │ 88.2ms │ 1.98s │ 2.15s │ 0.48x │  0.0 │ 3.55 Mbps │
╰────────────┴────────────────────────────────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "A vintage Volkswagen Beetle sits parked on a cobblestone street, its light blue body gleaming under the sunlight. The car's classic design, with its rounded front and rounded back, is reminiscent of the 1960s. The building behind it is painted in a warm yellow color, adding a touch of warmth to the scene. The building's facade is adorned with a wooden door and window, and a small window on the right side of the building. The car is positioned in front of the building, and the street is lined with trees, adding a touch of nature to the scene."}]
1.9s • 38.2 KB • 20.4 KB/s
```
2.11s • 38.2 KB • 18.1 KB/s

╭────────────┬───────────────────┬───────────────────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model             │ Base Command                                      │ Extra Args                                                                        │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼───────────────────┼───────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ image-res  │ qwen/qwen3.5-0.8b │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'Describe the image in 1 sentence.' --encode.strategy_opts max_width=512 │ 2.42s │ 42.1ms │ 2.39s │ 2.47s │ 0.41x │  0.0 │ 3.05 Mbps │
╰────────────┴───────────────────┴───────────────────────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "This image captures a charming vintage Volkswagen Beetle parked on a cobblestone street in front of a weathered, yellow wall with two wooden doors. The car's light teal paint contrasts beautifully with the darker pavement and the warm tones of the building, creating a visually appealing and nostalgic scene."}]
2.2s • 38.2 KB • 17.5 KB/s
```
2.41s • 38.2 KB • 15.9 KB/s

╭────────────┬───────────────────┬───────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model             │ Base Command                                      │ Extra Args                                                                         │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼───────────────────┼───────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ image-res  │ qwen/qwen3.5-0.8b │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'Describe the image in 1 sentence.' --encode.strategy_opts max_width=1024 │ 2.44s │ 39.5ms │ 2.40s │ 2.48s │ 0.41x │  0.0 │ 3.02 Mbps │
╰────────────┴───────────────────┴───────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "This image captures a classic Volkswagen Beetle parked on a paved street in front of a weathered, yellow wall with two wooden doors. The car, painted in a soft mint green, stands out against the muted tones of the building, showcasing its iconic rounded shape and vintage charm."}]
2.2s • 38.2 KB • 17.5 KB/s
```
2.40s • 38.2 KB • 15.9 KB/s

╭────────────┬───────────────────┬───────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model             │ Base Command                                      │ Extra Args                                                                         │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼───────────────────┼───────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ image-res  │ qwen/qwen3.5-0.8b │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'Describe the image in 1 sentence.' --encode.strategy_opts max_width=1536 │ 2.48s │ 87.7ms │ 2.39s │ 2.56s │ 0.40x │  0.0 │ 2.97 Mbps │
╰────────────┴───────────────────┴───────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "This image captures a classic Volkswagen Beetle parked on a paved street in front of a weathered, yellow stucco building with two wooden doors. The car, painted in a soft mint green and white, is the central focus, showcasing its rounded, vintage design and chrome hubcaps. The scene is bathed in natural daylight, highlighting the texture of the building and the smooth curves of the car."}]
2.3s • 38.2 KB • 16.8 KB/s
```
2.50s • 38.2 KB • 15.2 KB/s

╭────────────┬───────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model             │ Base Command                                      │ Extra Args                                                                                  │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼────────────┤
│ video-fra… │ qwen/qwen3.5-0.8b │ mm cat <vid> --mode fast --no-cache --format json │ --prompt 'Summarise what happens in this video in one sentence.' --generate.extra-body      │ 4.82s │ 223ms │ 4.69s │ 5.08s │ 52.4x │  5.8 │ 27.78 Gbps │
│            │                   │                                                   │ '{"video_fps":0.5,"video_max_frames":4}'                                                    │       │       │       │       │       │      │            │
╰────────────┴───────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴────────────╯
args: {"vid": "bakery.mp4", "mode": "fast"}
```json
[{"path": "bakery.mp4", "mode": "fast", "content": "Based on the visual evidence across the five images, here is the summary of the video:\n\nThe video chronicles the history of a bakery in McKees Rocks, Pennsylvania, focusing on its transformation from a historic site to a modern industrial facility.\n\n*   **Historical Context:** The video begins by establishing the bakery's past through a collage of black-and-white photographs. These images depict the original \"Baker's House\" complex, including its distinctive steel arch bridge, the original brick building, and historical photos of the bakery's employees and customers.\n*   **Modern Operations:** The narrative then shifts to the current state of the business. A modern, white, and clean facility is shown, featuring large racks of freshly baked goods and employees wearing protective gear (gloves, hairnets).\n*   **Conclusion:** The video concludes with a modern promotional shot of the bakery's new \"Welcome to McKees Rocks\" sign and a Google logo, indicat
... [73 bytes truncated]
```
4.69s • 28.0 MB • 6.0 MB/s

╭────────────┬───────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model             │ Base Command                                      │ Extra Args                                                                                  │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼────────────┤
│ video-fra… │ qwen/qwen3.5-0.8b │ mm cat <vid> --mode fast --no-cache --format json │ --prompt 'Summarise what happens in this video in one sentence.' --generate.extra-body      │ 4.81s │ 141ms │ 4.73s │ 4.98s │ 52.5x │  5.8 │ 27.84 Gbps │
│            │                   │                                                   │ '{"video_fps":1.0,"video_max_frames":8}'                                                    │       │       │       │       │       │      │            │
╰────────────┴───────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴────────────╯
args: {"vid": "bakery.mp4", "mode": "fast"}
```json
[{"path": "bakery.mp4", "mode": "fast", "content": "Based on the visual evidence across the five images, here is the summary of the video:\n\nThe video chronicles the history of a bakery in McKees Rocks, Pennsylvania, focusing on its transition from a historic, multi-generational operation to a modern, technology-driven entity.\n\n*   **Historical Context:** The video begins by establishing the bakery's origins through a collage of black-and-white historical photos. These images depict the early days of the business, including its founding, the construction of the \"Baker's House,\" and the early days of the \"Baker's Works.\"\n*   **Modern Operations:** The narrative then shifts to the current state of the business. A modern collage shows the interior of the facility, featuring stainless steel equipment, automated machinery, and staff in white uniforms and hairnets.\n*   **Technology and Branding:** The video concludes with a modern presentation. A Google search result for \"Cinnamon\" is displayed, followed
... [171 bytes truncated]
```
4.73s • 28.0 MB • 5.9 MB/s

╭────────────┬───────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model             │ Base Command                                      │ Extra Args                                                                                  │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼────────────┤
│ video-fra… │ qwen/qwen3.5-0.8b │ mm cat <vid> --mode fast --no-cache --format json │ --prompt 'Summarise what happens in this video in one sentence.' --generate.extra-body      │ 4.85s │ 244ms │ 4.70s │ 5.13s │ 52.1x │  5.8 │ 27.62 Gbps │
│            │                   │                                                   │ '{"video_fps":2.0,"video_max_frames":16}'                                                   │       │       │       │       │       │      │            │
╰────────────┴───────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴────────────╯
args: {"vid": "bakery.mp4", "mode": "fast"}
```json
[{"path": "bakery.mp4", "mode": "fast", "content": "Based on the visual evidence across the five images, here is the summary of the video:\n\nThe video chronicles the history of a bakery in McKees Rocks, Pennsylvania, focusing on its transformation from a small, traditional establishment to a modern, tech-enabled operation.\n\n*   **Historical Context:** The video begins by establishing the bakery's past, showing its location in a historic brick building and its original name, \"Bakery Woods.\" It also displays historical photos of the bakery's original location and a map of the area.\n*   **Modern Operations:** The core of the video shifts to the current state of the business. It features a montage of modern employees, including chefs and staff in white uniforms and hairnets, working in a clean, well-lit facility.\n*   **Technology and Data:** A significant portion of the video highlights the use of technology. There are shots of employees using computers and tablets, and a prominent Google logo appears on s
... [372 bytes truncated]
```
5.13s • 28.0 MB • 5.5 MB/s

╭────────────┬───────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬─────────────╮
│ Group      │ Model             │ Base Command                                      │ Extra Args                                          │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │         bps │
├────────────┼───────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼─────────────┤
│ cache      │ qwen/qwen3.5-0.8b │ mm cat <doc> --mode fast --no-cache --format json │ --prompt 'Summarize this document in one sentence.' │ 7.68s │ 281ms │ 7.36s │ 7.89s │ 0.13x │  0.0 │ 363.72 kbps │
╰────────────┴───────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴─────────────╯
args: {"doc": "BillDownload-8pg.pdf", "mode": "fast"}
```json
[{"path": "BillDownload-8pg.pdf", "mode": "fast", "content": "This document summarizes a monthly electricity bill from SEAWORLD PARKS & ENTERTAINMENT LLC for October 2024, detailing a $342,775.48 charge for 3,120,000 kWh usage, with a balance of $0.00 and a due date of October 18, 2024.\n\n---\n\nThis document summarizes the charges for three service addresses (33806 SAINT JOE RD, GILMORE/#578/.2S, and another unspecified address) for the 33rd billing period, detailing the total amounts billed ($32.40, $58.45, and $78.51) and noting that the first two addresses are currently at 0% usage while the third address shows a 20.7% usage increase.\n\n---\n\nThis document summarizes the monthly energy usage charges for three service addresses in Tampa, Florida, detailing the specific meter readings, current-to-previous kWh usage, and corresponding amounts billed for each account.\n\n---\n\nThis document summarizes the monthly energy usage charges for three service addresses in Tampa, FL, detailing the specific meter r
... [1,604 bytes truncated]
```
7.89s • 340.8 KB • 43.2 KB/s

╭────────────┬───────────────────┬────────────────────────────────────────┬─────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model             │ Base Command                           │ Extra Args                                          │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────────┼────────────────────────────────────────┼─────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼────────────┤
│ cache      │ qwen/qwen3.5-0.8b │ mm cat <doc> --mode fast --format json │ --prompt 'Summarize this document in one sentence.' │ 136ms │ 4.60ms │ 133ms │ 141ms │ 7.33x │  2.4 │ 20.48 Mbps │
╰────────────┴───────────────────┴────────────────────────────────────────┴─────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴────────────╯
args: {"doc": "BillDownload-8pg.pdf", "mode": "fast"}
```json
[{"path": "BillDownload-8pg.pdf", "mode": "fast", "content": "This document summarizes a monthly electricity bill from SEAWORLD PARKS & ENTERTAINMENT LLC for October 2024, detailing a $342,775.48 charge for 3,120,000 kWh usage, with a balance of $0.00 and a due date of October 18, 2024.\n\n---\n\nThis document summarizes the charges for three service addresses (33806 SAINT JOE RD, GILMORE/#578/.2S, and another unspecified address) for the 33rd billing period, detailing the total amounts billed ($32.40, $58.45, and $78.51) and noting that the first two addresses are currently at 0% usage while the third address shows a 20.7% usage increase.\n\n---\n\nThis document summarizes the monthly energy usage charges for three service addresses in Tampa, Florida, detailing the specific meter readings, current-to-previous kWh usage, and corresponding amounts billed for each account.\n\n---\n\nThis document summarizes the monthly energy usage charges for three service addresses in Tampa, FL, detailing the specific meter r
... [1,615 bytes truncated]
```
133ms • 340.8 KB • 2.5 MB/s

╭────────────┬────────────────────────┬───────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model                  │ Base Command                                      │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼────────────────────────┼───────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼────────────┤
│ 404        │ vlm-run/nonexistent-v0 │ mm cat <img> --mode fast --no-cache --format json │ 690ms │ 16.7ms │ 671ms │ 701ms │ 1.45x │  0.1 │ 10.68 Mbps │
╰────────────┴────────────────────────┴───────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴────────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Error code: 404 - {'detail': {'error': {'message': \"Model 'vlm-run/nonexistent-v0' not found. Available: ['Qwen/Qwen3.5-0.8B', 'facebook/sam3', 'fastino/gliner2-multi-v1', 'ggml-org/SmolVLM-256M-Instruct-GGUF', 'ggml-org/SmolVLM2-256M-Video-Instruct-GGUF', 'ggml-org/SmolVLM2-500M-Video-Instruct-GGUF', 'ggml-org/smolvlm-256m-instruct-gguf', 'ggml-org/smolvlm2-256m-video-instruct-gguf', 'ggml-org/smolvlm2-500m-video-instruct-gguf', 'microsoft/Florence-2-base-ft', 'microsoft/florence-2-base-ft', 'paddleocr/pp-ocrv5', 'qwen/qwen3.5-0.8b', 'rednote-hilab/dots.ocr', 'roboflow/rfdetr-nano', 'roboflow/rfdetr-seg-nano', 'usyd-community/vitpose-plus-small', 'vikhyatk/moondream2']\", 'type': 'model_not_found', 'code': None, 'param': None}}}]"}]
522ms • 38.2 KB • 73.1 KB/s
```
671ms • 38.2 KB • 56.9 KB/s

╭────────────┬──────────────────────────────────┬───────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model                            │ Base Command                                      │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼──────────────────────────────────┼───────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼────────────┤
│ 404        │ microsoft/florence-2-NONEXISTENT │ mm cat <img> --mode fast --no-cache --format json │ 704ms │ 8.01ms │ 697ms │ 713ms │ 1.42x │  0.1 │ 10.47 Mbps │
╰────────────┴──────────────────────────────────┴───────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴────────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Error code: 404 - {'detail': {'error': {'message': \"Model 'microsoft/florence-2-NONEXISTENT' not found. Available: ['Qwen/Qwen3.5-0.8B', 'facebook/sam3', 'fastino/gliner2-multi-v1', 'ggml-org/SmolVLM-256M-Instruct-GGUF', 'ggml-org/SmolVLM2-256M-Video-Instruct-GGUF', 'ggml-org/SmolVLM2-500M-Video-Instruct-GGUF', 'ggml-org/smolvlm-256m-instruct-gguf', 'ggml-org/smolvlm2-256m-video-instruct-gguf', 'ggml-org/smolvlm2-500m-video-instruct-gguf', 'microsoft/Florence-2-base-ft', 'microsoft/florence-2-base-ft', 'paddleocr/pp-ocrv5', 'qwen/qwen3.5-0.8b', 'rednote-hilab/dots.ocr', 'roboflow/rfdetr-nano', 'roboflow/rfdetr-seg-nano', 'usyd-community/vitpose-plus-small', 'vikhyatk/moondream2']\", 'type': 'model_not_found', 'code': None, 'param': None}}}]"}]
547ms • 38.2 KB • 69.7 KB/s
```
702ms • 38.2 KB • 54.3 KB/s

╭────────────┬─────────────────────────────┬───────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model                       │ Base Command                                      │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼─────────────────────────────┼───────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼────────────┤
│ 404        │ paddlepaddle/paddleocr-v999 │ mm cat <img> --mode fast --no-cache --format json │ 708ms │ 19.4ms │ 686ms │ 721ms │ 1.41x │  0.1 │ 10.41 Mbps │
╰────────────┴─────────────────────────────┴───────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴────────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
[{"path": "1-vqa-car.jpg", "mode": "fast", "content": "[LLM error: Error code: 404 - {'detail': {'error': {'message': \"Model 'paddlepaddle/paddleocr-v999' not found. Available: ['Qwen/Qwen3.5-0.8B', 'facebook/sam3', 'fastino/gliner2-multi-v1', 'ggml-org/SmolVLM-256M-Instruct-GGUF', 'ggml-org/SmolVLM2-256M-Video-Instruct-GGUF', 'ggml-org/SmolVLM2-500M-Video-Instruct-GGUF', 'ggml-org/smolvlm-256m-instruct-gguf', 'ggml-org/smolvlm2-256m-video-instruct-gguf', 'ggml-org/smolvlm2-500m-video-instruct-gguf', 'microsoft/Florence-2-base-ft', 'microsoft/florence-2-base-ft', 'paddleocr/pp-ocrv5', 'qwen/qwen3.5-0.8b', 'rednote-hilab/dots.ocr', 'roboflow/rfdetr-nano', 'roboflow/rfdetr-seg-nano', 'usyd-community/vitpose-plus-small', 'vikhyatk/moondream2']\", 'type': 'model_not_found', 'code': None, 'param': None}}}]"}]
546ms • 38.2 KB • 69.9 KB/s
```
718ms • 38.2 KB • 53.1 KB/s

╭────────────┬───────────┬───────────────────────────────────────────────────┬────────────────────────────────────┬────────┬────────┬────────┬────────┬───────┬──────┬────────────╮
│ Group      │ Model     │ Base Command                                      │ Extra Args                         │   Mean │   ±Std │    Min │    Max │ Speed │ MB/s │        bps │
├────────────┼───────────┼───────────────────────────────────────────────────┼────────────────────────────────────┼────────┼────────┼────────┼────────┼───────┼──────┼────────────┤
│ validation │ (default) │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{not json}' │ 85.4ms │ 5.41ms │ 80.7ms │ 91.3ms │ 11.7x │  0.4 │ 86.35 Mbps │
╰────────────┴───────────┴───────────────────────────────────────────────────┴────────────────────────────────────┴────────┴────────┴────────┴────────┴───────┴──────┴────────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```text
[exit 1]
Error: --generate.extra-body must be a JSON object: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
```
80.7ms • 38.2 KB • 472.8 KB/s

╭────────────┬───────────┬───────────────────────────────────────────────────┬─────────────────────────────────┬────────┬────────┬────────┬────────┬───────┬──────┬────────────╮
│ Group      │ Model     │ Base Command                                      │ Extra Args                      │   Mean │   ±Std │    Min │    Max │ Speed │ MB/s │        bps │
├────────────┼───────────┼───────────────────────────────────────────────────┼─────────────────────────────────┼────────┼────────┼────────┼────────┼───────┼──────┼────────────┤
│ validation │ (default) │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '[1,2,3]' │ 81.2ms │ 0.73ms │ 80.4ms │ 81.7ms │ 12.3x │  0.5 │ 90.81 Mbps │
╰────────────┴───────────┴───────────────────────────────────────────────────┴─────────────────────────────────┴────────┴────────┴────────┴────────┴───────┴──────┴────────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```text
[exit 1]
Error: --generate.extra-body must decode to a JSON object, got list
```
80.4ms • 38.2 KB • 474.9 KB/s
