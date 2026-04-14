.PHONY: develop build test test-rust test-python bench clean lint lint-rust lint-python typecheck fmt

develop:
	uv run maturin develop --release

build:
	uv run maturin build --release

test: test-rust test-python

test-rust:
	cargo test --workspace

test-python: develop
	uv run pytest tests/python -v

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
