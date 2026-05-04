# mm bench recording — vlmgw — 2026-05-02

Run: `mm bench` against `/Users/sudeep/data/mmbench-tiny` (rounds=3, warmup=1, 9 files / 43.1 MB, wall=501.80s).
Benchfile: `benchmarks/vlmgw_bench_commands.py`.
Host: `Sudeeps-M3-Max.local` · Apple M3 Max (16 threads) · macOS 14.6 · Python 3.12.9 · mm v0.10.0.
Profile: `vlmgw` (`https://gateway.vlm.run/v1/openai/`, default model `qwen/qwen3.5-0.8b`).

## Disabled (16)

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
- `gliner/extract_entities` — `fastino/gliner2-multi-v1`
- `gliner/classify_text` — `fastino/gliner2-multi-v1`
- `smolvlm2/256m-video` — `ggml-org/smolvlm2-256m-video-instruct-gguf`
- `smolvlm2/500m-video` — `ggml-org/smolvlm2-500m-video-instruct-gguf`
- `moondream/caption+llm` — `vikhyatk/moondream2`

---

╭────────────┬──────────────────────────────┬───────┬───────────────────────────────────────────────────┬──────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                        │ Task  │ Base Command                                      │ Extra Args                                   │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────────────────────┼───────┼───────────────────────────────────────────────────┼──────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ microsoft/florence-2-base-ft │ cap   │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"caption"}' │ 1.90s │ 67.1ms │ 1.83s │ 1.96s │ 0.53x │  0.0 │ 3.88 Mbps │
╰────────────┴──────────────────────────────┴───────┴───────────────────────────────────────────────────┴──────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
{
  "<CAPTION>": "A small green car parked in front of a building."
}
```
1.83s • 38.2 KB • 20.9 KB/s

╭────────────┬──────────────────────────────┬───────┬────────────────────────────────────────────────────┬──────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬─────╮
│ Group      │ Model                        │ Task  │ Base Command                                       │ Extra Args                               │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │ bps │
├────────────┼──────────────────────────────┼───────┼────────────────────────────────────────────────────┼──────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼─────┤
│ model      │ microsoft/florence-2-base-ft │ ocr   │ mm cat <file> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"ocr"}' │ 2.21s │ 43.0ms │ 2.16s │ 2.25s │     — │    — │   — │
╰────────────┴──────────────────────────────┴───────┴────────────────────────────────────────────────────┴──────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴─────╯
args: {"mode": "fast"}
```json
{
  "<OCR>": "Today is Thursday, October 20th-But itdefnifly feels like a friday. I'm alreadyconsarding making a glend cup ofcoffee-and I have a problem?Somitimes I'll flip through older notes livetalkin and my handwning is unrecognutable,perhaps it depends on the type of per I use?I've thied writing in all caps But IT LOOKS soFORCED AND UNNATURALCopen times, I'm just take notes on myLaptops, but I still seem to gramtate towardpen and paper. Amy advance on what toI'm prune? I already feel stressed at 100kingbank at what I've just written-it looks like3 different people wrote this !!"
}
```
2.25s

╭────────────┬──────────────────────────────┬───────┬───────────────────────────────────────────────────┬─────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                        │ Task  │ Base Command                                      │ Extra Args                              │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────────────────────┼───────┼───────────────────────────────────────────────────┼─────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ microsoft/florence-2-base-ft │ det   │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"od"}' │ 1.91s │ 115ms │ 1.81s │ 2.03s │ 0.52x │  0.0 │ 3.86 Mbps │
╰────────────┴──────────────────────────────┴───────┴───────────────────────────────────────────────────┴─────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
{
  "<OD>": {
    "bboxes": [
      [
        27.904001235961914,
        129.21600341796875,
        477.4400329589844,
        296.2560119628906
      ]
    ],
    "labels": [
      "car"
    ]
  }
}
```
1.81s • 38.2 KB • 21.1 KB/s

╭────────────┬─────────────────────┬───────┬───────────────────────────────────────────────────┬──────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model               │ Task  │ Base Command                                      │ Extra Args                                   │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼─────────────────────┼───────┼───────────────────────────────────────────────────┼──────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ vikhyatk/moondream2 │ cap   │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"caption"}' │ 2.48s │ 89.8ms │ 2.40s │ 2.58s │ 0.40x │  0.0 │ 2.97 Mbps │
╰────────────┴─────────────────────┴───────┴───────────────────────────────────────────────────┴──────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```text
A vintage light blue Volkswagen Beetle is parked parallel to a yellow building with a wooden door. The car's roof and side panels are a slightly darker shade of blue/teal. The building features a brown wooden door and has light beige or cream colored stucco or plaster. The street is paved with grey/light brown stone or brick.  There is a small patch of green vegetation visible behind the building.
```
2.40s • 38.2 KB • 15.9 KB/s

