"""Pipeline-driven content extraction — the source of truth behind ``mm cat``.

This module owns the full ``encode → generate`` extraction workflow
(passthrough detection, pipeline resolution, extraction caching, and the
fast / accurate dispatch). It lives in the library so that ``Context.cat``,
``Context.to_md``, the semantic index, and the ``mm cat`` command all share
one implementation — none of them re-implement extraction.

The command layer is responsible only for presentation (Rich rendering,
``--format`` serialization, throughput readouts); it calls :func:`extract`
and renders the returned :class:`~mm.results.CatResult`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, cast

from mm.cat_utils.base_utils import CatOpts, RunResult, effective_model, override_extra
from mm.cat_utils.extract_meta import extract_meta
from mm.results import CatResult
from mm.utils import file_kind

if TYPE_CHECKING:
    from mm.constants import BinaryFileKind
    from mm.pipelines.schema import PipelineSpec


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


def format_run(run: RunResult, verbose: bool) -> str:
    """Render a :class:`RunResult` for display, conditionally including the suffix."""
    if verbose and run.verbose_suffix:
        return f"{run.content}\n\n{run.verbose_suffix}"
    return run.content


def extract(path: Path, opts: CatOpts) -> CatResult:
    """Extract content for ``path`` under ``opts``, with caching.

    Args:
        path: File to extract.
        opts: Resolved :class:`~mm.cat_utils.base_utils.CatOpts` controlling
            mode, overrides, caching, and verbosity.

    Returns:
        A :class:`~mm.results.CatResult` carrying the extracted ``content``,
        the ``mode`` that produced it, the file ``kind``, and whether it was
        served from cache (``cached``).
    """
    kind = file_kind(path)
    ext = path.suffix.lower()

    if opts.dry_run:
        return CatResult(
            path=str(path),
            content=dry_run_preview(path, kind, ext, opts),
            mode=opts.mode,
            kind=kind,
        )

    if is_passthrough(kind, ext, opts.mode):
        from mm.cat_utils.extract_meta import extract_text

        assert kind in ("document", "text")
        content, cached = extract_text(path, kind)  # type: ignore[arg-type]
        return CatResult(
            path=str(path), content=content, mode=opts.mode, kind=kind, cached=bool(cached)
        )

    kind = cast("BinaryFileKind", kind)
    from mm.constants import OFFICE_EXTS
    from mm.encoders.auto_strategy import resolve_auto_strategy
    from mm.pipelines import apply_overrides
    from mm.pipelines.pipelines_utils import resolve_pipeline
    from mm.profile import get_profile
    from mm.store.utils import get_content_hash, shared_db

    db = shared_db()
    profile = get_profile()

    # Resolve & merge the pipeline spec exactly once so the cache key reflects
    # the effective model and the merged extra_body — required for correct
    # invalidation on `--model` / `--generate.extra-body` changes.
    spec = resolve_pipeline(opts, kind)
    spec = apply_overrides(spec, opts.encode_overrides or None, opts.generate_overrides or None)
    spec = resolve_auto_strategy(path, spec, opts)

    eff_model = effective_model(spec, profile.model)
    extra = override_extra(opts.encode_overrides, opts.generate_overrides, opts.pipelines)

    extraction_id: str | None = None
    content_hash = get_content_hash(path)
    if content_hash:
        from mm.store.utils import get_extraction_id

        extraction_id = get_extraction_id(
            content_hash, profile.name, eff_model, opts.mode, False, extra=extra
        )

        if not opts.no_cache:
            cached = db.get_extraction(extraction_id)
            if cached is not None:
                content = cached
                if opts.verbose:
                    meta = db.get_extraction_metadata(extraction_id)
                    suffix = meta.get("verbose_suffix") if meta else None
                    if suffix:
                        content = f"{cached}\n\n{suffix}"
                return CatResult(
                    path=str(path), content=content, mode=opts.mode, kind=kind, cached=True
                )
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
        extract_meta(path, kind)
        uri = str(path.resolve())
        meta = {"verbose_suffix": run.verbose_suffix} if run.verbose_suffix else None
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
            pass
    return CatResult(
        path=str(path), content=format_run(run, opts.verbose), mode=opts.mode, kind=kind
    )


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
    :func:`extract`; this function does no further override application.
    ``meta_path`` references the original office file when routing through PDF.
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


def dry_run_preview(path: Path, kind: str, ext: str, opts: CatOpts) -> str:
    """Render the resolved pipeline for ``path × opts.mode`` without invoking it.

    For passthrough kinds (``kind=text``, or non-PDF/non-office documents),
    emit a short header/info block instead of a pipeline tree.
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
