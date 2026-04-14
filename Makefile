.PHONY: develop build test test-rust test-python test-python-fast test-python-full bench clean lint lint-rust lint-python typecheck fmt

develop:
	uv run maturin develop --release
	@uv run pre-commit install --install-hooks >/dev/null 2>&1 || true

build:
	uv run maturin build --release

test: test-rust test-python ## Fast unit tests only (excludes slow/benchmark/integration)

test-all: test-rust test-python-all ## All tests including slow, benchmarks, and integration

test-rust:
	cargo test --workspace

# Fast tier — mocked unit tests only. Used by CI on every PR / push.
# Skips pytest-benchmark suites, subprocess cold-start benchmarks, and
# integration tests that need an external inference server.
test-python: test-python-fast

test-python-fast: develop
	uv run pytest tests/python -v

# Full tier — fast + slow + integration. Used by CI when the project
# version changes (release-track runs) and by developers before a
# release.
test-python-full: develop
	uv run pytest tests/python -v -m ""

bench:
	cargo bench --workspace

clean:
	cargo clean
	rm -rf target/ dist/ *.egg-info .mm/

lint: ## Format and lint all code
	uv run pre-commit run --all-files

lint-rust:
	cargo clippy --workspace -- -D warnings

lint-python:
	uv run ruff check python/ tests/
	uv run ruff format --check python/ tests/

typecheck: ## Run ty type checker on Python source
	uv run ty check python/mm/

fmt:
	cargo fmt --all
	uv run ruff format python/