╭────────────┬─────────────────────┬───────┬───────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model               │ Task  │ Base Command                                      │ Extra Args                                                                     │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼─────────────────────┼───────┼───────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ vikhyatk/moondream2 │ det   │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"detect","method_params":{"object":"bench"}}' │ 1.95s │ 34.2ms │ 1.93s │ 1.99s │ 0.51x │  0.0 │ 3.78 Mbps │
╰────────────┴─────────────────────┴───────┴───────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
{
  "objects": []
}
```
1.93s • 38.2 KB • 19.8 KB/s

╭────────────┬───────────────────┬───────┬───────────────────────────────────────────────────┬─────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model             │ Task  │ Base Command                                      │ Extra Args                              │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼───────────────────┼───────┼───────────────────────────────────────────────────┼─────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ qwen/qwen3.5-0.8b │ cap   │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'Describe this image briefly.' │ 2.62s │ 54.5ms │ 2.59s │ 2.69s │ 0.38x │  0.0 │ 2.81 Mbps │
╰────────────┴───────────────────┴───────┴───────────────────────────────────────────────────┴─────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```text
This image captures a charming, vintage-style scene featuring a classic Volkswagen Beetle, painted in a soft mint green, parked on a paved street. The car is positioned in front of a weathered, yellowish wall with two wooden doors, one of which is slightly ajar, revealing a glimpse of the interior. The setting appears to be a quiet residential or small-town street, with the textured pavement and the rustic architecture contributing to a nostalgic, timeless atmosphere. The composition is simple and focused, emphasizing the timeless appeal of the vehicle and its surroundings.
```
2.59s • 38.2 KB • 14.7 KB/s

╭────────────┬───────────────────┬───────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model             │ Task  │ Base Command                                      │ Extra Args                                                                          │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────────┼───────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼────────────┤
│ model      │ qwen/qwen3.5-0.8b │ cap   │ mm cat <vid> --mode fast --no-cache --format json │ --prompt 'Summarise what happens in this video in one sentence.'                    │ 4.90s │ 249ms │ 4.67s │ 5.17s │ 51.5x │  5.7 │ 27.33 Gbps │
│            │                   │       │                                                   │ --generate.extra-body                                                               │       │       │       │       │       │      │            │
│            │                   │       │                                                   │ '{"video_fps":0.4,"video_max_frames":8,"video_resolution":"448x336"}'               │       │       │       │       │       │      │            │
╰────────────┴───────────────────┴───────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴────────────╯
args: {"vid": "bakery.mp4", "mode": "fast"}
```text
Based on the visual evidence across the five images, here is the summary of the video's content:

