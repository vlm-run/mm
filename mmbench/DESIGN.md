# mmbench: mm eval system design

A state-of-the-art benchmark that measures whether `mm` makes AI agent harnesses
more **capable** and **faster** at real-world tasks over large, nested,
multimodal directories.

## Thesis (the one thing we measure)

Give an agent harness (claude, codex, gemini, openclaw, opencode, qwen) a hard,
real-world task over a directory tree of mixed media (photos, video, audio, PDFs,
docs) spread across subfolders. Run it twice, each in its own isolated copy:

- **without_mm arm**: the agent has only its native tools.
- **with_mm arm**: the agent additionally has `mm` on PATH plus a one-page
  usage primer.

Score both on **correctness** (against fixed ground truth, including the final
state of the filesystem) and **speed** (wall-clock to job done). The headline
number is the **lift**: `correctness(with_mm) - correctness(without_mm)` and
`speedup = time(without_mm) / time(with_mm)`.

This borrows the Next.js `AGENTS.md` framing (with-doc vs without-doc) and a
scoring/storage rigor, but the **tasks are mm's own**: real multimodal directory work, not orion-style perception probes.

### The tasks: agentic, real-world, action-based

The with_mm arm is **agentic**: we hand the agent the task + `mm` + the primer
and let it decide which commands to run. We never pick the `mm` command for it,
and there is no pre-piped arm. Tasks mirror how an agent uses mm in the wild
(see `docs/use-cases.md`), in three archetypes:

- **Retrieval**: locate the right file(s) in a large tree. "Find the photo from
  my Golden Gate Bridge trip", "which contract mentions indemnification".
  Exercises `grep -s`, `peek` (EXIF/pHash), `find`, `sql`. Non-mutating; graded
  on the file(s) named.
- **Organization**: restructure the tree. "Organize these into folders by date /
  kind / subject", "quarantine the near-duplicate photos". **Mutates** the
  sandbox; graded on the resulting structure.
- **Artifact creation**: synthesize across many files into an output file.
  "Build a spreadsheet of every invoice's vendor, date, and total". **Writes**
  an artifact; graded on the artifact's contents vs ground truth.

