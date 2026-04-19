# Video Encoder Benchmark

**Date**: 2026-04-18
**Input**: `bakery.mp4` — 252.7s (4m 13s), 28.0 MB, 1280×720, h264+aac, 23.97 fps
**Profile**: `ollama` → gemma4:e2b (Gemma 4, effective 2B)
**Machine**: Apple M3 Max

## Results


| Encoder                               | Time  | Throughput | Extracts                                                                 | Output shape                                             |
| ------------------------------------- | ----- | ---------- | ------------------------------------------------------------------------ | -------------------------------------------------------- |
| `video-chunk`                         | 3.3s  | 8.4 MB/s   | 7 overlapping 60s chunks (20s overlap), 16 frames/chunk                  | `Video chunk 0 (0s – 60s)` × 7                           |
| `frame-sample`                        | 5.6s  | 5.0 MB/s   | 252 frames at 1 fps, batched 16/message                                  | `Video frames from bakery.mp4 (0.0s – 15.0s)` × 16       |
| `mosaic`                              | 7.0s  | 4.0 MB/s   | 75 frames → 5 mosaic grids (4×4 tiles)                                   | `bakery.mp4 (4m13s) — 5 mosaic(s), 4×4 grid, 75 frames`  |
| `shot-frames`                         | 18.0s | 1.6 MB/s   | 76 shots via PySceneDetect, frames per shot                              | `Shot 1/76 of bakery.mp4 (0.0s – 6.8s)` × 76             |
| `shot-mosaic`                         | 33.1s | 866 KB/s   | 76 shots, mosaic grid per shot                                           | `Shot 1/76 of bakery.mp4 (0.0s – 6.8s)` × 76             |
| `video-frames-transcript`             | 91.0s | 315 KB/s   | Whisper transcript (72 segments, 598 words, 77s) + 16 frame batches      | transcript + frames                                      |
| **accurate** (mosaic + Whisper + LLM) | 83.0s | 345 KB/s   | Full pipeline → structured summary, tags, scenes, transcript (869 words) | `## Summary` / `## Tags` / `## Scenes` / `## Transcript` |


## Observations

- **Fastest**: `video-chunk` at 3.3s — splits the timeline with minimal frame extraction.
- **Best visual coverage**: `shot-frames` / `shot-mosaic` detect 76 scene boundaries but cost 3–6× more than uniform sampling.
- **Whisper dominates transcript variants**: ~77s of the 91s `video-frames-transcript` time is Whisper transcription on the 4m 13s video.
- **Accurate mode** runs mosaic + Whisper + LLM inference in 83s total, producing a structured 869-word document with summary, tags, scene breakdown, and full transcript.
- `mosaic` is the sweet spot for encode-only: 75 frames compressed into 5 grid images in 7s.

## Sample output: `video-frames-transcript`