The video is a montage of scenes from a bakery, focusing on its history and operations. It begins with a collage of historical photos showing the bakery's past, including a fire incident and a family portrait, establishing its legacy. The video then transitions to a modern, clean interior of the bakery, where staff in white uniforms and hairnets are seen working in a well-lit, organized environment. The final shot displays the Google logo, indicating that the video was likely generated using the Google search engine.
```
4.67s • 28.0 MB • 6.0 MB/s

╭────────────┬───────────────────┬───────┬─────────────────────────────────────────────────────────┬──────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model             │ Task  │ Base Command                                            │ Extra Args                           │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────────┼───────┼─────────────────────────────────────────────────────────┼──────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼────────────┤
│ model      │ qwen/qwen3.5-0.8b │ cap   │ mm cat <img> <img> --mode fast --no-cache --format json │ --prompt 'Compare these two images.' │ 4.96s │ 202ms │ 4.73s │ 5.11s │ 0.40x │  0.0 │ 12.56 Mbps │
╰────────────┴───────────────────┴───────┴─────────────────────────────────────────────────────────┴──────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴────────────╯
args: {"img": ["1-vqa-car.jpg", "invoice.jpg"], "mode": "fast"}
```json
[
  "Picture 1: A vintage, light teal Volkswagen Beetle is parked on a paved street in front of a weathered, yellow wall. The car features classic chrome bumpers, whitewall tires, and a distinctively rounded, bulbous body shape. Behind the car, there are two wooden doors with arched tops, one of which is partially obscured by the vehicle. The scene is bathed in soft, natural light, highlighting the car's glossy paint and the texture of the building.\n\nPicture 2: A close-up shot focuses on the front and side of a vintage Volkswagen Beetle. The car's light teal paint is highly reflective, catching the light to create bright highlights and deep shadows that emphasize its curved lines and metallic chrome details. The front grille and headlights are visible, showing the classic VW emblem. The background is a slightly out-of-focus yellow wall, which helps to draw attention to the sharp details of the car itself.",
  "Here is a detailed comparison of the two images, focusing on their content, layout, and the specif
... [876 bytes truncated]
```
4.73s • 182.1 KB • 38.5 KB/s

╭────────────┬───────────────────┬───────┬───────────────────────────────────────────────────┬───────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model             │ Task  │ Base Command                                      │ Extra Args                │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼───────────────────┼───────┼───────────────────────────────────────────────────┼───────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ qwen/qwen3.5-0.8b │ ocr   │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'OCR this image' │ 2.64s │ 278ms │ 2.36s │ 2.91s │ 0.38x │  0.0 │ 2.79 Mbps │
╰────────────┴───────────────────┴───────┴───────────────────────────────────────────────────┴───────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```text
I cannot see any image in the provided text.

However, I can certainly describe the image you provided.

Based on the visual content, here is a detailed breakdown of the scene:

**Subject:**
The main subject is a classic, two-door Volkswagen Beetle. It is painted in a soft, mint-green or aquamarine color. The car features chrome bumpers, a silver hood, and distinctive round headlights. The wheels are fitted with whitewall tires and silver hubcaps.

**Setting:**
The car is parked on a paved surface, likely a cobblestone street or a plaza, which has a light gray or beige color. Behind the car is a weathered, yellowish-beige wall.

**Architecture:**
The wall features two distinct wooden doors.
*   **Left Door:** This door has a simple, vertical wooden frame and a dark, arched window in the center.
*   **Right Door:** This door is framed by a white border and features a similar dark, arched window.

**Background:**
At the very top of the image, above the wall, there is a glimpse of green foliage, suggesting the s
... [46 bytes truncated]
```
2.91s • 38.2 KB • 13.1 KB/s

╭────────────┬──────────────────────┬───────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                │ Task  │ Base Command                                      │ Extra Args                                  │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────────────┼───────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ roboflow/rfdetr-nano │ det   │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"detect"}' │ 1.97s │ 187ms │ 1.83s │ 2.18s │ 0.51x │  0.0 │ 3.74 Mbps │
╰────────────┴──────────────────────┴───────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
{
  "detections": [
    {
      "bbox_xyxy": [
        30.127044677734375,
        128.95506286621094,
        465.9603271484375,
        297.70526123046875
      ],
      "label": "car",
      "confidence": 0.9583,
      "class_id": 3
    }
  ],
  "count": 1
}
```
1.83s • 38.2 KB • 20.9 KB/s

╭────────────┬──────────────────────────┬───────┬───────────────────────────────────────────────────┬──────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                    │ Task  │ Base Command                                      │ Extra Args                                   │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────────────────┼───────┼───────────────────────────────────────────────────┼──────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ roboflow/rfdetr-seg-nano │ seg   │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"segment"}' │ 2.02s │ 88.8ms │ 1.94s │ 2.12s │ 0.50x │  0.0 │ 3.65 Mbps │
╰────────────┴──────────────────────────┴───────┴───────────────────────────────────────────────────┴──────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```json
{
  "detections": [
    {
      "bbox_xyxy": [
        29.09161376953125,
        129.51760864257812,
        466.57952880859375,
        297.937744140625
      ],
      "label": "car",
      "confidence": 0.9628,
      "class_id": 3,
      "mask_png": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAgAAAAGACAAAAAD+S4VjAAAF9klEQVR4nO3dy3LbOBAFUHgq///LnkXsclLRgwQbQDd4zmoWtgT0vYQoxfa0BgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACwzMfqBcT7PPh1G269wyZTOBr6a5sM45TKe45J/YnKgzmj5D6HJv+3kvM5o9oGJ2b/rdqIzqm0uwXhf6s0pnOq7Gxh+F+qTOqkCttaH/5vFWZ1WvpNZUm/tVZgWucl31Kq+Fv6cXXIvKNs6beWe15d0m4oY/qtJR5Yp6T7yRp/SzuxXr9WL+CBxOnv57/VC/hX8vyTL++sdAdagfmmm9kVyTZTIP6WbmiXpNpLjfhbsqldk+gmsEz8W8lzE1gp/0prfSPLCbDRSGtJcgJUy7/aep9LcTtTcZwpBhcgwwlQMf9tJChAzfxrrvpf6wuwyySLWv1SVjj+1aOLsfgEKJx/6bX/WFuAPWZY2tICFM+/+PJ/W1mALQZY3cIC1M+//g4W3sruMLwd3gmsOgH2yH8DiwqwS/7197GmAPXn9q38TpYUoPzUNrLgLmaz+IvfB84/ATbLv/p+pheg+LweqL2j2QWoPa3HSu9p7itY6VG9UPg+YOrSd82/Fa7AzIVvnH8rW4F5y947/taKVmDaovfP/0uxGkxa7m3i/1amBnMW
... [1,391 bytes truncated]
```
2.12s • 38.2 KB • 18.0 KB/s

╭────────────┬───────────────────────────────────┬───────┬────────────────────────────────────────────────────┬───────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬─────╮
│ Group      │ Model                             │ Task  │ Base Command                                       │ Extra Args                                │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │ bps │
├────────────┼───────────────────────────────────┼───────┼────────────────────────────────────────────────────┼───────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼─────┤
│ model      │ usyd-community/vitpose-plus-small │ pose  │ mm cat <file> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"pose"}' │ 2.29s │ 140ms │ 2.18s │ 2.45s │     — │    — │   — │
╰────────────┴───────────────────────────────────┴───────┴────────────────────────────────────────────────────┴───────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴─────╯
args: {"mode": "fast"}
```json
{
  "persons": [
    {
      "bbox_xyxy": [
        305.6180419921875,
        160.8521728515625,
        375.07598876953125,
        313.5617980957031
      ],
      "keypoints": [
        {
          "name": "nose",
          "xy": [
            346.0057373046875,
            206.3638916015625
          ],
          "score": 0.8838
        },
        {
          "name": "left_eye",
          "xy": [
            347.92462158203125,
            207.47018432617188
          ],
          "score": 0.9236
        },
        {
          "name": "right_eye",
          "xy": [
            347.52655029296875,
            206.01318359375
          ],
          "score": 0.997
        },
        {
          "name": "left_ear",
          "xy": [
            349.5863037109375,
            214.61541748046875
          ],
          "score": 0.9123
        },
        {
          "name": "right_ear",
          "xy": [
            346.6328125,
            209.67987060546875
          ],
          "score": 0.7188
        },
... [20,655 bytes truncated]
```
2.45s

