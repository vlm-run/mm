"""HTTP endpoints for the mm API surface.

All routes wrap the in-process mm Python API — no subprocess/CLI shelling
out. The cat and grep handlers reuse the same primitives the CLI uses:
``mm.commands.cat._extract`` for cat, ``mm.context.Context`` plus
``mm.cat_utils.extract_meta.extract_meta`` plus ``mm.semantic.grep_semantic``
for grep.
"""

from __future__ import annotations

import json
import re
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from fastapi import APIRouter, HTTPException, Query

from gradio_app.config import data_dir
from gradio_app.models import (
    CatRequest,
    CatResponse,
    GrepMatch,
    GrepRequest,
    GrepResponse,
    ListDirectoryResponse,
    ProfileCreateRequest,
    ProfileListResponse,
    ProfileSummary,
    ProfileUpdateRequest,
)

router = APIRouter()

_PROFILE_LOCK = threading.Lock()


@contextmanager
def _use_profile(name: str | None) -> Iterator[None]:
    """Temporarily set ``mm.config._cli_overrides.profile`` for one call.

    Serialised through a process-wide lock because ``_cli_overrides`` is a
    module global; concurrent overrides would clobber each other.
    """
    if not name:
        yield
        return
    from mm.config import _cli_overrides

    with _PROFILE_LOCK:
        prev = _cli_overrides.profile
        _cli_overrides.profile = name
        try:
            yield
        finally:
            _cli_overrides.profile = prev


def _resolve_path(p: str) -> Path:
    """Resolve ``p`` against the data dir when relative, else return as-is."""
    candidate = Path(p).expanduser()
    if not candidate.is_absolute():
        candidate = (data_dir() / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return candidate


@router.get("/list-directory", response_model=ListDirectoryResponse)
def list_directory(
    directory: str | None = Query(
        default=None, description="Directory to scan (default: data dir)"
    ),
    kind: str | None = Query(default=None, description="Filter by file kind"),
    name: str | None = Query(default=None, description="Filter by file name (regex)"),
    no_ignore: bool = Query(default=False, description="Don't respect .gitignore"),
) -> ListDirectoryResponse:
    """Hierarchical tree of the data directory — mirrors ``mm find <dir> --tree --format json``."""
    from mm._mm import Scanner
    from mm.commands.find import _build_tree, _count_subtree, _tree_to_json

    root = _resolve_path(directory) if directory else data_dir()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=404, detail=f"Directory not found: {root}")

    scanner = Scanner(str(root), None, no_ignore=no_ignore)
    scanner.scan()

    raw = json.loads(scanner.to_json_fast(kind=kind, name=name))
    tree_data = _build_tree(raw)
    files, total_bytes = _count_subtree(tree_data)

    return ListDirectoryResponse(
        root=str(root),
        files=files,
        bytes=total_bytes,
        tree=_tree_to_json(tree_data, str(root)),
    )


