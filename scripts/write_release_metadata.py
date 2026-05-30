"""Write release tag metadata into the Python package before wheel builds."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tomllib


ROOT = Path(__file__).resolve().parents[1]
RELEASE_FILE = ROOT / "python" / "mm" / "_release.py"


def main() -> None:
    """Write python/mm/_release.py from the current package version tag."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    release_version = pyproject["project"]["version"]
    release_tag = f"v{release_version}"
    released_at = _git(
        "for-each-ref", f"refs/tags/{release_tag}", "--format=%(creatordate:iso-strict)"
    )
    commit = _git("rev-parse", "--short", f"{release_tag}^{{commit}}")
    if not released_at or not commit:
        raise SystemExit(f"Could not resolve release metadata for tag {release_tag!r}")

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


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


if __name__ == "__main__":
    main()