╭────────────┬────────────────────┬───────┬────────────────────────────────────────────────────┬──────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬─────╮
│ Group      │ Model              │ Task  │ Base Command                                       │ Extra Args                               │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │ bps │
├────────────┼────────────────────┼───────┼────────────────────────────────────────────────────┼──────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼─────┤
│ model      │ paddleocr/pp-ocrv5 │ ocr   │ mm cat <file> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"ocr"}' │ 1.90s │ 68.5ms │ 1.82s │ 1.95s │     — │    — │   — │
╰────────────┴────────────────────┴───────┴────────────────────────────────────────────────────┴──────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴─────╯
args: {"mode": "fast"}
```json
{
  "regions": [
    {
      "text": "fisot. Do I havex, a probler?",
      "score": 0.8206,
      "poly": [
        [
          64.0,
          101.0
        ],
        [
          359.0,
          105.0
        ],
        [
          359.0,
          125.0
        ],
        [
          64.0,
          121.0
        ]
      ],
      "bbox_xyxy": [
        64.0,
        101.0,
        359.0,
        125.0
      ]
    },
    {
      "text": "FORCED AND UNNATURAL",
      "score": 0.9555,
      "poly": [
        [
          58.0,
          176.0
        ],
        [
          306.0,
          179.0
        ],
        [
          306.0,
          197.0
        ],
        [
          58.0,
          194.0
        ]
      ],
      "bbox_xyxy": [
        58.0,
        176.0,
        306.0,
        197.0
      ]
    },
    {
      "text": "Crten times, lill just take notes on my",
      "score": 0.8827,
      "poly": [
        [
          71.0,
          191.0
        ],
        [
          461.0,
          192.0
... [2,394 bytes truncated]
```
1.82s

╭────────────┬────────────────────┬───────┬────────────────────────────────────────────────────┬─────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬─────╮
│ Group      │ Model              │ Task  │ Base Command                                       │ Extra Args                                  │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │ bps │
├────────────┼────────────────────┼───────┼────────────────────────────────────────────────────┼─────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼─────┤
│ model      │ paddleocr/pp-ocrv5 │ ocr   │ mm cat <file> --mode fast --no-cache --format json │ --generate.extra-body '{"method":"detect"}' │ 1.88s │ 117ms │ 1.77s │ 2.00s │     — │    — │   — │
╰────────────┴────────────────────┴───────┴────────────────────────────────────────────────────┴─────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴─────╯
args: {"mode": "fast"}
```json
{
  "regions": [
    {
      "poly": [
        [
          64.0,
          101.0
        ],
        [
          359.0,
          105.0
        ],
        [
          359.0,
          125.0
        ],
        [
          64.0,
          121.0
        ]
      ],
      "bbox_xyxy": [
        64.0,
        101.0,
        359.0,
        125.0
      ]
    },
    {
      "poly": [
        [
          58.0,
          176.0
        ],
        [
          306.0,
          179.0
        ],
        [
          306.0,
          197.0
        ],
        [
          58.0,
          194.0
        ]
      ],
      "bbox_xyxy": [
        58.0,
        176.0,
        306.0,
        197.0
      ]
    },
    {
      "poly": [
        [
          71.0,
          191.0
        ],
        [
          461.0,
          192.0
        ],
        [
          461.0,
          214.0
        ],
        [
          71.0,
          212.0
        ]
      ],
      "bbox_xyxy": [
        71.0,
        191.0,
        461.0,
        214.0
      ]
... [1,755 bytes truncated]
```
1.88s

╭────────────┬─────────────────────────────────────┬───────┬───────────────────────────────────────────────────┬─────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                               │ Task  │ Base Command                                      │ Extra Args                              │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼─────────────────────────────────────┼───────┼───────────────────────────────────────────────────┼─────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ ggml-org/smolvlm-256m-instruct-gguf │ cap   │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'Describe this image briefly.' │ 2.22s │ 54.2ms │ 2.16s │ 2.26s │ 0.45x │  0.0 │ 3.32 Mbps │
╰────────────┴─────────────────────────────────────┴───────┴───────────────────────────────────────────────────┴─────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```text
This image shows a blue vintage car parked on a paved road. The car is painted in a bright, pastel color, which gives it a cheerful and inviting appearance. The car has a sleek design, with a long hood and a short trunk. The tires are large and round, and the car has a classic design. The roof of the car is painted in a light blue color, and the door is brown. The car is parked in front of a building made of light-colored stone or concrete. The building has a simple, utilitarian design, with a few wooden doors and windows. The windows are small and rectangular, and they are painted in a light brown color. The building has a simple, utilitarian design, with a few wooden doors and windows. The building is simple and utilitarian, with a few wooden doors and windows. The building has a simple, utilitarian design, with a few wooden doors and windows. The building has a simple, utilitarian design, with a few wooden doors and windows.
```
2.16s • 38.2 KB • 17.7 KB/s

