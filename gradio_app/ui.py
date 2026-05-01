"""Gradio UI for the mm app.

Calls the same in-process route handlers as the FastAPI surface — no
HTTP round-trip. The Modern Organic Editorial design system is loaded
via ``mount_gradio_app(head=DESIGN_HEAD)``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import gradio as gr
from fastapi import HTTPException
from mm.cat_utils.base_utils import CatMode

from gradio_app import routes
from gradio_app.config import data_dir
from gradio_app.design import DESIGN_HEAD, FOOTER_HTML, HEADER_HTML
from gradio_app.models import (
    CatRequest,
    EncodeOverrides,
    GenerateOverrides,
    GrepRequest,
    ProfileCreateRequest,
    ProfileUpdateRequest,
)

__all__ = ["DESIGN_HEAD", "FOOTER_HTML", "HEADER_HTML", "build_ui"]


def _format_error(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return f"[{exc.status_code}] {exc.detail}"
    return f"[error] {type(exc).__name__}: {exc}"


def _ascii_tree(node: dict[str, Any], prefix: str = "", is_last: bool = True) -> list[str]:
    """Render a tree dict (as produced by /list-directory) as ASCII lines."""
    name = node["name"]
    if node["type"] == "directory":
        size_label = f"  ({node.get('files', 0)} files, {node.get('bytes', 0)} bytes)"
        line = f"{prefix}{'└── ' if is_last else '├── '}{Path(name).name}/{size_label}"
    else:
        line = f"{prefix}{'└── ' if is_last else '├── '}{name}  [{node.get('size', 0)} bytes, {node.get('kind', '?')}]"

    lines = [line]
    children = node.get("children", []) or []
    next_prefix = prefix + ("    " if is_last else "│   ")
    for i, child in enumerate(children):
        lines.extend(_ascii_tree(child, next_prefix, i == len(children) - 1))
    return lines


def _do_list_directory(directory: str, kind: str, name: str) -> tuple[str, str]:
    try:
        result = routes.list_directory(
            directory=directory or None,
            kind=kind or None,
            name=name or None,
            no_ignore=False,
        )
    except HTTPException as e:
        return _format_error(e), "{}"
    tree_dict = result.tree
    header = f"{result.root}  ({result.files} files, {result.bytes:,} bytes)"
    lines = [header]
    for i, child in enumerate(tree_dict.get("children", []) or []):
        lines.extend(_ascii_tree(child, "", i == len(tree_dict["children"]) - 1))
    return "\n".join(lines), json.dumps(result.model_dump(), indent=2)


def _parse_strategy_opts(raw: str) -> dict[str, Any]:
    """Parse ``key=value`` lines into a dict, coercing int/float/bool."""
    out: dict[str, Any] = {}
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, val = line.partition("=")
        if not sep:
            continue
        v = val.strip()
        if v.lower() in ("true", "false"):
            out[key.strip()] = v.lower() == "true"
            continue
        try:
            out[key.strip()] = int(v)
            continue
        except ValueError:
            pass
        try:
            out[key.strip()] = float(v)
            continue
        except ValueError:
            pass
        out[key.strip()] = v
    return out


def _profile_choices() -> tuple[list[str], str]:
    resp = routes.list_profiles()
    return [p.name for p in resp.profiles], resp.active


def _do_cat(
    path: str,
    mode: CatMode,
    profile: str,
    n: int | None,
    no_cache: bool,
    pipeline: str,
    strategy_opts: str,
    prompt: str,
    max_tokens: str,
    temperature: str,
) -> tuple[str, str]:
    if not path:
        return "[error] file path is required", ""

    encode = None
    parsed_opts = _parse_strategy_opts(strategy_opts)
    if parsed_opts:
        encode = EncodeOverrides(strategy_opts=parsed_opts)

    generate = None
    gen_kwargs = {
        k: v
        for k, v in {
            "prompt": prompt or None,
            "max_tokens": max_tokens or None,
            "temperature": temperature or None,
        }.items()
        if v
    }
    if gen_kwargs:
        generate = GenerateOverrides(**gen_kwargs)

    pipeline_list = [p.strip() for p in (pipeline or "").split(",") if p.strip()] or None

    req = CatRequest(
        path=path,
        mode=mode,
        profile=profile or None,
        n=n if n not in (None, 0) else None,
        no_cache=no_cache,
        pipeline=pipeline_list,
        encode=encode,
        generate=generate,
    )
    try:
        resp = routes.cat(req)
    except HTTPException as e:
        return _format_error(e), ""
    info = (
        f"path: {resp.path}\n"
        f"mode: {resp.mode}\n"
        f"profile: {profile or '(active)'}\n"
        f"bytes_processed: {resp.bytes_processed:,}\n"
        f"cached: {resp.cached}"
    )
    return resp.content, info


def _do_grep(
    pattern: str,
    directory: str,
    kind: str,
    ext: str,
    context_lines: int,
    ignore_case: bool,
    limit: int,
) -> tuple[list[list[Any]], str]:
    """Grep is always semantic + pre-index; binary files are searched via embeddings."""
    if not pattern:
        return [], "[error] pattern is required"

    req = GrepRequest(
        pattern=pattern,
        directory=directory or None,
        kind=kind or None,
        ext=ext or None,
        context_lines=int(context_lines or 0),
        semantic=True,
        pre_index=True,
        ignore_case=ignore_case,
        no_ignore=False,
        limit=int(limit or 200),
    )
    try:
        resp = routes.grep(req)
    except HTTPException as e:
        return [], _format_error(e)

    rows: list[list[Any]] = [[m.path, m.line_number, m.line] for m in resp.matches]
    summary = (
        f"{resp.total_matches} matches across {len(resp.file_counts)} files "
        f"(showing {len(resp.matches)})"
    )
    return rows, summary


def _do_list_profiles() -> tuple[list[list[Any]], str]:
    resp = routes.list_profiles()
    rows = [
        [p.name, p.base_url, p.model, "✓" if p.is_active else "", "✓" if p.api_key else ""]
        for p in resp.profiles
    ]
    return rows, f"active: {resp.active}"


def _do_refresh_cat_profile() -> Any:
    choices, active = _profile_choices()
    return gr.update(choices=choices, value=active)


def _do_add_profile(
    name: str, base_url: str, model: str, api_key: str
) -> tuple[list[list[Any]], str]:
    if not name or not base_url or not model:
        rows, _ = _do_list_profiles()
        return rows, "[error] name, base_url, and model are required"
    try:
        routes.create_profile(
            ProfileCreateRequest(name=name, base_url=base_url, model=model, api_key=api_key)
        )
    except HTTPException as e:
        rows, _ = _do_list_profiles()
        return rows, _format_error(e)
    rows, summary = _do_list_profiles()
    return rows, f"added '{name}'. {summary}"


def _do_update_profile(
    name: str, base_url: str, model: str, api_key: str
) -> tuple[list[list[Any]], str]:
    if not name:
        rows, _ = _do_list_profiles()
        return rows, "[error] name is required"
    body = ProfileUpdateRequest(
        base_url=base_url or None,
        model=model or None,
        api_key=api_key if api_key else None,
    )
    try:
        routes.update_profile_route(name, body)
    except HTTPException as e:
        rows, _ = _do_list_profiles()
        return rows, _format_error(e)
    rows, summary = _do_list_profiles()
    return rows, f"updated '{name}'. {summary}"


def _do_use_profile(name: str) -> tuple[list[list[Any]], str]:
    if not name:
        rows, _ = _do_list_profiles()
        return rows, "[error] name is required"
    try:
        routes.use_profile(name)
    except HTTPException as e:
        rows, _ = _do_list_profiles()
        return rows, _format_error(e)
    rows, summary = _do_list_profiles()
    return rows, f"switched to '{name}'. {summary}"


def _do_delete_profile(name: str) -> tuple[list[list[Any]], str]:
    if not name:
        rows, _ = _do_list_profiles()
        return rows, "[error] name is required"
    try:
        routes.delete_profile(name)
    except HTTPException as e:
        rows, _ = _do_list_profiles()
        return rows, _format_error(e)
    rows, summary = _do_list_profiles()
    return rows, f"removed '{name}'. {summary}"


def build_ui() -> gr.Blocks:
    """Construct and return the Gradio Blocks app."""
    default_dir = str(data_dir())
    initial_profiles, initial_active = _profile_choices()

    with gr.Blocks(title="mm app") as demo:
        gr.HTML(HEADER_HTML)

        with gr.Tabs():
            with gr.TabItem("Browse"):
                gr.HTML(
                    '<div class="mm-section"><h2>List Directory</h2>'
                    '<p class="mm-note">Mirrors <code>mm find &lt;dir&gt; --tree</code>.</p></div>'
                )
                with gr.Row(elem_classes=["mm-twocol"]):
                    with gr.Column(elem_classes=["mm-result"]):
                        ld_tree = gr.Code(label="Tree", language=None, lines=22)
                        with gr.Accordion("Raw JSON", open=False):
                            ld_json = gr.Code(language="json", lines=14)
                    with gr.Column(elem_classes=["mm-config", "mm-config-panel"]):
                        ld_dir = gr.Textbox(
                            label="Directory",
                            value=default_dir,
                            interactive=False,
                            elem_classes=["mm-readonly"],
                        )
                        ld_kind = gr.Textbox(label="Kind filter", placeholder="image,document")
                        ld_name = gr.Textbox(label="Name regex", placeholder=".*\\.pdf")
                        ld_btn = gr.Button("Scan", variant="primary")
                ld_btn.click(
                    _do_list_directory,
                    inputs=[ld_dir, ld_kind, ld_name],
                    outputs=[ld_tree, ld_json],
                )

            with gr.TabItem("Cat"):
                gr.HTML(
                    '<div class="mm-section"><h2>Cat</h2>'
                    '<p class="mm-note">Extract content. <code>mode = metadata|fast|accurate</code>.</p></div>'
                )
                with gr.Row(elem_classes=["mm-twocol"]):
                    with gr.Column(elem_classes=["mm-result"]):
                        cat_content = gr.Textbox(label="Content", lines=18)
                        cat_info = gr.Textbox(label="Info", lines=5, interactive=False)
                    with gr.Column(elem_classes=["mm-config", "mm-config-panel"]):
                        cat_path = gr.Textbox(
                            label="File path", placeholder="mmbench-tiny/photo.jpg"
                        )
                        cat_mode = gr.Dropdown(
                            choices=["metadata", "fast", "accurate"],
                            value="metadata",
                            label="Mode",
                        )
                        cat_n = gr.Number(label="n (head=+/tail=-)", value=0, precision=0)
                        cat_profile = gr.Dropdown(
                            choices=initial_profiles,
                            value=initial_active,
                            label="Profile (overrides active)",
                            allow_custom_value=True,
                        )
                        cat_profile_refresh = gr.Button("↻ Refresh profiles")
                        cat_no_cache = gr.Checkbox(label="No cache", value=False)
                        with gr.Accordion("Pipeline + overrides", open=False):
                            cat_pipeline = gr.Textbox(
                                label="Pipeline (comma-separated)",
                                placeholder="image/accurate, my-pipeline.yaml",
                            )
                            cat_strategy_opts = gr.Textbox(
                                label="encode.strategy_opts (key=value per line)",
                                placeholder="max_width=768\nfps=5",
                                lines=3,
                            )
                            cat_prompt = gr.Textbox(label="generate.prompt", lines=3)
                            cat_max_tokens = gr.Textbox(
                                label="generate.max_tokens", placeholder="256"
                            )
                            cat_temperature = gr.Textbox(
                                label="generate.temperature", placeholder="0.1"
                            )
                        cat_btn = gr.Button("Run cat", variant="primary")
                cat_btn.click(
                    _do_cat,
                    inputs=[
                        cat_path,
                        cat_mode,
                        cat_profile,
                        cat_n,
                        cat_no_cache,
                        cat_pipeline,
                        cat_strategy_opts,
                        cat_prompt,
                        cat_max_tokens,
                        cat_temperature,
                    ],
                    outputs=[cat_content, cat_info],
                )
                cat_profile_refresh.click(_do_refresh_cat_profile, outputs=[cat_profile])

            with gr.TabItem("Grep"):
                gr.HTML(
                    '<div class="mm-section"><h2>Grep</h2>'
                    '<p class="mm-note">Always runs <code>--semantic</code> with <code>--pre-index</code> '
                    "for binary files; text files use regex.</p></div>"
                )
                with gr.Row(elem_classes=["mm-twocol"]):
                    with gr.Column(elem_classes=["mm-result"]):
                        g_summary = gr.Textbox(label="Summary", interactive=False)
                        g_results = gr.Dataframe(
                            headers=["path", "line", "match"],
                            datatype=["str", "number", "str"],
                            label="Matches",
                            wrap=True,
                            row_count=(0, "dynamic"),
                        )
                    with gr.Column(elem_classes=["mm-config", "mm-config-panel"]):
                        g_pattern = gr.Textbox(
                            label="Pattern (required)", placeholder="attention | TODO"
                        )
                        g_dir = gr.Textbox(
                            label="Directory",
                            value=default_dir,
                            interactive=False,
                            elem_classes=["mm-readonly"],
                        )
                        g_kind = gr.Textbox(label="Kind", placeholder="document,image")
                        g_ext = gr.Textbox(label="Extension", placeholder=".pdf,.md")
                        g_context = gr.Number(label="Context lines (-C)", value=0, precision=0)
                        g_limit = gr.Number(label="Limit", value=200, precision=0)
                        g_ignore_case = gr.Checkbox(label="Ignore case (-i)", value=False)
                        g_btn = gr.Button("Run grep", variant="primary")
                g_btn.click(
                    _do_grep,
                    inputs=[
                        g_pattern,
                        g_dir,
                        g_kind,
                        g_ext,
                        g_context,
                        g_ignore_case,
                        g_limit,
                    ],
                    outputs=[g_results, g_summary],
                )

            with gr.TabItem("Profiles"):
                gr.HTML(
                    '<div class="mm-section"><h2>Profiles</h2>'
                    '<p class="mm-note">LLM provider configuration. Reserved profiles: '
                    "<code>ollama</code>, <code>gemini</code>, <code>vlmrun</code>.</p></div>"
                )
                p_status = gr.Textbox(label="Status", interactive=False)
                p_table = gr.Dataframe(
                    headers=["name", "base_url", "model", "active", "has_api_key"],
                    datatype=["str", "str", "str", "str", "str"],
                    label="Profiles",
                    wrap=True,
                    row_count=(0, "dynamic"),
                )
                p_refresh = gr.Button("Refresh")

                with gr.Accordion("Add profile", open=False):
                    with gr.Row():
                        a_name = gr.Textbox(label="name")
                        a_base_url = gr.Textbox(label="base_url")
                        a_model = gr.Textbox(label="model")
                        a_api_key = gr.Textbox(label="api_key", type="password")
                    a_btn = gr.Button("Add", variant="primary")

                with gr.Accordion("Update / Use / Delete", open=False):
                    with gr.Row():
                        u_name = gr.Textbox(label="name")
                        u_base_url = gr.Textbox(label="base_url (optional)")
                        u_model = gr.Textbox(label="model (optional)")
                        u_api_key = gr.Textbox(label="api_key (optional)", type="password")
                    with gr.Row():
                        u_update_btn = gr.Button("Update")
                        u_use_btn = gr.Button("Set active")
                        u_delete_btn = gr.Button("Delete", variant="stop")

                p_refresh.click(_do_list_profiles, outputs=[p_table, p_status])
                a_btn.click(
                    _do_add_profile,
                    inputs=[a_name, a_base_url, a_model, a_api_key],
                    outputs=[p_table, p_status],
                ).then(_do_refresh_cat_profile, outputs=[cat_profile])
                u_update_btn.click(
                    _do_update_profile,
                    inputs=[u_name, u_base_url, u_model, u_api_key],
                    outputs=[p_table, p_status],
                ).then(_do_refresh_cat_profile, outputs=[cat_profile])
                u_use_btn.click(_do_use_profile, inputs=[u_name], outputs=[p_table, p_status]).then(
                    _do_refresh_cat_profile, outputs=[cat_profile]
                )
                u_delete_btn.click(
                    _do_delete_profile, inputs=[u_name], outputs=[p_table, p_status]
                ).then(_do_refresh_cat_profile, outputs=[cat_profile])

                demo.load(_do_list_profiles, outputs=[p_table, p_status])

        gr.HTML(FOOTER_HTML)

    return demo
