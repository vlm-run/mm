# Contributing to mm

Thanks for your interest in contributing! `mm` is a Rust + Python hybrid project — see [CLAUDE.md](CLAUDE.md) for an architecture overview and coding conventions.

## Setup

Always use [`uv`](https://docs.astral.sh/uv/) — never bare `pip` or `maturin`.

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"
make develop   # builds the Rust extension via maturin
```

After any change to Rust code, re-run `make develop` before Python will see it.

## Before opening a PR

```bash
make test        # cargo test + pytest
make lint         # ruff lint + format + pre-commit hooks
make lint-rust    # clippy
make typecheck    # ty type checker
```

Performance-critical code (I/O, parsing, hashing, serialization) should come with both a unit test and a Criterion (Rust) or pytest-benchmark (Python) benchmark in the same PR — see CLAUDE.md's "Testing and benchmarks" section.

## Style

- Rust: idiomatic, `clippy::pedantic` as guidance, doc comments (`///`) on public APIs.
- Python: Google-style docstrings, type annotations on public APIs, no header/separator comments.

## Submitting changes

1. Fork the repo and create a branch off `main`.
2. Make your change, with tests.
3. Ensure `make test` and `make lint` pass.
4. Open a PR describing the change and why it's needed.
