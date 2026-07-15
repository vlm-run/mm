"""HTML report generation for ``mm cat --report``.

Builds a self-contained HTML document visualising the pipeline internals
(encoder output messages, LLM chat completions messages, and the LLM response)
for one or more files processed by ``mm cat``.

Reuses :func:`mm.notebook.render_messages` for the styled message rendering
(zoomable image galleries, text parts, role badges, stats footer).
"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from mm.cat_utils.base_utils import RunResult


def _fmt_ms(ms: float | None) -> str:
    if ms is None:
        return "—"
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms / 1000:.2f}s"


def _render_pipeline_summary(path: Path, run: RunResult) -> str:
    """Render the pipeline metadata header for a single file."""
    spec = run.pipeline_spec
    strategy: str = spec.encode.strategy if spec and spec.encode.strategy else "—"
    mode = spec.mode if spec else "—"
    kind = spec.kind if spec else "—"

    opts_str = ""
    if spec and spec.encode.strategy_opts:
        opts_str = ", ".join(f"{k}={v}" for k, v in sorted(spec.encode.strategy_opts.items()))

    gen_model = "—"
    if spec and spec.generate and spec.generate.model:
        gen_model = spec.generate.model
    elif spec and spec.generate:
        from mm.profile import get_profile

        gen_model = f"{get_profile().model} (profile)"

    usage_str = "—"
    if run.llm_usage:
        u = run.llm_usage
        usage_str = f"{u['prompt_tokens']}→{u['completion_tokens']} tokens"

    rows = [
        ("File", str(path)),
        ("Kind", kind),
        ("Mode", mode),
        ("Encoder", strategy),
        ("Strategy opts", opts_str or "—"),
        ("Generate model", gen_model),
        ("Encode time", _fmt_ms(run.encode_elapsed_ms)),
        ("Generate time", _fmt_ms(run.generate_elapsed_ms)),
        ("Token usage", usage_str),
    ]
    body = "\n".join(
        f'<tr><td class="mm-rpt-key">{html.escape(k)}</td>'
        f'<td class="mm-rpt-val">{html.escape(v)}</td></tr>'
        for k, v in rows
    )
    return f'<table class="mm-rpt-summary"><tbody>{body}</tbody></table>'


def _render_file_section(path: Path, run: RunResult) -> str:
    """Render the full report section for one file."""
    from mm.notebook import render_messages

    parts: list[str] = []
    parts.append(f'<h2 class="mm-rpt-file-h">{html.escape(path.name)}</h2>')
    parts.append(_render_pipeline_summary(path, run))

    if run.llm_messages:
        parts.append(
            render_messages(
                run.llm_messages,
                title=f"Chat completions request — {path.name}",
                max_image_width=480,
            )
        )
    elif run.encoded_messages:
        parts.append(
            render_messages(
                run.encoded_messages,
                title=f"Encoder output — {path.name}",
                max_image_width=480,
            )
        )

    if run.llm_response:
        resp_msgs = [{"role": "assistant", "content": run.llm_response}]
        parts.append(
            render_messages(
                resp_msgs,
                title=f"LLM response — {path.name}",
                max_image_width=480,
            )
        )

    return f'<div class="mm-rpt-section">{"".join(parts)}</div>'


_CSS = """
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background: #f6f8fa;
        margin: 0;
        padding: 24px;
    }
    .mm-rpt-header {
        max-width: 960px;
        margin: 0 auto 16px;
    }
    .mm-rpt-header h1 {
        font-size: 18px;
        margin: 0 0 4px;
    }
    .mm-rpt-header .mm-rpt-sub {
        font-size: 12px;
        color: #656d76;
    }
    .mm-rpt-section {
        max-width: 960px;
        margin: 0 auto 24px;
    }
    .mm-rpt-file-h {
        font-size: 15px;
        margin: 0 0 8px;
        padding-bottom: 4px;
        border-bottom: 1px solid #d1d9e0;
    }
    .mm-rpt-summary {
        border-collapse: collapse;
        font-size: 11px;
        margin-bottom: 12px;
        width: 100%;
    }
    .mm-rpt-summary td {
        padding: 2px 12px 2px 0;
        vertical-align: top;
    }
    .mm-rpt-key {
        color: #656d76;
        font-weight: 600;
        white-space: nowrap;
        width: 120px;
    }
    .mm-rpt-val {
        color: #1a1a2e;
        font-family: "SF Mono", Menlo, Consolas, monospace;
        font-size: 11px;
    }
    /* Widen notebook render root for standalone viewing */
    .mm-rpt-section > div[class$="-root"] {
        max-width: 960px;
    }
"""


def generate_report(
    entries: list[tuple[Path, RunResult]],
) -> str:
    """Build a self-contained HTML report for one or more pipeline runs.

    Args:
        entries: List of ``(path, RunResult)`` tuples, one per file.

    Returns:
        Full HTML document string (``<!DOCTYPE html>`` ... ``</html>``).
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    n = len(entries)
    file_label = "1 file" if n == 1 else f"{n} files"

    sections = "\n".join(_render_file_section(p, r) for p, r in entries)

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        f"<title>mm cat report — {file_label} — {timestamp}</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n<body>\n"
        '<div class="mm-rpt-header">'
        f"<h1>mm cat report</h1>"
        f'<div class="mm-rpt-sub">{file_label} · {timestamp}</div>'
        "</div>\n"
        f"{sections}\n"
        "</body>\n</html>"
    )