╭────────────┬────────────────────────────────────────────┬───────┬───────────────────────────────────────────────────┬───────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                                      │ Task  │ Base Command                                      │ Extra Args                        │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼────────────────────────────────────────────┼───────┼───────────────────────────────────────────────────┼───────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ ggml-org/smolvlm2-256m-video-instruct-gguf │ cap   │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'What is in this image?' │ 2.06s │ 43.0ms │ 2.01s │ 2.09s │ 0.49x │  0.0 │ 3.58 Mbps │
╰────────────┴────────────────────────────────────────────┴───────┴───────────────────────────────────────────────────┴───────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```text
The image features a vintage car parked on a street, with a yellow building in the background. The car is a light blue color, and it has a distinctive design with a rounded front end and a rounded rear end. The car is parked on a paved road, and there are no other cars or people in the scene. The building in the background has a wooden door and a window, and there are trees and bushes in the background as well.
```
2.01s • 38.2 KB • 19.0 KB/s

╭────────────┬────────────────────────────────────────────┬───────┬───────────────────────────────────────────────────┬─────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                                      │ Task  │ Base Command                                      │ Extra Args                              │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼────────────────────────────────────────────┼───────┼───────────────────────────────────────────────────┼─────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼───────────┤
│ model      │ ggml-org/smolvlm2-500m-video-instruct-gguf │ cap   │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'Describe this image briefly.' │ 2.12s │ 112ms │ 1.99s │ 2.20s │ 0.47x │  0.0 │ 3.48 Mbps │
╰────────────┴────────────────────────────────────────────┴───────┴───────────────────────────────────────────────────┴─────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```text
A vintage green Volkswagen Beetle sits parked on a cobblestone street, its classic design and vibrant color contrasting with the muted tones of the surrounding buildings. The car's two-tone paint job and chrome accents add a touch of nostalgia to the scene. The building behind the car, painted in a light yellow color, stands out against the backdrop of the street. The image captures a moment of quiet reflection, as if the car has been parked for a while, waiting for its next adventure.
```
2.16s • 38.2 KB • 17.6 KB/s

╭────────────┬───────────────────┬───────┬───────────────────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model             │ Task  │ Base Command                                      │ Extra Args                                                                        │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼───────────────────┼───────┼───────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ image-res  │ qwen/qwen3.5-0.8b │ cap   │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'Describe the image in 1 sentence.' --encode.strategy_opts max_width=512 │ 2.41s │ 47.8ms │ 2.36s │ 2.45s │ 0.42x │  0.0 │ 3.06 Mbps │
╰────────────┴───────────────────┴───────┴───────────────────────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```text
Picture 1: A vintage light blue Volkswagen Beetle is parked on a paved street in front of a yellow wall with two wooden doors.
```
2.41s • 38.2 KB • 15.8 KB/s

╭────────────┬───────────────────┬───────┬───────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model             │ Task  │ Base Command                                      │ Extra Args                                                                         │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼───────────────────┼───────┼───────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ image-res  │ qwen/qwen3.5-0.8b │ cap   │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'Describe the image in 1 sentence.' --encode.strategy_opts max_width=1024 │ 2.59s │ 52.2ms │ 2.54s │ 2.64s │ 0.39x │  0.0 │ 2.85 Mbps │
╰────────────┴───────────────────┴───────┴───────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```text
This image captures a classic Volkswagen Beetle parked on a paved street in front of a weathered, yellow wall with two wooden doors. The car's light teal paint contrasts with the darker tones of the building, while its chrome wheels and rounded body reflect the ambient light.
```
2.64s • 38.2 KB • 14.4 KB/s

╭────────────┬───────────────────┬───────┬───────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model             │ Task  │ Base Command                                      │ Extra Args                                                                         │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼───────────────────┼───────┼───────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼───────────┤
│ image-res  │ qwen/qwen3.5-0.8b │ cap   │ mm cat <img> --mode fast --no-cache --format json │ --prompt 'Describe the image in 1 sentence.' --encode.strategy_opts max_width=1536 │ 2.58s │ 105ms │ 2.47s │ 2.68s │ 0.39x │  0.0 │ 2.85 Mbps │
╰────────────┴───────────────────┴───────┴───────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```text
This image captures a classic Volkswagen Beetle parked on a paved street in front of a weathered, yellow wall with two wooden doors. The car's light blue paint contrasts with the earthy tones of the building, while its chrome wheels and rounded design stand out against the textured pavement.
```
2.68s • 38.2 KB • 14.2 KB/s

