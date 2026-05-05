---
title: mm-ctx
emoji: 🗂️
colorFrom: indigo
colorTo: pink
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: mm CLI in your browser — multimodal context for agents
---

# mm-ctx

Browser-hosted xterm.js terminal for the
[`mm-ctx`](https://pypi.org/project/mm-ctx/) Python package — a fast,
multimodal context tool for agents on the CLI.

The Space runs a FastAPI server that bridges xterm.js (in your browser)
to a PTY-backed `bash` session via a `/ws/terminal` WebSocket. Every
`mm` command is available exactly as in a local shell:

```
mm find ./mmbench-tiny --tree
mm cat photo.jpg -m fast
mm grep "attention" --kind document
mm sql "SELECT kind, COUNT(*) FROM files GROUP BY kind"
mm profile list
```

## Notes

- The Space pre-loads the
  [`mmbench-tiny`](https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-tiny.tar.gz)
  fixture on first start so you can try `mm cat` / `mm grep` immediately.
- For `accurate` mode you'll need to add an LLM profile
  (`mm profile add ...`) that points at any OpenAI-compatible endpoint
  (Ollama, vLLM, OpenAI, OpenRouter, etc.).
- Audio/video accurate mode runs faster-whisper / CTranslate2; on
  CPU-tier hardware this is functional but slow. Upgrade the Space
  hardware for full speed.
- Source: <https://github.com/vlm-run/mm>
