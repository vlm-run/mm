.PHONY: develop build test test-rust test-python test-python-fast test-python-full bench clean lint fmt

develop:
	uv run maturin develop --release

build:
	uv run maturin build --release

test: test-rust test-python

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

lint:
	cargo clippy --workspace -- -D warnings
	uv run ruff check python/
	uv run mypy python/mm/

lint-rust:
	cargo clippy --workspace -- -D warnings

lint-python:
	uv run ruff check python/
	uv run mypy python/mm/

fmt:
	cargo fmt --all
	uv run ruff format python/