mm's value concentrates where the without_mm is weak: scale (hundreds of files),
and modalities the agent cannot read natively (video, audio, deep PDF). Single-file
image tasks are poor discriminators (the agent's own image-read tool matches mm),
so the suite avoids them and weights speed alongside correctness.

## Resolved decisions

- **Treatment arm**: agentic only. There is no pre-piped arm.
- **Profile**: a profile is an `mm profile`, uniquely identified by
  `(base_url, model)`, that mm uses for accurate-mode extraction. It is
  independent of the agent's own model (they may coincide). Profiles are
  selectable; default `['gateway']`. The **without_mm arm never touches mm**, so a
  profile only affects the with_mm arm.
- **Sandbox per run**: every cell runs in an isolated, tagged copy of the
  dataset so mutating tasks cannot contaminate each other. The grader inspects
  this sandbox after the run. (Granularity + copy strategy: see Sandbox.)
- **Dataset**: a frozen, purpose-built nested multimodal fixture (the existing
  `mmbench-tiny` / `mmbench-mini` are too flat and small for the real-world
  archetypes). See Dataset.

## Run unit: the assistant/profile cell

The basic unit is an **(assistant, profile)** cell. A run takes the cartesian
product of the selected `--assistants` and `--profiles`, so:

- `--assistants claude --profiles gateway` -> 1 cell.
- `--assistants claude --profiles gateway,my-profile` -> 2 cells (sweep backends).
- `--assistants claude,gemini --profiles gateway` -> 2 cells (the leaderboard).
- `--assistants claude,gemini --profiles gateway,my-profile` -> 4 cells.

Each cell is one **session**; its inner loop is `for case: for arm in
[without_mm, with_mm]: run -> grade -> persist`. The dashboard filters by
assistant and profile, so any N x N subset can be compared. Sessions accumulate
over time for trend/regression analysis. (There is no "mode A/B" concept; that
is just the product's shape.)

## Eval cases

20 cases, declarative YAML (data, not code). Composition rules:

| Axis | Target |
|---|---|
| Archetype | ~8 retrieval, ~6 organization, ~6 artifact-creation |
| mm commands | each of `find peek wc sql grep cat` is the primary surface in >= 3 cases |
| Modality | image / video / audio / pdf / doc each load-bearing in >= 3 cases |
| Scale | every task runs over a nested tree (subfolders); several over hundreds of files |
| Anti-noise | no two cases share `(archetype x primary command x dominant modality)`; every case has deterministic ground truth |

Case schema: `id, title, archetype, modality[], dataset, mm_commands[],
difficulty, prompt, ground_truth{}, checks[], judge_objective`. The same case
feeds both arms and every assistant/profile.

`checks[]` (kinds defined in `cases.CHECK_SPECS`) cover all three archetypes:

- **answer checks** (retrieval): `names_file`, `contains_number`,
  `contains_text` against the agent's final answer.
- **filesystem checks** (organization): `path_exists`, `path_absent` against the
  sandbox's final state.
- **artifact checks** (artifact-creation): `artifact_exists`,
  `artifact_contains`, `artifact_row_count` against a written output file,
  parsed and compared to ground truth.

## Sandbox

Retrieval is read-only, but organization and artifact tasks **mutate the
filesystem**, so every run gets its own working copy:

- A run materializes the case's dataset into a **tagged sandbox** keyed on
  `(assistant, profile, case, arm, run_index)`. The agent's `cwd` is the
  sandbox; it reads, moves, and writes only there.
- The grader runs **after** the agent against the sandbox's final state
  (`checks[]` of kind `path_exists` / `tree_matches` / `artifact_*`).
- The sandbox is retained on failure for postmortem, pruned on success (or
  always, configurable).
- mm's own state is isolated per run via a temp `XDG_DATA_HOME` (already wired)
  so its global index never leaks across cells.

Open: copy granularity vs cost. A full copy per cell is the simplest and most
isolated, but a large fixture x assistants x profiles x arms x runs multiplies
disk fast. Alternatives: per-`(assistant,profile)` sandbox reset between cases;
or copy-on-write / hardlink the read-only inputs and only materialize writes.

## Scoring

Three persisted signals per `(case, arm, assistant, profile)`:

1. **Correctness (0-100, primary)**: blend of deterministic `checks[]`
   (partial-credit, run against the final answer **and** the sandbox's final
   filesystem state / written artifacts) and an **LLM-judge** (0-5 against
   `judge_objective`, grounded to `ground_truth`). 50/50 blend.
2. **Speed (seconds)**: wall-clock to job done, per arm.
3. **mm-grounding (with_mm only)**: which `mm` commands the agent actually
   ran. Captured reliably via a PATH-shimmed `mm` that logs every invocation
   (agent-agnostic; no transcript parsing). Separates "mm helped" from "mm was
   available but ignored", and powers a coverage report. In the without_mm arm the
   same shim makes `mm` resolve to "command not found", so the without_mm is mm-free
   by construction.

Plus `task_completion` (task finished at all) and a failure-mode flag
(`timeout | tool_error`). The judge endpoint is asserted reachable by preflight
before any session starts. If it becomes unreachable for 3 retries mid-run, that
**run is voided** (its rows are deleted) and the process stops; the session keeps
its other completed runs, and no run ever mixes judged and checks-only cells.
Fix the judge and `--resume`.

Headline per cell: `correctness_lift`, `speedup`, `mm_adoption_rate`.

## Storage and dashboard

- **Store**: SQLite:
  `sessions(assistant, profile_name, base_url, model, ...)` ->
  `runs(session_id, run_index, elapsed_s)` ->
  `case_results(case_id, arm, correctness, checkpoint_score, judge_score,
  speed_s, task_completion, mm_used, mm_commands_used, failure_mode,
  final_output, transcript)`.
- **Dashboard**: FastAPI JSON API + a Svelte/Tailwind/Vite SPA (source in
  `mmbench/frontend`, built into `app/static`; Chart.js + svelte-multiselect).
  Leaderboard is **averaged over all of a cell's sessions** and ranked, with
  with/without lift as the hero stat; `svelte-multiselect` chips filter
  assistants/profiles. Drill-down: cell -> per-session trend + runs -> per-case
  results (incl. which mm commands ran).

## Dataset

A frozen, **nested multimodal fixture** (`mmbench-agent/`) plus the cases
(`cases.jsonl`); each case pins a subtree of the fixture as its `dataset`. It
lives on the Hugging Face Hub at `vlm-run/mmbench` (private).

The harness fetches it on first run: `ensure_dataset()` downloads the repo into
`mmbench/data/` (gitignored) and loads the corpus and cases from there, reusing
the local copy on later runs. HF auth (`hf auth login`) is required. Everything
the harness produces (the dataset, the results DB, sandboxes) stays under
`mmbench/data/`.

## Status

Engine complete: store, cases, sandbox, adapters (claude/codex/gemini/opencode
verified; qwen wired, needs key), grader, preflight, orchestrator+CLI, dashboard.
Fixture: ~180 files. 20 cases (10 retrieval / 6 artifact / 4 organization; 14 hard
/ 6 medium) over all six mm commands and pdf/image/video/mixed. Notes that shaped
the suite: the mmbench-mini keynote video is corrupt and all audio has no speech,
so differentiation leans on deep PDF, video, OCR-at-scale, and content-based
organization. Component layout: see `README.md`.

## Best practices

- Cases are data (YAML), reviewable and diffable; no logic drift between cases.
- Same prompt verbatim to both arms; the only variable is mm-availability.
- Deterministic ground truth on a frozen dataset; no case without a checkable
  answer.
- Deterministic checkpoints anchor the LLM-judge so a flaky judge cannot swing
  the headline.
- Persist full transcripts for postmortem and judge re-runs without re-executing
  agents.
- Resumable runs: `--resume` reuses the latest session for an (assistant,
  profile) and skips cells already completed (`task_completion=1`); agent runs
  are slow and flaky, so an interrupted pass continues cheaply.
- Preflight before any run: fixture present, each assistant's autonomy verified
  live, each profile + the judge endpoint reachable. No silent fallbacks.

## Pitfalls

- **Non-determinism**: agents are stochastic and slow. N runs per cell (default
  low), report mean + std, treat the *lift* as the signal not the absolute.
- **LLM-judge drift**: pin the judge model; keep deterministic checkpoints
  dominant on objective cases; spot-audit.
- **Unfair without_mm**: keep prompts tool-agnostic so the without_mm is honest (no
  leaking the mm command).
- **mm side-effects**: mm writes a global SQLite (`~/.local/share/mm/mm.db`) and
  `--pre-index` mutates state. Isolate mm's `XDG_DATA_HOME` / config per run so
  runs do not pollute each other.
- **Timeouts**: hard per-cell cap, preserve partial trace.
- **Cost**: assistants x profiles x cases x arms x runs explodes. The matrix is
  opt-in per axis; default to one profile and a subset of assistants.

## Hardest challenges

- **Mode A repointing**: agent CLIs bind to their own model/endpoint
  differently; some cannot be freely repointed. This constrains Mode A more than
  Mode B. (Note: in our profile model the swept profile is mm's backend, not the
  agent's, which sidesteps most of this.)
- **mm-grounding**: solved with a PATH-shimmed `mm` (see Scoring) rather than
  parsing five different agent transcript formats. The shim logs every mm
  invocation; reliable and agent-agnostic.
- **Non-interactive autonomy**: agentic CLIs gate tool calls behind interactive
  approval, which stalls headless runs. Both arms run with each agent's autonomy
  flag so the only difference is mm availability. Wired and verified live by
  preflight (it must non-interactively echo a sentinel): claude
  `--dangerously-skip-permissions`, codex `exec --dangerously-bypass-approvals-and-sandbox`,
  gemini/qwen `--yolo`, opencode `run`, openclaw `agent`, hermes `--yolo -z` (one-shot,
  approvals auto-bypassed), pi `--no-session -p` (non-interactive, ephemeral session).
  Preflight gates each one live: it refuses to run an unreachable/unauthenticated
  agent rather than scoring noise.
