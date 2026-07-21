"""Extraction and accumulation logic for ``mm cat``.

Extracted from ``cat.py`` to separate the extraction/pipeline dispatch
path from the CLI command and rendering logic.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

from mm.cat_utils.base_utils import (
    CatOpts,
    RunResult,
    effective_model,
    override_extra,
)
from mm.cat_utils.extract_meta import extract_meta, extract_text
from mm.utils import file_kind

if TYPE_CHECKING:
    from mm.constants import BinaryFileKind
    from mm.pipelines.schema import PipelineSpec


@dataclass
class CatRunState:
    """Per-invocation accumulator for ``mm cat`` timing/cost/report state.

    Replaces the former module-level globals. ``token_cost`` and ``total_bytes``
    are accumulated in the main thread after concurrent work completes;
    ``was_cached`` and ``report_output`` are set/appended from ``extract``
    (idempotent bool set, GIL-safe list append).
    """

    total_bytes: int = 0
    was_cached: bool = False
    report_output: list[str] = field(default_factory=list)
    total_token_cost: float = 0.0


def is_passthrough(kind: str, ext: str, mode: str) -> bool:
    """Return True when the file should bypass the encode→generate pipeline."""
    from mm.constants import OFFICE_EXTS

    return kind == "text" or (
        kind == "document"
        and (
            (ext != ".pdf" and ext not in OFFICE_EXTS)
            or (ext in OFFICE_EXTS and mode != "accurate")
        )
    )


def extract(
    path: Path, opts: CatOpts, state: CatRunState | None = None
) -> tuple[str, RunResult | None]:
    """Pipeline-driven extraction dispatch with unified extraction caching.

    Returns ``(content, run_result)`` where ``run_result`` is the
    :class:`RunResult` from the encode→generate pipeline, or ``None``
    for passthrough / cache-hit / dry-run paths.

    Args:
        path: File to extract.
        opts: Resolved cat options.
        state: Per-invocation accumulator for bytes/cached/cost.
    """
    if state is None:
        state = CatRunState()
    kind = file_kind(path)
    ext = path.suffix.lower()
    if opts.dry_run:
        return dry_run_preview(path, kind, ext, opts), None

    if is_passthrough(kind, ext, opts.mode):
        assert kind in ("document", "text")
        content, cached = extract_text(path, kind)  # type: ignore[arg-type]
        if cached:
            state.was_cached = True
        return content, None

    kind = cast("BinaryFileKind", kind)
    from mm.constants import OFFICE_EXTS
    from mm.encoders.auto_strategy import resolve_auto_strategy
    from mm.pipelines import apply_overrides
    from mm.pipelines.pipelines_utils import resolve_pipeline
    from mm.profile import get_profile
    from mm.store.utils import get_content_hash, shared_db

    db = shared_db()
    profile = get_profile()

    spec = resolve_pipeline(opts, kind)
    spec = apply_overrides(spec, opts.encode_overrides or None, opts.generate_overrides or None)
    spec = resolve_auto_strategy(path, spec, opts)

    eff_model = effective_model(spec, profile.model)
    extra = override_extra(
        opts.encode_overrides,
        opts.generate_overrides,
        opts.pipelines,
    )

    extraction_id: str | None = None
    content_hash = get_content_hash(path)
    if content_hash:
        from mm.store.utils import get_extraction_id

        extraction_id = get_extraction_id(
            content_hash,
            profile.name,
            eff_model,
            opts.mode,
            False,
            extra=extra,
        )

        if not opts.no_cache:
            cached = db.get_extraction(extraction_id)
            if cached is not None:
                state.was_cached = True
                if opts.report:
                    state.report_output.append(
                        f"Report skipped for {path.name}: result served from cache. "
                        "Use --no-cache to regenerate."
                    )
                if opts.verbose:
                    meta = db.get_extraction_metadata(extraction_id)
                    suffix = meta.get("verbose_suffix") if meta else None
                    if suffix:
                        return f"{cached}\n\n{suffix}", None
                return cached, None
        else:
            db.evict_extraction(extraction_id)

    if ext in OFFICE_EXTS and opts.mode == "accurate":
        with tempfile.TemporaryDirectory(prefix="mm-office-") as tmpdir:
            from mm._mm import office_to_pdf

            tmp_pdf = Path(tmpdir) / f"{path.stem}.pdf"
            office_to_pdf(str(path), str(tmp_pdf))
            run = run_accurate(tmp_pdf, kind, spec, opts, meta_path=path)
    elif opts.mode == "accurate":
        run = run_accurate(path, kind, spec, opts)
    else:
        run = run_fast(path, kind, spec, opts)

    if content_hash and run.content and not run.content.startswith("["):
        uri = str(path.resolve())
        meta = {"verbose_suffix": run.verbose_suffix} if run.verbose_suffix else None
        extract_meta(path, kind)
        try:
            db.put_extraction(
                uri=uri,
                content_hash=content_hash,
                profile=profile.name,
                model=eff_model,
                content=run.content,
                mode=opts.mode,
                detail=False,
                extra=extra,
                metadata=meta,
            )
        except RuntimeError:
            return format_run(run, opts.verbose), run
    return format_run(run, opts.verbose), run


def format_run(run: RunResult, verbose: bool) -> str:
    """Render a :class:`RunResult` for display, conditionally including the suffix."""
    if verbose and run.verbose_suffix:
        return f"{run.content}\n\n{run.verbose_suffix}"
    return run.content


def run_fast(path: Path, kind: BinaryFileKind, spec: PipelineSpec, opts: CatOpts) -> RunResult:
    """Fast mode: run the kind's fast pipeline."""
    from mm.cat_utils.run_encoder import run_encoder

    if getattr(opts, "no_generate", False):
        import dataclasses

        spec = dataclasses.replace(spec, generate=None)
    if spec.encode.strategy:
        return run_encoder(path, kind, spec, opts)

    return RunResult(content=extract_meta(path, kind, no_cache=opts.no_cache))