@router.post("/cat", response_model=CatResponse)
def cat(req: CatRequest) -> CatResponse:
    """Extract content from a single file at the given mode.

    Mirrors ``mm cat <path> -m <mode>`` plus encode/generate overrides.
    """
    from mm.cat_utils.base_utils import CatOpts
    from mm.commands import cat as cat_module
    from mm.pipelines.pipelines_utils import load_pipeline_args

    path = _resolve_path(req.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a regular file: {path}")

    enc_overrides: dict[str, Any] = {}
    if req.encode is not None:
        if req.encode.strategy is not None:
            enc_overrides["strategy"] = req.encode.strategy
        if req.encode.pyfunc is not None:
            enc_overrides["pyfunc"] = req.encode.pyfunc
        if req.encode.strategy_opts:
            enc_overrides["strategy_opts"] = dict(req.encode.strategy_opts)

    gen_overrides: dict[str, str] = {}
    if req.generate is not None:
        for k, v in req.generate.model_dump(exclude_none=True).items():
            gen_overrides[k] = str(v)

    pipeline_specs = load_pipeline_args(req.pipeline) if req.pipeline else {}

    opts = CatOpts(
        n=req.n,
        output_dir=None,
        mode=req.mode,
        no_cache=req.no_cache,
        format="json",
        encode_overrides=enc_overrides,
        generate_overrides=gen_overrides,
        pipelines=pipeline_specs,
        verbose=req.verbose,
    )

    cat_module._total_bytes_processed = 0
    cat_module._was_cached = False

    try:
        with _use_profile(req.profile):
            content = cat_module._extract(path, opts)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if req.n is not None:
        all_lines = content.splitlines()
        sliced = all_lines[: req.n] if req.n >= 0 else all_lines[req.n :]
        content = "\n".join(sliced)

    return CatResponse(
        path=str(path),
        mode=req.mode,
        content=content,
        bytes_processed=path.stat().st_size,
        cached=cat_module._was_cached,
    )


@router.post("/grep", response_model=GrepResponse)
def grep(req: GrepRequest) -> GrepResponse:
    """Regex (and optionally semantic) search across files.

    Mirrors ``mm grep <pattern> <dir> [--semantic] [--pre-index] ...``.
    Text, code, and document files are searched with regex; when
    ``semantic=True`` and binary files are present, vector search runs
    alongside via ``mm.semantic.grep_semantic``.
    """
    from mm.cat_utils.extract_meta import _local_document
    from mm.context import Context
    from mm.utils import is_binary_content

    root = _resolve_path(req.directory) if req.directory else data_dir()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=404, detail=f"Directory not found: {root}")

    pattern_literals = re.sub(r"\\.", "", req.pattern, flags=re.DOTALL)
    smart_case = not req.ignore_case and not any(c.isupper() for c in pattern_literals)
    re_flags = re.IGNORECASE if (req.ignore_case or smart_case) else 0
    try:
        regex = re.compile(req.pattern, re_flags)
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"Invalid regex: {e}") from e

    ctx = Context(root, no_ignore=req.no_ignore)
    if req.kind:
        ctx = ctx.filter(kind=req.kind)
    if req.ext:
        ctx = ctx.filter(ext=req.ext)

    matches: list[dict[str, Any]] = []
    file_counts: dict[str, int] = {}

    for f in ctx.files:
        if f.path.startswith("."):
            continue
        full_path = (root / f.path).resolve()
        try:
            if f.kind == "document":
                content = _local_document(full_path)
            elif f.is_binary:
                continue
            else:
                content = full_path.read_text(errors="replace")
        except Exception:
            continue

        lines = content.splitlines()
        for i, line in enumerate(lines):
            if not regex.search(line):
                continue
            file_counts[f.path] = file_counts.get(f.path, 0) + 1
            if not req.count and len(matches) < req.limit:
                entry: dict[str, Any] = {
                    "path": f.path,
                    "line_number": i + 1,
                    "line": line,
                }
                if req.context_lines > 0:
                    start = max(0, i - req.context_lines)
                    end = min(len(lines), i + req.context_lines + 1)
                    entry["context"] = lines[start:end]
                matches.append(entry)

    if req.semantic:
        from mm.semantic import grep_semantic

        has_binary = any(is_binary_content(kind=f.kind) for f in ctx.files)
        if has_binary:
            try:
                hits = grep_semantic(
                    req.pattern,
                    root,
                    req.kind,
                    req.ext,
                    limit=min(req.limit, 50),
                    stdin_paths=None,
                    no_ignore=req.no_ignore,
                    do_index=req.pre_index,
                    quiet=True,
                    cmd_hint=None,
                )
            except Exception:
                hits = []

            seen: set[tuple[str, int]] = {(m["path"], m["line_number"]) for m in matches}
            for r in hits:
                rel_path = r["path"]
                try:
                    rel_path = str(Path(rel_path).relative_to(root))
                except ValueError:
                    pass
                key = (rel_path, r["index"])
                if key in seen:
                    continue
                seen.add(key)
                snippet = r.get("snippet") or r.get("match", "")
                line_text = snippet.replace("\n", " ")[:280]
                if len(matches) < req.limit:
                    matches.append({"path": rel_path, "line_number": r["index"], "line": line_text})
                file_counts[rel_path] = file_counts.get(rel_path, 0) + 1

    return GrepResponse(
        pattern=req.pattern,
        total_matches=sum(file_counts.values()),
        file_counts=file_counts,
        matches=[GrepMatch(**m) for m in matches],
    )


