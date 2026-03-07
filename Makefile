.PHONY: develop build test test-rust test-python bench clean lint fmt

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
	rm -rf target/ dist/ *.egg-info .vlmctx/

lint:
	cargo clippy --workspace -- -D warnings
	uv run ruff check python/
	uv run mypy python/vlmctx/

fmt:
	cargo fmt --all
	uv run ruff format python/