def run_accurate(
    path: Path,
    kind: BinaryFileKind,
    spec: PipelineSpec,
    opts: CatOpts,
    *,
    meta_path: Path | None = None,
) -> RunResult:
    """Accurate mode: LLM-powered semantic extraction.

    ``spec`` is the merged (YAML + CLI) pipeline spec resolved by
    ``extract``; this function does no further override application
    ``meta_path`` reference to the original office file
    """
    if getattr(opts, "no_generate", False):
        import dataclasses

        spec = dataclasses.replace(spec, generate=None)

    extract_meta(meta_path or path, kind, no_cache=opts.no_cache)

    return accurate_dispatch(path, kind, spec, opts)


def accurate_dispatch(
    path: Path, kind: BinaryFileKind, spec: PipelineSpec, opts: CatOpts
) -> RunResult:
    """Dispatch accurate-mode extraction based on file kind."""
    from mm.cat_utils.accurate_audio import accurate_audio
    from mm.cat_utils.accurate_image import accurate_image
    from mm.cat_utils.accurate_video import accurate_video

    if kind == "image":
        return accurate_image(path, spec, opts)
    if kind == "video":
        return accurate_video(path, spec, opts)
    if kind == "audio":
        return accurate_audio(path, spec, opts)

    from mm.cat_utils.run_encoder import run_encoder

    if spec.encode.strategy:
        return run_encoder(path, kind, spec, opts)

    return RunResult(content=extract_meta(path, kind))


def write_report(
    entries: list[tuple[Path, RunResult]], output_dir: Path | None, state: CatRunState
) -> None:
    """Write a combined HTML report for all collected pipeline runs."""
    from datetime import datetime

    from mm.cat_utils.report import generate_report

    html_doc = generate_report(entries)
    out_dir = output_dir or Path("mm_reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if len(entries) == 1:
        filename = f"{entries[0][0].name}_{timestamp}_report.html"
    else:
        filename = f"multi_{timestamp}_report.html"
    out_path = out_dir / filename
    out_path.write_text(html_doc, encoding="utf-8")
    state.report_output.append(f"Report written to {out_path}")


def dry_run_preview(path: Path, kind: str, ext: str, opts: CatOpts) -> str:
    """Render the resolved pipeline for ``path × opts.mode`` without invoking it.

    For passthrough kinds (``kind=text``, or non-PDF/non-office documents),
    emit a short header/info block.
    """
    from mm.constants import OFFICE_EXTS
    from mm.display import format_size
    from mm.encoders.auto_strategy import resolve_auto_strategy
    from mm.pipelines import apply_overrides
    from mm.pipelines.pipelines_utils import resolve_pipeline
    from mm.profile import get_profile

    if is_passthrough(kind, ext, opts.mode):
        size_str = format_size(path.stat().st_size)
        header = f"\n# {path} (kind={kind}, mode={opts.mode}) — passthrough preview (--dry-run)"
        info_lines = [
            f"  ├─ size: {size_str}",
            "  └─ passthrough: content emitted as-is \\[skipped via --dry-run]",
        ]
        return "\n".join(["[dim]", header, "passthrough", *info_lines, "[/dim]"])

    spec = resolve_pipeline(opts, kind)
    spec = apply_overrides(spec, opts.encode_overrides or None, opts.generate_overrides or None)
    autoencode = spec.encode.strategy == "auto" or (
        spec.encode.strategy is None and spec.generate is not None
    )
    spec = resolve_auto_strategy(path, spec, opts)
    header = f"\n# {path} (kind={kind}, mode={opts.mode}) — pipeline preview (--dry-run)"

    encode = spec.encode
    strategy = encode.strategy or "<unspecified>"
    strategy = f"auto → {strategy}" if autoencode else strategy
    enc_opts = encode.strategy_opts or {}
    enc_opts_str = (
        ", ".join(f"{k}={v}" for k, v in sorted(enc_opts.items())) if enc_opts else "<defaults>"
    )

    if spec.generate is not None:
        gen = spec.generate
        lines = (gen.prompt or "").strip().splitlines()
        first_line = lines[0] if lines else ""
        if len(first_line) > 60:
            first_line = first_line[:60] + "..."

        prompt_part = f' · prompt="{first_line}"' if first_line else ""
        profile = get_profile()
        eff = gen.model or profile.model
        gen_line = (
            f"generate: profile={profile.name} · model={eff}{prompt_part}  [skipped via --dry-run]"
        )
    else:
        gen_line = "generate: <none>  [encode-only pipeline]"

    if ext in OFFICE_EXTS and opts.mode == "accurate":
        header += " [routes through office→PDF before encode]"

    middle: list[str] = [f"  ├─ encode: {strategy} · {enc_opts_str}"]
    if encode.pyfunc:
        middle.append(f"  ├─ pyfunc: {encode.pyfunc}")

    return "\n".join(["[dim]", header, "pipeline", *middle, f"  └─ {gen_line}", "[/dim]"])
