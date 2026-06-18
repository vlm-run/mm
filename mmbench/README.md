# mmbench

An agent-vs-agent benchmark: does giving an AI agent harness the `mm` CLI make
it more capable and faster at real-world multimodal directory tasks?

Each task runs twice per agent, in its own disposable sandbox copy of a dataset:

- **baseline**: the agent has only its native tools.
- **treatment**: the agent also has `mm` on PATH + a one-page primer.

Both are scored on correctness (deterministic checks + LLM judge) and speed; the
headline is the **lift**. See `DESIGN.md` for the full design.

## Layout

```
mmbench/
├── DESIGN.md            # design, decisions, findings
├── cases/               # eval cases (declarative YAML)
├── dataset/
│   └── build_fixture.py # assembles the nested mmbench-agent fixture
├── harness/
│   ├── cases.py         # typed case model + loader/validator
│   ├── sandbox.py       # per-run disposable working copies
│   ├── assistants.py    # agent-CLI adapters (claude, codex, gemini, ...)
│   ├── grader.py        # checks[] + LLM judge -> correctness
│   ├── store.py         # SQLite results store
│   └── run.py           # orchestrator + CLI
└── app/                 # FastAPI + SQLite dashboard
```

Datasets, sandboxes, and the results DB live under `benchmarks/data/`
(gitignored).

## Usage

**Prereqs:** an agent CLI installed + authed (claude / codex / gemini / opencode
verified; qwen needs its key), the `gateway` mm profile reachable (`mm profile
list`), and `MMBENCH_JUDGE_API_KEY` for the judge. The
fixture **auto-builds** on first run. Preflight checks all of this and aborts on
any failure.

All commands run from the repo root with the package on the path:

```bash
cd <repo root>

# 0. Check your setup is live (pings each assistant/profile/judge, then exits):
uv run python -m mmbench.harness.run --assistants claude,codex,gemini,opencode --check

# 1. Run the benchmark. On first run the fixture auto-builds; preflight then
#    verifies fixture + each agent's autonomy + each profile + the judge, and
#    aborts on any failure (no silent fallbacks).
uv run python -m mmbench.harness.run --assistants claude --profiles gateway

# 2. View the dashboard (filter by assistant/profile to compare any subset)
uv run python -m mmbench.app.app        # http://localhost:9095

# (optional) build/rebuild the fixture explicitly
uv run python mmbench/dataset/build_fixture.py
```

The unit of work is an **(assistant, profile) cell**. A run is the cartesian
product of `--assistants` and `--profiles` (`gateway` is the shared default
profile; team members add their own mm profiles for custom backends):

```bash
# leaderboard across agents on the shared backend:
uv run python -m mmbench.harness.run --assistants claude,codex,gemini,opencode --profiles gateway --runs 3
# full grid: claude,gemini x gateway,my-profile -> 4 cells:
uv run python -m mmbench.harness.run --assistants claude,gemini --profiles gateway,my-profile
# subset of cases + resume an interrupted pass:
uv run python -m mmbench.harness.run --cases retrieve-video-product,invoices-to-csv --resume

ls mmbench/cases/   # list case ids
```

### Flags (`-m mmbench.harness.run`)

| Flag | Default | Meaning |
|---|---|---|
| `--assistants` | `claude` | comma list from `claude,codex,gemini,opencode,qwen,openclaw` (preflight gates whichever you select; uninstalled/unauthed ones fail fast) |
| `--profiles` | `gateway` | comma list of `mm profile` names (the treatment arm's mm backend) |
| `--cases` | all 20 | comma list of case ids |
| `--runs` | `1` | repetitions per cell (`3`+ for variance; dashboard shows mean±std) |
| `--timeout` | `360` | per-agent cap, seconds (keep ≥300; mm's video/PDF paths are slow) |
| `--no-judge` | off | score on deterministic checks only |
| `--resume` | off | reuse latest session per cell, skip completed cells |
| `--keep-sandboxes` | off | keep per-run working copies |
| `--db` | `benchmarks/data/mmbench.db` | results SQLite path |
| `--check` | off | ping the selected assistants/profiles/judge and exit (no run); non-zero exit if any fails |
| `--skip-preflight` | off | bypass preflight (not advised) |

The **judge** is fixed (no profile): OpenRouter + `google/gemini-3.1-flash-lite`,
key from `MMBENCH_JUDGE_API_KEY`  (override model/url via `MMBENCH_JUDGE_MODEL` / `MMBENCH_JUDGE_BASE_URL`). Profiles only set the treatment
arm's mm backend; the baseline arm never touches mm.

## Cases

20 difficult, multi-turn, action-based cases across the three archetypes
(10 retrieval, 6 artifact, 4 organization), grounded in the real content of the
fixture (catalogued with `mm` itself). They span a 15-page paper (deep-PDF QA),
invoices in PDF and image form, a video the baseline cannot watch, OCR at scale
(one container photo among 150+), floor-plan vs not-floor-plan classification,
structured invoice/JSON extraction, and content-based folder organization. Each
names the file(s) / writes the artifact / leaves the tree in a state the grader
checks deterministically, plus an LLM-judge pass.

## Notes

- Agent CLIs run with autonomy flags so non-interactive tool use does not stall;
  preflight verifies each agent live. Verified working: claude
  (`--dangerously-skip-permissions`), codex (`exec --dangerously-bypass-approvals-and-sandbox`),
  gemini/qwen (`--yolo`), opencode (`run`). qwen needs a valid API key. openclaw
  (`-p`) is wired but not installed here, so its autonomy flag is unverified;
  preflight will catch it for whoever has it.
- mm-grounding (which `mm` commands the agent ran) is captured by a PATH-shimmed
  `mm` that logs every invocation; the same shim makes `mm` "command not found"
  in the baseline arm, so the baseline is mm-free by construction.
- The fixture is built only from the three reproducible sources. The keynote
  video in mmbench-mini is corrupt and the audio assets contain no speech, so the
  current suite leans on deep PDF, video, and scale-image tasks for mm's lift.
- `mmbench-agent.manifest.json` (ground-truth labels) is written *outside* the
  fixture dir on purpose, so sandbox copies never leak answers to the agent.
