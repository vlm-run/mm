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
_PIPELINES_SRC = _REPO_ROOT / "python" / "mm" / "pipelines"
_SPEC_TEMPLATE_KINDS = ("image", "video", "audio", "document")

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
    if dest.is_dir():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for nb in _NOTEBOOKS_SRC.glob("*.ipynb"):
        shutil.copy2(nb, dest / nb.name)


def _render_spec_templates(docs_dir: Path) -> None:
    """Wrap each `pipelines/<kind>/spec.yaml.template` into a Markdown page.

    The generated pages live under `docs/spec-templates/<kind>.md` and embed
    the raw YAML in a fenced code block so developers can read the full
    reference (every strategy, every option, every comment) directly from
    the docs site.
    """
    dest_dir = docs_dir / "spec-templates"
    if dest_dir.is_dir():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    for kind in _SPEC_TEMPLATE_KINDS:
        src = _PIPELINES_SRC / kind / "spec.yaml.template"
        if not src.is_file():
            continue
        title = kind.capitalize()
        body = (
            f"# {title} pipeline spec template\n\n"
            f"Reference template for the **{kind}** pipeline. Every encode "
            f"strategy and every `generate` option is documented inline. "
            f"Copy this into `~/.config/mm/pipelines/{kind}/{{mode}}.yaml` "
            f"(replacing `{{mode}}` with `fast` or `accurate`) and edit only "
            f"the fields you want to override — omitted keys fall back to the "
            f"built-in defaults.\n\n"
            f"Source: `python/mm/pipelines/{kind}/spec.yaml.template`\n\n"
            f"```yaml\n{src.read_text(encoding='utf-8').rstrip()}\n```\n"
        )
        (dest_dir / f"{kind}.md").write_text(body, encoding="utf-8")


def on_pre_build(config, **_):
    """Regenerate the landing page and sync notebooks before the build starts."""
    docs_dir = Path(config["docs_dir"])
    _render_landing(docs_dir)
    _sync_notebooks(docs_dir)
    _render_spec_templates(docs_dir)


def on_serve(server, config, **_):
    """Hot-reload generated docs when README or notebooks change during `mkdocs serve`."""
    server.watch(str(_README))
    if _NOTEBOOKS_SRC.is_dir():
        server.watch(str(_NOTEBOOKS_SRC))
    if _PIPELINES_SRC.is_dir():
        server.watch(str(_PIPELINES_SRC))
    return server
