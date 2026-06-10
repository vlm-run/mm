.PHONY: dev develop build test test-rust test-python test-python-fast test-python-full bench clean lint lint-rust lint-python typecheck fmt dist dist-verify dist-test dist-publish dist-publish-test

dev:
	uv venv --python 3.12
	. .venv/bin/activate && uv pip install -e ".[dev]"
	uv run maturin develop --release
	@uv run pre-commit install --install-hooks >/dev/null 2>&1 || true

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

# --- PyPI release targets ---

DIST_DIR := dist

dist: clean-dist ## Build wheel for current platform
	uv run maturin build --release --out $(DIST_DIR)
	@echo "── Built wheels ──"
	@ls -lh $(DIST_DIR)/*.whl

WHEEL_ALLOWED_EXTS := py|pyi|yaml|so|pyd|typed
dist-verify: ## Verify wheels contain only whitelisted file types
	@test -n "$$(ls $(DIST_DIR)/*.whl 2>/dev/null)" || { echo "No wheels found in $(DIST_DIR)/"; exit 1; }
	@FAIL=0; for whl in $(DIST_DIR)/*.whl; do \
		echo "── $$(basename $$whl) ──"; \
		BAD=$$(unzip -l "$$whl" \
			| awk '/[0-9]{2}-[0-9]{2}-[0-9]{4}/ {print $$NF}' \
			| grep -v 'dist-info' \
			| grep -vE '\.($(WHEEL_ALLOWED_EXTS))$$'); \
		if [ -n "$$BAD" ]; then \
			echo "ERROR: non-whitelisted files (allowed: .py .pyi .yaml .so .pyd py.typed):"; \
			echo "$$BAD" | sed 's/^/  /'; \
			FAIL=1; \
		fi; \
	done; \
	if [ "$$FAIL" = "1" ]; then exit 1; fi
	@echo "All wheels clean (only .py .pyi .yaml .so .pyd py.typed)"
	@ls -lh $(DIST_DIR)/*.whl

dist-test: dist dist-verify ## Build, verify, and smoke-test wheel
	rm -rf /tmp/mm-test-install
	uv venv --python 3.12 /tmp/mm-test-install
	VIRTUAL_ENV=/tmp/mm-test-install uv pip install $(DIST_DIR)/*.whl
	/tmp/mm-test-install/bin/mm --version
	@echo "── Smoke test passed ──"
	rm -rf /tmp/mm-test-install

dist-publish-test: dist dist-verify ## Upload wheel to TestPyPI
	uv run twine upload --repository testpypi $(DIST_DIR)/*.whl

dist-publish: dist dist-verify ## Upload wheel to PyPI (IRREVERSIBLE for this version)
	uv run twine upload $(DIST_DIR)/*.whl

clean-dist:
	rm -rf $(DIST_DIR)