╭────────────┬───────────────────┬───────┬───────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model             │ Task  │ Base Command                                      │ Extra Args                                                                         │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────────┼───────┼───────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼────────────┤
│ video-fra… │ qwen/qwen3.5-0.8b │ cap   │ mm cat <vid> --mode fast --no-cache --format json │ --prompt 'Summarise what happens in this video in one sentence.'                   │ 5.06s │ 42.6ms │ 5.02s │ 5.10s │ 50.0x │  5.5 │ 26.51 Gbps │
│            │                   │       │                                                   │ --generate.extra-body '{"video_fps":0.5,"video_max_frames":4}'                     │       │        │       │       │       │      │            │
╰────────────┴───────────────────┴───────┴───────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴────────────╯
args: {"vid": "bakery.mp4", "mode": "fast"}
```text
Based on the visual evidence across the five images, here is the summary of the video:

The video chronicles the history of a bakery in McKees Rocks, Pennsylvania, focusing on its transition from a historic, fire-damaged site to a modern, operational facility.

*   **Historical Context:** The video begins by showing the bakery's past, including its location on "Baker's Block" and its history as a "Baker's Warehouse." It features archival footage of the building's original state, including a fire that destroyed the complex and a historical photograph of the bakery's original owner.
*   **Modern Operations:** The narrative then shifts to the current state of the business. It shows the modernized interior, including a "Welcome to McKees Rocks" sign and a map of the area.
*   **Production Process:** The final segment displays the day-to-day operations of the bakery, showing staff in white uniforms and hairnets working in a clean, organized environment. This includes scenes of baking, handling dough, and the use o
... [92 bytes truncated]
```
5.10s • 28.0 MB • 5.5 MB/s

╭────────────┬───────────────────┬───────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model             │ Task  │ Base Command                                      │ Extra Args                                                                          │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────────┼───────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼────────────┤
│ video-fra… │ qwen/qwen3.5-0.8b │ cap   │ mm cat <vid> --mode fast --no-cache --format json │ --prompt 'Summarise what happens in this video in one sentence.'                    │ 5.02s │ 130ms │ 4.88s │ 5.13s │ 50.3x │  5.6 │ 26.70 Gbps │
│            │                   │       │                                                   │ --generate.extra-body '{"video_fps":1.0,"video_max_frames":8}'                      │       │       │       │       │       │      │            │
╰────────────┴───────────────────┴───────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴────────────╯
args: {"vid": "bakery.mp4", "mode": "fast"}
```text
Based on the visual evidence across the five images, here is the summary of the video:

The video chronicles the history of a bakery in McKees Rocks, Pennsylvania, focusing on its transition from a historic, fire-damaged site to a modern, operational facility.

*   **Historical Context:** The video begins by showing the bakery's past, including its location in the "Baker's Block" and its history as a "Baker's Wood Marketplace." It features black-and-white footage of the original building and a map of the area.
*   **The Incident:** A significant portion of the video documents the "Fire damages bakery complex" event, showing the aftermath of a five-alarm blaze that caused heavy damage and loss of life.
*   **Modern Operations:** The narrative shifts to the current state of the business. It shows modern employees in white coats and hairnets working in a clean, organized environment.
*   **Conclusion:** The video concludes with a modern view of the bakery's exterior, marked by "Welcome to McKees Rocks," and disp
... [95 bytes truncated]
```
4.88s • 28.0 MB • 5.7 MB/s

╭────────────┬───────────────────┬───────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model             │ Task  │ Base Command                                      │ Extra Args                                                                          │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────────┼───────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼────────────┤
│ video-fra… │ qwen/qwen3.5-0.8b │ cap   │ mm cat <vid> --mode fast --no-cache --format json │ --prompt 'Summarise what happens in this video in one sentence.'                    │ 5.20s │ 197ms │ 5.00s │ 5.39s │ 48.6x │  5.4 │ 25.79 Gbps │
│            │                   │       │                                                   │ --generate.extra-body '{"video_fps":2.0,"video_max_frames":16}'                     │       │       │       │       │       │      │            │
╰────────────┴───────────────────┴───────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴────────────╯
args: {"vid": "bakery.mp4", "mode": "fast"}
```text
Based on the visual evidence across the five images, here is the summary of the video:

The video chronicles the history of a bakery in McKees Rocks, Pennsylvania, focusing on its transformation from a small, traditional establishment to a modern, tech-enabled operation.

*   **Historical Context:** The video begins by establishing the bakery's origins through a collage of black-and-white photographs. These images depict the early days of the business, showing its location on "Baker's Block," its original name, and the historical context of the fire that destroyed the "Baker's Bakery" complex in 1998.
*   **Modern Operations:** The narrative then shifts to the current state of the business. A modern collage shows the interior of the facility, featuring stainless steel counters, automated machinery, and a "Welcome to McKees Rocks" sign.
*   **Technology and Staff:** The final segment highlights the modern workforce and technology. It shows employees in white uniforms and hairnets working at various stations, i
... [208 bytes truncated]
```
5.00s • 28.0 MB • 5.6 MB/s

