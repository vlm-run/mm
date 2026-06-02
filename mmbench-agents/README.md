# mmbench-agents

An agent-capability benchmark for `mm`: how well do universal assistants
(Claude Code, Codex, Devin, Gemini, OpenClaw, …) accomplish hard, multi-turn,
**action-based** multimodal tasks — **with** and **without** `mm` — across model
`profiles`?

This is distinct from `mm bench` ("mmbench-mini"), which measures the speed of
`mm` itself. mmbench-agents measures the *agent harness*.

> Status: **foundation slice.** This PR lands the data model, a frozen corpus
> with independent ground truth, the task catalogue, and deterministic
> verifiers (all unit-tested). The trial harness, scoring store, and dashboard
> land in follow-up PRs (see Roadmap).

## 1. Layout

```
mmbench-agents/
  mmbench_agents/
    types.py        # trial-matrix axes + VerifierReport
    dataset.py      # deterministic corpus + independent ground truth + hash pin
    verifiers.py    # deterministic verifiers (Verifier ABC + concrete checks)
    tasks.py        # TaskSpec + TASKS registry
  dataset/
    ground_truth.json   # frozen, computed by independent tools (committed)
    MANIFEST.json       # dataset_hash pin (committed)
    corpus/             # generated, gitignored (rebuilt from dataset.py)
  tests/                # verifier + dataset-pin unit tests
```

## 2. The trial matrix

A **trial** is the atomic unit: `(assistant, profile, mm_condition, task, repeat)`.

| Axis | Examples | Notes |
|------|----------|-------|
| `assistant` | claude, codex, devin, gemini | the agent harness (its own brain + tool loop) |
| `profile` | gateway, orion-2, openrouter, ollama | `mm`'s LLM backend; `none` for the baseline arm |
| `mm_condition` | `baseline` \| `mm` | baseline = native tools only; mm = `mm` available |
| `task` | the catalogue in `tasks.py` | each ships ground truth + a deterministic verifier |
| `repeat` | 1..R | for variance / `success@k` |

Two sweep modes (`SweepMode`): **profile** (fix assistant, vary profile) and
**assistant** (fix profile, vary assistant). The baseline arm has no `mm`, hence
no profile — it isolates the value of `mm` itself.

## 3. Tasks & verifiers

- Every task ships an **identical-across-arms** prompt that pins the answer JSON
  schema and the kind taxonomy, and **never names an `mm` command** — the agent
  must decide to use `mm`.
- Every task has a **deterministic verifier**: the final answer is checkable
  (counts, sizes, hashes, durations, set membership). A free-text rubric judge
  is layered on later, never overriding a deterministic failure.
- Ground truth is computed by tools **independent of `mm`** (`os.stat`,
  `hashlib`, `wave`) to avoid circularity, then frozen and pinned by hash.

The catalogue starts with three foundational tasks (`manifest`,
`exact_duplicates`, `audio_duration`) and grows toward the full 20-case design.

## 4. Usage

```bash
# Rebuild the frozen corpus and (re)write ground_truth.json + MANIFEST.json
python -m mmbench_agents.dataset freeze

# Verify a checkout reproduces the committed corpus hash + ground truth
python -m mmbench_agents.dataset verify

# Run the unit tests (isolated from mm's own suite)
python -m pytest mmbench-agents
```

## 5. Roadmap

1. **Dataset & GT** — frozen corpus + independent ground truth, pinned. *(this slice)*
2. **Tasks & verifiers** — task specs + deterministic verifiers + rubric judge. *(this slice, ongoing)*
3. **Harness** — sandboxed runner, cache hygiene, profile injection, mm on/off, metric capture; one assistant adapter end-to-end.
4. **Scoring + store** — 6-dimension schema (completion/correctness/grounding + speed) in SQLite.
5. **Sweeps** — orchestrator for the profile and assistant sweeps, resumable + cost-guarded.
6. **App** — FastAPI + Svelte dashboard: leaderboard, mm-uplift, profile/assistant comparisons, trial explorer, trends.
