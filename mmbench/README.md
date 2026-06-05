# mmbench-agents

An agent-capability benchmark for `mm`: how well do universal assistants
(Claude Code, Codex, Devin, Gemini, OpenClaw, …) accomplish hard, multi-turn,
**action-based** multimodal tasks — **with** and **without** `mm` — across model
`profiles`?

This is distinct from `mm bench` ("mmbench-mini"), which measures the speed of
`mm` itself. mmbench-agents measures the *agent harness*: can it wield `mm`'s
action commands (`find`/`sql`/`peek`/`wc`/`grep`/`cat`) to solve a task, and how
much does `mm` help versus native tools alone?

The pipeline is **end-to-end runnable with zero external credentials** via a
deterministic mock adapter, which is what powers the unit tests and the demo
dashboard below. Real assistants plug in through the same adapter interface.

## 1. Layout

```
mmbench-agents/
  mmbench/
    types.py        # trial-matrix axes, Profile/AssistantSpec, Score, TrialResult
    dataset.py      # deterministic corpus + independent ground truth + hash pin
    tasks.py        # TaskSpec + the task catalogue (9 tasks, all six mm commands)
    verifiers.py    # deterministic verifiers (Verifier ABC + concrete checks)
    oracle.py       # reference correct/corrupt answers (mock adapter + tests)
    answers.py      # robust JSON answer extraction from agent output
    judge.py        # optional rubric judge for free-text (NullJudge by default)
    scoring.py      # VerifierReport + failure mode -> Score (0-100)
    adapters/       # AssistantAdapter ABC + registry; mock + cli adapters
    harness.py      # per-trial sandbox, fresh MM_* paths, mm on/off, metrics
    store.py        # SQLite store: runs + idempotent/resumable trial rows
    sweep.py        # orchestrator for the profile and assistant sweeps
    analysis.py     # pure-python leaderboard / uplift / per-task aggregations
    report.py       # static, self-contained Plotly HTML export
    app.py          # FastAPI interactive dashboard (lazy Plotly render)
    __main__.py     # CLI: dataset / run / report / serve
  dataset/
    ground_truth.json   # frozen, computed by independent tools (committed)
    MANIFEST.json       # dataset_hash pin (committed)
    corpus/             # generated, gitignored (rebuilt from dataset.py)
  tests/                # verifier, oracle, answer-parsing, end-to-end pipeline
  requirements.txt      # optional deps for the dashboard (plotly/fastapi/uvicorn)
```

## 2. The trial matrix

A **trial** is the atomic unit: `(assistant, profile, mm_condition, task, repeat)`.

| Axis | Examples | Notes |
|------|----------|-------|
| `assistant` | claude, codex, devin, gemini, mock-strong | the agent harness (its own brain + tool loop) |
| `profile` | gateway, orion-2, openrouter, ollama | `mm`'s LLM backend; `none` for the baseline arm |
| `mm_condition` | `baseline` \| `mm` | baseline = native tools only; mm = `mm` available |
| `task` | the catalogue in `tasks.py` | each ships ground truth + a deterministic verifier |
| `repeat` | 1..R | for variance / `success@k` |

Two sweep modes (`SweepMode`): **profile** (fix assistant, vary profile → tests
the model `mm` calls) and **assistant** (fix profile, vary assistant → the
leaderboard of harnesses). The baseline arm has no `mm`, hence no profile — it
isolates the value of `mm` itself, and the headline metric is **mm-uplift**
(Δcorrectness, Δsuccess, speedup).

## 3. Tasks, verifiers & scoring

- The catalogue ships **9 tasks** spanning all three scopes (file / directory /
  mixed) and collectively exercising all six action commands. Each task's prompt
  is **identical across arms**, pins the answer JSON schema, and **never names an
  `mm` command** — the agent must decide to use `mm`.
