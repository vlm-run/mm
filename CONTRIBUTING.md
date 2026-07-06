# Contributing to mm

Thank you for your interest in contributing to `mm`! We welcome contributions from everyone — whether it's fixing a typo, improving documentation, reporting a bug, or implementing a new feature.

## Code of Conduct

Be respectful, constructive, and inclusive. We follow the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

## Getting Started

### Prerequisites

- **Rust** (stable toolchain — pinned via `rust-toolchain.toml`)
- **Python 3.11–3.13**
- **[uv](https://docs.astral.sh/uv/)** — used for all Python operations (never bare `pip` or `maturin`)
- **ffmpeg** (optional — needed for video/audio accurate-mode pipelines)

### Development Setup

```bash
# Clone the repo
git clone https://github.com/vlm-run/mm.git
cd mm

# Create a virtual environment and install in editable mode
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"

# Build the Rust extension
make develop

# or run it directly
uv run maturin develop --release

# Install pre-commit hooks (also run automatically by `make develop`)
uv run pre-commit install --install-hooks
```

After modifying Rust code, you **must** re-run `make develop` before Python sees the changes.

### Running the CLI

```bash
# From the activated venv:
mm --version

# Or without activating:
uv run mm --version
```

## Making Changes

### Branching

Create a feature branch from `main`:

```bash
git checkout -b your-username/short-description
```

### Code Style — Python

- **Google-style docstrings** for all public functions, classes, and modules.
- **Type annotations** on all public APIs.
- **No header/separator comments** (`# === Section ===`). Let the code structure speak.
- Follow the Zen of Python — elegant, minimal, intentional code.
- Think in abstractions — prefer well-designed class hierarchies over loose functions for library code.

### Code Style — Rust

- Idiomatic Rust: `clippy::pedantic` as guidance, zero-copy where possible.
- `///` doc comments with examples on public APIs.
- Keep allocations off the hot path.

### Commit Messages

Write clear, concise commit messages:

```
feat: add WebP support to image encoder
fix: handle empty PDF pages in rasterize encoder
docs: update CLI examples for mm cat
```

Use conventional prefixes: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `perf:`.

## Testing

Every PR must pass the existing test suite. If you add new functionality, include tests.

```bash
# Run all fast tests (Rust + Python)
make test

# Rust tests only
make test-rust

# Python tests only (fast tier — mocked, no external server)
make test-python-fast

# Full Python test suite (includes slow/integration)
make test-python-full

# Benchmarks (Rust, via Criterion)
make bench
```

### Benchmark expectations

Performance-critical code **must** have benchmark coverage:

- **Rust**: Criterion benchmarks in `crates/mm-core/benches/`
- **Python**: pytest-benchmark tests in `tests/python/test_benchmark.py`

If your change touches I/O, parsing, hashing, or serialization on the hot path, include a benchmark.

## Linting & Formatting

Pre-commit hooks run automatically on `git commit`. You can also run them manually:

```bash
# Run all linters and formatters
make lint

# Individual targets
make lint-rust      # cargo clippy
make lint-python    # ruff check + ruff format --check
make typecheck      # ty type checker
make fmt            # cargo fmt + ruff format
```

The pre-commit config enforces:
- **ruff** — Python linting and formatting
- **ty** — Python type checking
- **nbstripout** — strips notebook outputs before commit
- Standard hooks (trailing whitespace, end-of-file, merge conflicts, large files)

## AI Disclosure

We encourage using AI coding assistants (Claude, Copilot, Cursor, Devin, etc.). They make contributors faster and are part of how `mm` itself is built. What we require is that a human understands and vouches for every line before it becomes a PR.

Before opening an AI-assisted PR:

- **Review every change yourself.** You are accountable for the code, not the tool.
- **Verify, don't trust.** Run the tests, lints, and the actual code paths you touched. Confirm the change does what its description claims. AI output can be confidently wrong.
- **Keep it in scope.** Strip speculative features, unnecessary fallbacks, and unrelated refactors that assistants tend to add.
- **Own the design.** Be able to explain *why* the change is written the way it is, and how it fits the Rust-core / Python-shell architecture.

If a PR was written with AI assistance, say so in the PR description. Disclosing AI assistance is welcome and never counts against you; an AI-written PR opened without that disclosure will be closed. Shipping unverified code will also get a PR closed.

The goal of this policy is to preserve codebase hygiene and maintainability, and to prevent abuse.

## Submitting a Pull Request

1. **Ensure tests pass**: `make test`
2. **Ensure lints pass**: `make lint`
3. **Push your branch** and open a pull request against `main`.
4. **Fill out the PR description** — explain *what* changed and *why*.
5. **Keep PRs focused** — one logical change per PR. Large refactors should be discussed in an issue first.

### PR Review Process

- A maintainer will review your PR, typically within a few business days.
- Address review feedback by pushing additional commits (don't force-push during review).
- Once approved, a maintainer will merge your PR.

## Reporting Bugs

Open a [GitHub Issue](https://github.com/vlm-run/mm/issues/new) with:

- **mm version** (`mm --version`)
- **OS and Python version**
- **Steps to reproduce** (minimal example)
- **Expected vs. actual behavior**
- **Relevant logs** (run with `--debug` for verbose output)

## Suggesting Features

We love ideas! Open an issue with the `enhancement` label describing:

- **The problem** you're trying to solve
- **Your proposed solution** (if any)
- **Alternatives considered**

For large features, please discuss in an issue before starting implementation.

## Architecture Notes

`mm` follows a **Rust core + Python shell** pattern:

- Performance-critical logic lives in Rust (`crates/mm-core/`) and is exposed to Python via PyO3 bindings (`crates/mm-python/`).
- The Python layer (`python/mm/`) provides CLI (Typer), developer experience, LLM integrations, and the `mm.Context` API.
- Data crosses the Rust/Python boundary as Arrow IPC bytes, primitives, or simple structs.

If your contribution is performance-sensitive (file I/O, hashing, parsing, batch transforms), consider implementing it in Rust. Prototype in Python if needed, but graduate to Rust before shipping.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
