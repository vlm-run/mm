"""MkDocs hooks for the mm docs site.

Generates `docs/index.md` from the repository `README.md` at build time and
rewrites `docs/`-prefixed asset and link paths so they resolve relative to
`docs_dir`. Also mirrors `notebooks/*.ipynb` into `docs/notebooks/` so the
`mkdocs-jupyter` plugin can render them in-place. Keeps the README and
notebooks as the single source of truth without duplicating their content
into the repo.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_README = _REPO_ROOT / "README.md"
_NOTEBOOKS_SRC = _REPO_ROOT / "notebooks"

_ATTR_RE = re.compile(r'(\b(?:src|href)\s*=\s*")docs/')
_MD_LINK_RE = re.compile(r"\]\(docs/")


def _render_landing(docs_dir: Path) -> None:
    """Copy README → docs/index.md, rewriting docs/-prefixed paths."""
    text = _README.read_text(encoding="utf-8")
    text = _ATTR_RE.sub(r"\1", text)
    text = _MD_LINK_RE.sub("](", text)
    (docs_dir / "index.md").write_text(text, encoding="utf-8")


def _sync_notebooks(docs_dir: Path) -> None:
    """Mirror notebooks/ → docs/notebooks/ for mkdocs-jupyter to render."""
    if not _NOTEBOOKS_SRC.is_dir():
        return
    dest = docs_dir / "notebooks"
    dest.mkdir(parents=True, exist_ok=True)
    for nb in _NOTEBOOKS_SRC.glob("*.ipynb"):
        shutil.copy2(nb, dest / nb.name)


def on_pre_build(config, **_):
    """Regenerate the landing page and sync notebooks before the build starts."""
    docs_dir = Path(config["docs_dir"])
    _render_landing(docs_dir)
    _sync_notebooks(docs_dir)


def on_serve(server, config, **_):
    """Hot-reload generated docs when README or notebooks change during `mkdocs serve`."""
    server.watch(str(_README))
    if _NOTEBOOKS_SRC.is_dir():
        server.watch(str(_NOTEBOOKS_SRC))
    return server