- Every task has a **deterministic verifier** (counts, sizes, hashes, durations,
  set membership, substring grounding). A free-text rubric judge (`judge.py`) is
  layered on optionally and never overrides a deterministic failure.
- Ground truth is computed by tools **independent of `mm`** (`os.stat`,
  `hashlib`, `wave`, `pypdfium2`) to avoid circularity, then frozen and pinned by
  `dataset_hash`.
- Scoring (`scoring.py`) collapses the verifier report + failure mode into a
  `Score` with `completion`, `correctness`, `grounding`, optional `rubric`, and a
  normalized `overall` (0–100). Any non-`NONE` failure mode scores zero — no
  silent partial credit.

## 4. Cache isolation

Each trial runs in a throwaway sandbox with fresh `MM_*` paths
(`MM_DATA_DIR`/`MM_DB_PATH`/`MM_CACHE_DIR`/`MM_BLOBS_DIR`), so prior extractions,
embeddings, and the DB-level cache never leak between trials. This relies on the
overridable settings landed in vlm-run/mm#163. The baseline arm additionally
drops `mm` from `PATH`.

## 5. How to test and run the benchmarks

All commands run from the `mmbench-agents/` directory. The core package is
dependency-light; only the dashboard needs the optional extras:

```bash
pip install -r requirements.txt   # plotly + fastapi + uvicorn (dashboard only)
```

### Run the test suite

```bash
python -m pytest mmbench-agents          # from the repo root, or:
cd mmbench-agents && python -m pytest     # verifiers, oracle, answers, end-to-end
```

The end-to-end tests drive the mock adapter through the harness, store, sweep,
and analysis layers — proving sandboxing, scoring, idempotent resume, and the
leaderboard/uplift aggregations without any credentials.

### Freeze / verify the dataset

```bash
python -m mmbench dataset freeze    # rebuild corpus + ground_truth + pin
python -m mmbench dataset verify    # confirm a checkout reproduces the pin
```

### Run a sweep (mock adapter — no credentials needed)

```bash
# Assistant sweep (leaderboard): fix profile, vary assistant
python -m mmbench run --db benchmark.db \
  --assistants mock-strong,mock-weak --repeats 3 \
  --sweep-mode assistant --label "assistant sweep (gateway)"

# Profile sweep: fix assistant, vary the model mm calls
python -m mmbench run --db benchmark.db \
  --assistants mock-strong --profiles gateway,orion-2 --repeats 3 \
  --sweep-mode profile --label "profile sweep (claude)"
```

Sweeps are **idempotent and resumable**: re-running skips trials already in the
store. Use `--max-cost` to set a spend guard, `--tasks t1,t2` to subset, and
`--report out.html` to render a static report inline.

### Run with real assistants

Pass `claude`, `codex`, or `gemini` as assistants. They activate only when the
CLI binary is on `PATH`; otherwise the trial is recorded as `failure_mode=skipped`
(never a silent zero). Configure the `mm` profile/model out of band as usual.

```bash
python -m mmbench run --db benchmark.db --assistants claude,codex --repeats 3
```

### View the dashboard / visualization

```bash
# Static, self-contained HTML (no server, easy to share/archive)
python -m mmbench report --db benchmark.db --run 1 --out report.html

# Interactive FastAPI dashboard at http://127.0.0.1:8008
python -m mmbench serve --db benchmark.db
```

The dashboard shows the **leaderboard** (mean overall per assistant), the
**baseline-vs-mm** uplift, a **per-task** breakdown, a **trend** of mean overall
across runs, and a **trial explorer** table (per-trial prompt outcome, the exact
`mm` commands run, wall time, and verifier checks).

## 6. Roadmap

The five design phases (dataset/GT, tasks/verifiers, harness, store+sweeps,
dashboard) are implemented here. Next up: more real assistant adapters
(Devin/OpenClaw headless), growing the catalogue toward the full 20 cases, and
wiring live `mm` profiles for real `baseline`-vs-`mm` uplift numbers.
