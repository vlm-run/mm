"""Fetch + extract the mmbench-tiny fixture on first startup."""

from __future__ import annotations

import logging
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from gradio_app.config import MMBENCH_TINY_URL, data_dir, mmbench_tiny_dir

log = logging.getLogger("mm.gradio_app.data_setup")


def ensure_mmbench_tiny() -> Path:
    """Download + extract mmbench-tiny if missing. Idempotent.

    Returns:
        Path to the unpacked ``mmbench-tiny`` directory.
    """
    target = mmbench_tiny_dir()
    if target.exists() and any(target.iterdir()):
        log.info("mmbench-tiny already present at %s", target)
        return target

    root = data_dir()
    root.mkdir(parents=True, exist_ok=True)
    log.info("Downloading mmbench-tiny from %s", MMBENCH_TINY_URL)

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        with urllib.request.urlopen(MMBENCH_TINY_URL) as resp, tmp_path.open("wb") as out:
            shutil.copyfileobj(resp, out)

        log.info("Extracting %s → %s", tmp_path, root)
        with tarfile.open(tmp_path, "r:gz") as tar:
            tar.extractall(root, filter="data")
    finally:
        tmp_path.unlink(missing_ok=True)

    if not target.exists():
        raise RuntimeError(
            f"mmbench-tiny extraction did not produce {target} — archive layout may have changed"
        )

    log.info("mmbench-tiny ready at %s", target)
    return target
