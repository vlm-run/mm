"""Write release tag metadata into the Python package before wheel builds."""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_FILE = ROOT / "python" / "mm" / "_release.py"


def main() -> None:
    """Write python/mm/_release.py from the release tag that triggered the build."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    release_version = pyproject["project"]["version"]
    release_tag = _release_tag(release_version)
    released_at: str | None = _git(
        "for-each-ref", f"refs/tags/{release_tag}", "--format=%(creatordate:iso-strict)"
    )
    commit: str | None = _git("rev-parse", "--short", f"{release_tag}^{{commit}}")
    if not released_at or not commit:
        print(
            f"warning: could not resolve release metadata for tag {release_tag!r}; "
            "writing an empty imprint",
            file=sys.stderr,
        )
        released_at = commit = None

    RELEASE_FILE.write_text(
        "\n".join(
            [
                '"""Build-time release metadata for packaged wheels."""',
                "",
                f"RELEASE_VERSION: str | None = {release_version!r}",
                f"RELEASED_AT: str | None = {released_at!r}",
                f"RELEASE_COMMIT: str | None = {commit!r}",
                "",
            ]
        )
    )


def _release_tag(release_version: str) -> str:
    ref = os.environ.get("GITHUB_REF", "")
    if ref.startswith("refs/tags/"):
        return ref.removeprefix("refs/tags/")
    return f"v{release_version}"


def _git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True,
            check=False,
            text=True,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


if __name__ == "__main__":
    main()
