"""Single multi-image chat-completion helper for vlmgw benchmarks.

Times the gateway round-trip cost of a *single* chat completion that
attaches multiple ``image_url`` content parts to one user message --
in contrast to ``mm cat <file1> <file2>`` which iterates over files
client-side and fires one independent gateway request per file.

Profile resolution mirrors ``mm cat``: :class:`mm.llm.LlmBackend`
walks the same precedence (CLI flags > env vars > active mm profile)
to pick up ``base_url`` / ``api_key``. Only ``--model`` is overridden
explicitly on the call site so the bench can pin a model regardless
of the active profile's default.

Usage::

    python benchmarks/_multi_image_call.py \\
        --model qwen/qwen3.5-0.8b \\
        --prompt 'Compare these two images.' \\
        path/to/img1.jpg path/to/img2.jpg

Existence check: this is a benchmark utility, not a public mm CLI;
keep it intentionally tiny so the timing measures the gateway, not
our wrapper.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mm.llm import LlmBackend, image_part


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True, help="Pinned model id (e.g. qwen/qwen3.5-0.8b).")
    ap.add_argument(
        "--prompt",
        required=True,
        help="Single user-message text prefix; images attach after.",
    )
    ap.add_argument(
        "--max-tokens",
        type=int,
        default=128,
        help="Cap on completion length (default 128, mirroring mm cat's fast pipeline).",
    )
    ap.add_argument("files", nargs="+", type=Path, help="Image files to attach.")
    args = ap.parse_args(argv)

    backend = LlmBackend(model=args.model)

    # One ``user`` message with text first, then N image parts -- the
    # canonical multi-image chat completion shape supported by every
    # OpenAI-compatible vlm gateway.
    parts = [image_part(p) for p in args.files]
    messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": args.prompt}, *parts],
        }
    ]

    out = backend._chat(messages, max_tokens=args.max_tokens)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
