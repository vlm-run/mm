"""Runtime budgets for ``mm find`` to catch scan / JSON-path regressions.

Budgets are wall-clock seconds on a warm-ish interpreter. Override with
``MM_TEST_FIND_SCAN_MAX_S`` and ``MM_TEST_FIND_CLI_MAX_S`` if CI hardware
requires looser limits. Select with ``pytest -m perf``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.perf


def _scan_max_s() -> float:
    return float(os.environ.get("MM_TEST_FIND_SCAN_MAX_S", "1.25"))


def _cli_max_s() -> float:
    return float(os.environ.get("MM_TEST_FIND_CLI_MAX_S", "6.0"))


def _columns_max_s() -> float:
    return float(os.environ.get("MM_TEST_FIND_COLUMNS_MAX_S", "2.0"))


def test_find_scanner_scan_and_json_fast_under_budget(small_tree: Path) -> None:
    """Rust scan + ``to_json_fast`` must stay cheap for small trees."""
    from mm._mm import Scanner

    scanner = Scanner(str(small_tree), None)
    t0 = time.perf_counter()
    n = scanner.scan()
    payload = scanner.to_json_fast()
    elapsed = time.perf_counter() - t0

    assert n > 0
    assert len(payload) > 4
    assert elapsed < _scan_max_s(), (
        f"scan()+to_json_fast took {elapsed:.3f}s (budget {_scan_max_s()}s)"
    )


def test_find_subprocess_json_format_under_budget(small_tree: Path) -> None:
    """Full CLI ``find --format json`` including imports; stdin closed like scripts."""
    t0 = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-m", "mm.cli", "find", str(small_tree), "--format", "json"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed = time.perf_counter() - t0

    assert result.returncode == 0, result.stderr
    assert len(result.stdout) > 10
    assert elapsed < _cli_max_s(), (
        f"mm find --format json took {elapsed:.3f}s (budget {_cli_max_s()}s)"
    )


def test_find_subprocess_columns_under_budget(small_tree: Path) -> None:
    """Arrow / column projection path must not explode vs the JSON fast path."""
    t0 = time.perf_counter()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mm.cli",
            "find",
            str(small_tree),
            "--columns",
            "name,kind,size",
            "--format",
            "tsv",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed = time.perf_counter() - t0

    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert len(lines) >= 2
    assert "name" in lines[0] and "kind" in lines[0]
    assert elapsed < _columns_max_s(), (
        f"mm find --columns … took {elapsed:.3f}s (budget {_columns_max_s()}s)"
    )


@pytest.mark.slow
def test_find_scanner_large_tree_json_fast_under_budget(large_tree: Path) -> None:
    """Regression guard for O(n) scan on hundreds of files (not run in default CI)."""
    from mm._mm import Scanner

    max_s = float(os.environ.get("MM_TEST_FIND_LARGE_SCAN_MAX_S", "4.0"))
    scanner = Scanner(str(large_tree), None)
    t0 = time.perf_counter()
    n = scanner.scan()
    scanner.to_json_fast()
    elapsed = time.perf_counter() - t0

    assert n >= 400
    assert elapsed < max_s, f"large-tree scan+to_json_fast took {elapsed:.3f}s (budget {max_s}s)"
