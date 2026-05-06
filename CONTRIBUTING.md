# Contributing to mm

Thanks for taking the time! This guide is the short version — see
[`AGENTS.md`](AGENTS.md) for the deep-dive on architecture, conventions, and
performance philosophy.

## Quick start

```bash
git clone https://github.com/vlm-run/mm.git
cd mm

uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"
uv run maturin develop --release
uv run pre-commit install
```

Always use `uv` — never bare `pip` or `maturin`. The `Makefile` wraps everything
through `uv run`.

After modifying any Rust code under `crates/`, re-run `make develop` before the
Python side will see the changes.

## Make targets

| Target            | What it runs                                              |
|-------------------|-----------------------------------------------------------|
| `make develop`    | `uv run maturin develop --release` + install pre-commit   |
| `make test`       | `cargo test` + fast Python tests                          |
| `make test-all`   | Full Python suite incl. slow / integration / benchmarks   |
| `make lint`       | `pre-commit run --all-files` (ruff + ruff-format + ty)    |
| `make lint-rust`  | `cargo clippy --workspace -- -D warnings`                 |
| `make lint-python`| `ruff check` + `ruff format --check`                      |
| `make typecheck`  | `ty check python/mm/`                                     |
| `make bench`      | `cargo bench --workspace` (Criterion)                     |
| `make fmt`        | `cargo fmt` + `ruff format`                               |

Every PR runs `make lint`, `make test-rust`, and `make test-python` in CI.

## Project layout (TL;DR)

- `crates/mm-core/` — Rust core (walk, hash, extract, schema, table).
- `crates/mm-python/` — PyO3 bindings (Arrow IPC over the FFI boundary).
- `python/mm/` — Python package (CLI, `Context`, encoders, pipelines, store).
- `tests/python/` — pytest suite (markers: `slow`, `integration`, `perf`).

See [`AGENTS.md`](AGENTS.md) for the full tree and module-level notes.

## Code style

- **Python**: Google-style docstrings on public APIs. Type-annotate all public
  surfaces. No header/separator comments. Match the surrounding ruff style.
- **Rust**: idiomatic, `clippy::pedantic` as guidance, doc comments (`///`) on
  public items with examples.
- **Performance-critical code lives in Rust.** If a Python method shows up in
  profiling or processes data at scale, it's a candidate to graduate to Rust
  via PyO3.

## Tests and benchmarks

Every performance-oriented or hot-path method needs *both* a unit test and a
benchmark:

- Rust: Criterion benches under `crates/mm-core/benches/`.
- Python: `pytest-benchmark` under `tests/python/test_benchmark.py`.

Benchmarks are first-class — they catch regressions unit tests can't see.

## Pull requests

1. Branch off `main` (`git checkout -b your-username/short-slug`).
2. Run `make lint && make test` locally before pushing.
3. Open a PR using the template in `.github/PULL_REQUEST_TEMPLATE.md`.
4. CI must be green before merge. If your change moves performance numbers,
   include a row in the PR description with the before/after.
5. For changes that affect the public surface (CLI flags, `mm.Context` API),
   update `README.md` and `AGENTS.md` in the same PR.

## Reporting bugs

Use the issue forms under `.github/ISSUE_TEMPLATE/`. Please include:

- `mm --version`
- `python --version` and OS
- Full command + minimal repro
- `mm doctor` output (when available)

## Getting help

- [Discord](https://discord.gg/6aqcyvPF79)
- [GitHub Issues](https://github.com/vlm-run/mm/issues)
