"""MkDocs hooks for the mm docs site.

Generates `docs/index.md` from the repository `README.md` at build time and
rewrites `docs/`-prefixed asset and link paths so they resolve relative to
`docs_dir`. Keeps the README as the single source of truth for the landing
page without duplicating its content into the repo.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_README = _REPO_ROOT / "README.md"

_ATTR_RE = re.compile(r'(\b(?:src|href)\s*=\s*")docs/')
_MD_LINK_RE = re.compile(r"\]\(docs/")


def _render_landing(docs_dir: Path) -> None:
    """Copy README → docs/index.md, rewriting docs/-prefixed paths."""
    text = _README.read_text(encoding="utf-8")
    text = _ATTR_RE.sub(r"\1", text)
    text = _MD_LINK_RE.sub("](", text)
    (docs_dir / "index.md").write_text(text, encoding="utf-8")


def on_pre_build(config, **_):
    """Regenerate the landing page before the build starts."""
    _render_landing(Path(config["docs_dir"]))


def on_serve(server, config, **_):
    """Hot-reload the landing page when README.md changes during `mkdocs serve`."""
    server.watch(str(_README))
    return server