╭────────────┬───────────────────┬───────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────────────┬───────┬───────┬───────┬───────┬───────┬──────┬─────────────╮
│ Group      │ Model             │ Task  │ Base Command                                      │ Extra Args                                          │  Mean │  ±Std │   Min │   Max │ Speed │ MB/s │         bps │
├────────────┼───────────────────┼───────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────┼───────┼───────┼───────┼───────┼───────┼──────┼─────────────┤
│ cache      │ qwen/qwen3.5-0.8b │ llm   │ mm cat <doc> --mode fast --no-cache --format json │ --prompt 'Summarize this document in one sentence.' │ 7.82s │ 300ms │ 7.50s │ 8.10s │ 0.13x │  0.0 │ 356.98 kbps │
╰────────────┴───────────────────┴───────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────────────┴───────┴───────┴───────┴───────┴───────┴──────┴─────────────╯
args: {"doc": "BillDownload-8pg.pdf", "mode": "fast"}
```text
This document is a 2024 statement from SEAWORLD PARKS & ENTERTAINMENT LLC showing a bill of $342,775.48 due on October 18, 2024, with a credit balance of $0.00 and monthly usage ranging from 0 to 3,900,000 kWh.

---

This document summarizes the charges for three service addresses (33806 SAINT JOE RD, GILMORE/#578/.2S, and 33806 SAINT JOE RD) for the 33rd billing period, detailing the meter readings, usage amounts, and percentages for each account.

---

This document summarizes the monthly energy usage charges for three service addresses in GILMORE, DADE CITY, FL, detailing the current and previous meter readings, total kWh used, and corresponding amounts billed for each account.

---

This document summarizes the monthly energy usage charges for three service addresses in Tampa, FL, detailing the specific meter readings, kWh totals, and corresponding amounts for each account.

---

This document summarizes the monthly energy usage charges for three different service addresses in Tampa, FL, detailing the spe
... [903 bytes truncated]
```
7.50s • 340.8 KB • 45.4 KB/s

╭────────────┬───────────────────┬───────┬────────────────────────────────────────┬─────────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬────────────╮
│ Group      │ Model             │ Task  │ Base Command                           │ Extra Args                                          │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │        bps │
├────────────┼───────────────────┼───────┼────────────────────────────────────────┼─────────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼────────────┤
│ cache      │ qwen/qwen3.5-0.8b │ llm   │ mm cat <doc> --mode fast --format json │ --prompt 'Summarize this document in one sentence.' │ 136ms │ 3.18ms │ 133ms │ 139ms │ 7.37x │  2.5 │ 20.59 Mbps │
╰────────────┴───────────────────┴───────┴────────────────────────────────────────┴─────────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴────────────╯
args: {"doc": "BillDownload-8pg.pdf", "mode": "fast"}
```text
This document is a 2024 statement from SEAWORLD PARKS & ENTERTAINMENT LLC showing a bill of $342,775.48 due on October 18, 2024, with a credit balance of $0.00 and monthly usage ranging from 0 to 3,900,000 kWh.

---

This document summarizes the charges for three service addresses (33806 SAINT JOE RD, GILMORE/#578/.2S, and 33806 SAINT JOE RD) for the 33rd billing period, detailing the meter readings, usage amounts, and percentages for each account.

---

This document summarizes the monthly energy usage charges for three service addresses in GILMORE, DADE CITY, FL, detailing the current and previous meter readings, total kWh used, and corresponding amounts billed for each account.

---

This document summarizes the monthly energy usage charges for three service addresses in Tampa, FL, detailing the specific meter readings, kWh totals, and corresponding amounts for each account.

---

This document summarizes the monthly energy usage charges for three different service addresses in Tampa, FL, detailing the spe
... [903 bytes truncated]
```
134ms • 340.8 KB • 2.5 MB/s

╭────────────┬────────────────────────┬───────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                  │ Base Command                                      │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼────────────────────────┼───────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ 404        │ vlm-run/nonexistent-v0 │ mm cat <img> --mode fast --no-cache --format json │ 820ms │ 33.7ms │ 796ms │ 858ms │ 1.22x │  0.0 │ 9.00 Mbps │
╰────────────┴────────────────────────┴───────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```text
[LLM error: Error code: 404 - {'detail': {'error': {'message': "Model 'vlm-run/nonexistent-v0' not found. Available: ['Qwen/Qwen3.5-0.8B', 'facebook/sam3', 'fastino/gliner2-multi-v1', 'ggml-org/SmolVLM-256M-Instruct-GGUF', 'ggml-org/SmolVLM2-256M-Video-Instruct-GGUF', 'ggml-org/SmolVLM2-500M-Video-Instruct-GGUF', 'ggml-org/smolvlm-256m-instruct-gguf', 'ggml-org/smolvlm2-256m-video-instruct-gguf', 'ggml-org/smolvlm2-500m-video-instruct-gguf', 'microsoft/Florence-2-base-ft', 'microsoft/florence-2-base-ft', 'paddleocr/pp-ocrv5', 'qwen/qwen3.5-0.8b', 'rednote-hilab/dots.ocr', 'roboflow/rfdetr-nano', 'roboflow/rfdetr-seg-nano', 'usyd-community/vitpose-plus-small', 'vikhyatk/moondream2']", 'type': 'model_not_found', 'code': None, 'param': None}}}]
```
796ms • 38.2 KB • 47.9 KB/s