```
Audio transcript of bakery.mp4 (lang=en, model=medium, 77250ms):

[0.9s - 5.9s] The Keys Rocks is the rough-and-tumble area just outside Pittsburgh.
[5.9s - 7.1s] My name's Scott Baker.
[7.1s - 10.7s] My family has been connected with this community for generations.
[10.7s - 16.2s] In 1941, my grandfather opened his bakery here, and he called it Jenny Lee.
[16.2s - 19.7s] We used to always go to Jenny Lee's after church.
[19.7s - 27.1s] If you were good in church, oh, egg custard pies, homemade bread that was still warm.
[27.1s - 29.5s] Years later, I worked in a store.
[29.5s - 32.3s] I did wedding cakes.
[32.3s - 35.9s] My father, Bernie, took over after my grandfather retired.
[35.9s - 38.6s] I am a baker by name, baker by trade.
[38.6s - 42.4s] I started coming into the bakery with my dad when I was seven or eight years old.
[42.4s - 43.8s] Absolutely loved it.
[43.8s - 46.1s] I remember Scott as a young man.
[46.1s - 47.9s] He just jumped in here.
[47.9s - 52.9s] It was a booming time.
[52.9s - 58.5s] We're just coming up the ramp, the McKees Rocks Bridge, around Thanksgiving,
[58.5s - 60.9s] and we heard all the sirens and that.
[60.9s - 64.1s] And my husband said, it's where you work.
[64.1s - 66.9s] And I was like, no.
[66.9s - 69.2s] And he said, it is.
[69.2s - 75.9s] You don't have a job.
[75.9s - 83.6s] I remember pulling up to the bakery and seeing my dad and just the look of despair.
[83.6s - 88.6s] It was my life, my employment.
[88.6s - 93.7s] To see that all go up in smoke was just an overwhelming feeling.
[93.7s - 97.3s] The fire followed by the recession made it really hard to hang on.
[97.3s - 105.7s] And ultimately, the decision was made to close the doors.
[105.7s - 109.2s] After that, I was so frustrated and burnt out.
[109.2s - 112.8s] I said, Scott, you ought to just sell cars, sell furniture.
[112.8s - 114.1s] You can make a very good living.
[114.1s - 118.0s] You don't have all the headaches, but he didn't listen.
[118.0s - 119.9s] I started thinking, baking is in my blood.
[119.9s - 121.0s] It's what we do.
[121.0s - 124.6s] We've been baking in this community for five generations.
[124.6s - 128.6s] I wanted to try and rebuild the business here in McKees Rocks.
[128.6s - 130.8s] So I started looking.
[130.8s - 134.1s] And I learned retail bakeries in today's market are dinosaurs.
[134.1s - 135.8s] People go to supermarkets.
[135.8s - 138.8s] You can find a donut shop on nearly every corner.
[138.8s - 141.6s] So I realized we had to do the baking ourselves
[141.6s - 143.0s] and then sell it to the stores.
[143.0s - 145.8s] But my aha moment was when I learned that one
[145.8s - 152.2s] of the top flavor profiles for sweet goods is cinnamon.
[152.2s - 156.1s] I wanted to manufacture gourmet cinnamon bread.
[156.1s - 159.3s] That would be the foundation of the new business.
[159.3s - 162.4s] And so I founded the Five Generation Bakers
[162.4s - 165.4s] and branded our bread, Jenny Lee Swirl Bread.
[165.4s - 167.2s] But in order to make this thing last,
[167.2s - 169.8s] I had to learn about some of the things my dad didn't have.
[169.8s - 172.3s] So I hired a young kid named Cody.
[172.3s - 174.9s] He spearheaded a digital ad campaign.
[174.9s - 177.7s] And he introduced our product to thousands of new customers
[177.7s - 179.6s] on social media.
[179.6s - 183.6s] Most days, I leave the bakery smelling like cinnamon.
[183.6s - 185.7s] Since then, we have been one of Pittsburgh's fastest
[185.7s - 186.8s] growing companies.
[186.9s - 192.0s] I called him up and I said, I want my job back.
[192.0s - 193.6s] So I hired her on the spot.
[193.6s - 196.4s] And of course, I hired my dad back as well.
[196.4s - 198.2s] When are we going to get the first order?
[198.2s - 200.5s] I'm very proud of him for keeping it going.
[200.5s - 205.8s] He keeps me young.
[205.8s - 208.3s] I feel that we're really blessed to be
[208.3s - 210.2s] able to help the community.
[210.2s - 211.8s] But when you think about it,
[211.8s - 215.7s] really the community has been helping us for a long time.
[215.7s - 219.2s] And I hope it's for another five generations to come.
[219.2s - 221.4s] I'm not good at putting things in the words,
[221.4s - 225.9s] but it makes me proud being back with Scott and Bernie,
[225.9s - 228.2s] making something good again, something
[228.2s - 231.6s] that they could have in every house.
[231.6s - 233.8s] I made that.
[233.8s - 236.1s] I'm proud to say that.

Video frames from bakery.mp4 (0.0s - 15.0s):
Video frames from bakery.mp4 (16.0s - 31.0s):
Video frames from bakery.mp4 (32.0s - 47.0s):
...
Video frames from bakery.mp4 (240.0s - 252.0s):
```

## Sample output: `accurate` (gemma4:e2b)

```
## Summary
This collection of images provides a visual and textual documentation of a bakery
business, likely focusing on its history, operations, and the impact of a significant
event, specifically fire damage. The visuals are dominated by close-ups of baked goods,
rows of product shelves, and portraits of the staff, establishing a theme of
craftsmanship, tradition, and community. The accompanying text and map suggest a
historical context, referencing the "Cinnamon Bakery" and the "Fire damages bakery
complex," framing the images as a historical record of a business facing adversity.
The overall mood is nostalgic and documentary, highlighting the enduring nature of
the bakery despite the disaster.

## Tags
- bakery - history - fire damage - business - baking - staff - storefront - vintage - complex

## Scenes
- Scene 1: Exterior and Context — Depicts the exterior of the bakery, including
  signage ("Welcome to McKees Rocks") and the surrounding landscape, setting the
  historical and geographical context.
- Scene 2: Product Display and Staff Portraits — Focuses on rows of baked goods,
  shelves, and portraits of the bakers and staff, emphasizing the craft and the
  people behind the business.
- Scene 3: Interior Operations and Damage — Shows the interior of the bakery,
  including production areas, shelving, and implied context of the fire damage
  and the complex.
- Scene 4: Product Close-ups — Features detailed shots of various baked products,
  highlighting the quality and variety of the bakery's offerings.
- Scene 5: Historical Context and Map — Includes the map and text overlays, linking
  the visual evidence to the historical event and location of the damage.

## Transcript (598 words)
The Keys Rocks is the rough-and-tumble area just outside Pittsburgh. My name's Scott
Baker. My family has been connected with this community for generations. In 1941, my
grandfather opened his bakery here, and he called it Jenny Lee. ...
```

## CLI commands used

```bash
# Set profile to ollama with gemma4:e2b
mm profile use ollama

# Encode-only (no LLM) — each encoder
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-chunk      --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p frame-sample     --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p mosaic           --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p shot-frames      --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p shot-mosaic      --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-frames-transcript --no-cache

# Full pipeline (encode + Whisper + LLM)
mm cat ~/data/mmbench-tiny/bakery.mp4 -m accurate --no-cache
```
