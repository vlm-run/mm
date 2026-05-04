"""Runtime configuration for the mm FastAPI surface."""

from __future__ import annotations

import os
from pathlib import Path

MMBENCH_TINY_URL = "https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-tiny.tar.gz"

API_DIR = Path(__file__).resolve().parent


def data_dir() -> Path:
    """Resolve the data directory (override with ``MM_API_DATA_DIR``).

    Defaults to ``api/data/`` next to this package. The mmbench-tiny
    fixture is fetched into ``<data_dir>/mmbench-tiny`` on first start.
    """
    override = os.environ.get("MM_API_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return API_DIR / "data"


def mmbench_tiny_dir() -> Path:
    """Path where the mmbench-tiny fixture is unpacked."""
    return data_dir() / "mmbench-tiny"
