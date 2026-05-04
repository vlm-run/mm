"""Tests for the indexing deadline in ``semantic.index_missing``.

A slow file in the `mm grep -s --pre-index` pipeline should not block the
search indefinitely — once ``INDEX_TIMEOUT_S`` is hit, pending files are
cancelled and the caller continues with whatever got indexed.
"""

from __future__ import annotations

import time
from unittest.mock import patch

from mm import semantic


def test_index_missing_returns_partial_on_timeout(capsys):
    """Fast files complete, slow files are skipped, count reflects only fast ones."""
    fast_uris = [f"/tmp/fast-{i}.jpg" for i in range(2)]
    slow_uris = [f"/tmp/slow-{i}.jpg" for i in range(2)]
    all_uris = fast_uris + slow_uris
    slow_set = set(slow_uris)

    def fake_index_one(uri: str) -> str | None:
        if uri in slow_set:
            time.sleep(5.0)  # blow past the 0.5s timeout
        return uri

    with (
        patch.object(semantic, "INDEX_TIMEOUT_S", 0.5),
        patch.object(semantic, "_index_one", side_effect=fake_index_one),
    ):
        t0 = time.monotonic()
        n = semantic.index_missing(all_uris)
        elapsed = time.monotonic() - t0

    assert n == len(fast_uris), f"expected {len(fast_uris)} indexed, got {n}"
    # Should not wait for the slow ones to finish.
    assert elapsed < 2.0, f"index_missing blocked on slow files: {elapsed:.2f}s"

    out = capsys.readouterr().err
    assert "timeout" in out.lower()
    for uri in slow_uris:
        assert uri in out, f"expected {uri} to be reported as skipped"


def test_index_missing_clean_exit_reports_count(capsys):
    """When everything finishes in time, the summary still prints."""
    uris = [f"/tmp/ok-{i}.jpg" for i in range(3)]

    with (
        patch.object(semantic, "INDEX_TIMEOUT_S", 5.0),
        patch.object(semantic, "_index_one", side_effect=lambda u: u),
    ):
        n = semantic.index_missing(uris)

    assert n == 3
    out = capsys.readouterr().err
    assert "Indexed 3 files" in out
    assert "timeout" not in out.lower() or "timeout:" in out.lower()