@router.get("/profiles", response_model=ProfileListResponse)
def list_profiles() -> ProfileListResponse:
    """List configured LLM profiles (api_key masked)."""
    from mm.profile import (
        get_active_profile_name,
        get_profile_names,
        get_profile_section,
        load_profile_config,
    )

    file_data = load_profile_config()
    active = get_active_profile_name()
    summaries: list[ProfileSummary] = []
    for name in get_profile_names():
        section = get_profile_section(file_data, name)
        summaries.append(
            ProfileSummary(
                name=name,
                base_url=section.get("base_url", ""),
                model=section.get("model", ""),
                api_key="••••" if section.get("api_key") else "",
                is_active=name == active,
            )
        )
    return ProfileListResponse(active=active, profiles=summaries)


@router.get("/profiles/active", response_model=ProfileSummary)
def active_profile() -> ProfileSummary:
    """Return the currently active profile (api_key masked)."""
    from mm.profile import get_profile

    p = get_profile()
    return ProfileSummary(
        name=p.name,
        base_url=p.base_url,
        model=p.model,
        api_key="••••" if p.api_key else "",
        is_active=True,
    )


@router.post("/profiles", response_model=ProfileSummary, status_code=201)
def create_profile(req: ProfileCreateRequest) -> ProfileSummary:
    """Add a new profile."""
    from mm.profile import add_profile

    try:
        add_profile(req.name, base_url=req.base_url, model=req.model, api_key=req.api_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ProfileSummary(
        name=req.name,
        base_url=req.base_url,
        model=req.model,
        api_key="••••" if req.api_key else "",
        is_active=False,
    )


@router.patch("/profiles/{name}", response_model=ProfileSummary)
def update_profile_route(name: str, req: ProfileUpdateRequest) -> ProfileSummary:
    """Update one or more fields of an existing profile."""
    from mm.profile import (
        get_active_profile_name,
        get_profile_section,
        load_profile_config,
        update_profile,
    )

    if req.base_url is None and req.api_key is None and req.model is None:
        raise HTTPException(
            status_code=400,
            detail="No fields to update. Provide at least one of base_url, api_key, model.",
        )
    try:
        update_profile(name, base_url=req.base_url, api_key=req.api_key, model=req.model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    section = get_profile_section(load_profile_config(), name)
    return ProfileSummary(
        name=name,
        base_url=section.get("base_url", ""),
        model=section.get("model", ""),
        api_key="••••" if section.get("api_key") else "",
        is_active=name == get_active_profile_name(),
    )


@router.post("/profiles/{name}/use", response_model=ProfileSummary)
def use_profile(name: str) -> ProfileSummary:
    """Set ``name`` as the active profile."""
    from mm.profile import get_profile_section, load_profile_config, set_active_profile

    try:
        set_active_profile(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    section = get_profile_section(load_profile_config(), name)
    return ProfileSummary(
        name=name,
        base_url=section.get("base_url", ""),
        model=section.get("model", ""),
        api_key="••••" if section.get("api_key") else "",
        is_active=True,
    )


@router.delete("/profiles/{name}", status_code=204)
def delete_profile(name: str) -> None:
    """Remove a non-reserved profile."""
    from mm.profile import remove_profile

    try:
        remove_profile(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
