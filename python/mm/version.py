"""Version imprint helpers for the mm CLI."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from . import _release


def version_imprint(version: str) -> str:
    """Return the CLI version imprint.

    Args:
        version: Package version to resolve.

    Returns:
        A string such as ``v0.13.0 - 2026.5.23 (bfd578d)``.
    """
    metadata = _static_release_metadata(version) or _git_release_metadata(version)
    if metadata is None:
        return f"v{version}"
    released_at, commit = metadata
    return f"v{version} - {released_at} ({commit})"


def _static_release_metadata(version: str) -> tuple[str, str] | None:
    if _release.RELEASE_VERSION != version:
        return None
    released_at = _format_release_time(_release.RELEASED_AT)
    if not released_at or not _release.RELEASE_COMMIT:
        return None
    return released_at, _release.RELEASE_COMMIT


def _git_release_metadata(version: str) -> tuple[str, str] | None:
    repo = _repo_root()
    if not repo:
        return None
    tag = f"v{version.split('+', maxsplit=1)[0]}"
    tag_date = _run_git(
        repo, "for-each-ref", f"refs/tags/{tag}", "--format=%(creatordate:iso-strict)"
    )
    commit = _run_git(repo, "rev-parse", "--short", f"{tag}^{{commit}}")
    released_at = _format_release_time(tag_date)
    if not released_at or not commit:
        return None
    return released_at, commit


def _repo_root() -> Path | None:
    resolved = Path(__file__).resolve()
    if len(resolved.parents) > 2:
        root = resolved.parents[2]
        if (root / ".git").exists():
            return root
    return None


def _run_git(cwd: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _format_release_time(value: str | None) -> str | None:
    if not value:
        return None

    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return value.strip() or None

    return f"{parsed.year}.{parsed.month}.{parsed.day}"