╭────────────┬──────────────────────────────────┬───────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                            │ Base Command                                      │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼──────────────────────────────────┼───────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ 404        │ microsoft/florence-2-NONEXISTENT │ mm cat <img> --mode fast --no-cache --format json │ 789ms │ 13.9ms │ 775ms │ 803ms │ 1.27x │  0.0 │ 9.34 Mbps │
╰────────────┴──────────────────────────────────┴───────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```text
[LLM error: Error code: 404 - {'detail': {'error': {'message': "Model 'microsoft/florence-2-NONEXISTENT' not found. Available: ['Qwen/Qwen3.5-0.8B', 'facebook/sam3', 'fastino/gliner2-multi-v1', 'ggml-org/SmolVLM-256M-Instruct-GGUF', 'ggml-org/SmolVLM2-256M-Video-Instruct-GGUF', 'ggml-org/SmolVLM2-500M-Video-Instruct-GGUF', 'ggml-org/smolvlm-256m-instruct-gguf', 'ggml-org/smolvlm2-256m-video-instruct-gguf', 'ggml-org/smolvlm2-500m-video-instruct-gguf', 'microsoft/Florence-2-base-ft', 'microsoft/florence-2-base-ft', 'paddleocr/pp-ocrv5', 'qwen/qwen3.5-0.8b', 'rednote-hilab/dots.ocr', 'roboflow/rfdetr-nano', 'roboflow/rfdetr-seg-nano', 'usyd-community/vitpose-plus-small', 'vikhyatk/moondream2']", 'type': 'model_not_found', 'code': None, 'param': None}}}]
```
789ms • 38.2 KB • 48.4 KB/s

╭────────────┬─────────────────────────────┬───────────────────────────────────────────────────┬───────┬────────┬───────┬───────┬───────┬──────┬───────────╮
│ Group      │ Model                       │ Base Command                                      │  Mean │   ±Std │   Min │   Max │ Speed │ MB/s │       bps │
├────────────┼─────────────────────────────┼───────────────────────────────────────────────────┼───────┼────────┼───────┼───────┼───────┼──────┼───────────┤
│ 404        │ paddlepaddle/paddleocr-v999 │ mm cat <img> --mode fast --no-cache --format json │ 814ms │ 64.3ms │ 773ms │ 888ms │ 1.23x │  0.0 │ 9.06 Mbps │
╰────────────┴─────────────────────────────┴───────────────────────────────────────────────────┴───────┴────────┴───────┴───────┴───────┴──────┴───────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```text
[LLM error: Error code: 404 - {'detail': {'error': {'message': "Model 'paddlepaddle/paddleocr-v999' not found. Available: ['Qwen/Qwen3.5-0.8B', 'facebook/sam3', 'fastino/gliner2-multi-v1', 'ggml-org/SmolVLM-256M-Instruct-GGUF', 'ggml-org/SmolVLM2-256M-Video-Instruct-GGUF', 'ggml-org/SmolVLM2-500M-Video-Instruct-GGUF', 'ggml-org/smolvlm-256m-instruct-gguf', 'ggml-org/smolvlm2-256m-video-instruct-gguf', 'ggml-org/smolvlm2-500m-video-instruct-gguf', 'microsoft/Florence-2-base-ft', 'microsoft/florence-2-base-ft', 'paddleocr/pp-ocrv5', 'qwen/qwen3.5-0.8b', 'rednote-hilab/dots.ocr', 'roboflow/rfdetr-nano', 'roboflow/rfdetr-seg-nano', 'usyd-community/vitpose-plus-small', 'vikhyatk/moondream2']", 'type': 'model_not_found', 'code': None, 'param': None}}}]
```
781ms • 38.2 KB • 48.9 KB/s

╭────────────┬───────────┬───────────────────────────────────────────────────┬────────────────────────────────────┬────────┬────────┬────────┬────────┬───────┬──────┬────────────╮
│ Group      │ Model     │ Base Command                                      │ Extra Args                         │   Mean │   ±Std │    Min │    Max │ Speed │ MB/s │        bps │
├────────────┼───────────┼───────────────────────────────────────────────────┼────────────────────────────────────┼────────┼────────┼────────┼────────┼───────┼──────┼────────────┤
│ validation │ (default) │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '{not json}' │ 78.7ms │ 3.04ms │ 76.8ms │ 82.2ms │ 12.7x │  0.5 │ 93.64 Mbps │
╰────────────┴───────────┴───────────────────────────────────────────────────┴────────────────────────────────────┴────────┴────────┴────────┴────────┴───────┴──────┴────────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```text
[exit 1]
Error: --generate.extra-body must be a JSON object: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
```
76.8ms • 38.2 KB • 496.6 KB/s

╭────────────┬───────────┬───────────────────────────────────────────────────┬─────────────────────────────────┬────────┬────────┬────────┬────────┬───────┬──────┬────────────╮
│ Group      │ Model     │ Base Command                                      │ Extra Args                      │   Mean │   ±Std │    Min │    Max │ Speed │ MB/s │        bps │
├────────────┼───────────┼───────────────────────────────────────────────────┼─────────────────────────────────┼────────┼────────┼────────┼────────┼───────┼──────┼────────────┤
│ validation │ (default) │ mm cat <img> --mode fast --no-cache --format json │ --generate.extra-body '[1,2,3]' │ 78.7ms │ 0.75ms │ 77.9ms │ 79.4ms │ 12.7x │  0.5 │ 93.64 Mbps │
╰────────────┴───────────┴───────────────────────────────────────────────────┴─────────────────────────────────┴────────┴────────┴────────┴────────┴───────┴──────┴────────────╯
args: {"img": "1-vqa-car.jpg", "mode": "fast"}
```text
[exit 1]
Error: --generate.extra-body must decode to a JSON object, got list
```
79.4ms • 38.2 KB • 480.5 KB/s
