"""markdown encoder: gateway OCR of a whole document into markdown.

Sends the document to the VLM Run gateway as a single ``document_url`` content
part (base64 ``data:`` URI) and asks a document-OCR model to transcribe it into
clean markdown. The OCR model is parametrized — pick one of the gateway's
document models and it is passed through as the chat-completions ``model``:

* ``dots-mocr``     — **default**, multimodal document OCR.
* ``glm-ocr``       — GLM document OCR.
* ``deepseek-ocr``  — DeepSeek document OCR.

Unlike ``page-text`` (local pypdfium2 text extraction) this works on
scanned/image-only PDFs, since rendering + OCR happen server-side.

The model default lives in this encoder's ``generate`` override, so
``mm cat doc.pdf -p markdown`` uses ``dots-mocr`` out of the box. Override per
call with ``--model`` / ``--generate.model``::

    mm cat doc.pdf -p markdown                    # dots-mocr (default)
    mm cat doc.pdf -p markdown --model glm-ocr
    mm cat doc.pdf -p markdown --model deepseek-ocr
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from mm.encoders import register
from mm.encoders.base import Message
from mm.encoders.document.document_url import DocumentUrl, document_url_message
from mm.pipelines.schema import Generate

OCR_MODELS: tuple[str, ...] = ("dots-mocr", "glm-ocr", "deepseek-ocr")
"""Document-OCR models on the gateway that this encoder targets."""

DEFAULT_OCR_MODEL: str = "dots-mocr"
"""Model used when the caller does not pass ``--model`` / ``--generate.model``."""

_OCR_PROMPT = (
    "Convert this document ({filename}) into clean, well-structured markdown. "
    "Transcribe every page in reading order. Preserve headings, lists, tables, "
    "and inline emphasis. The conversion should be lossless — do not summarize, "
    "omit, or invent content. Output only the markdown."
)


def _ocr_generate() -> Generate:
    """Generate override pinning the default OCR model and markdown prompt."""
    return Generate(prompt=_OCR_PROMPT, model=DEFAULT_OCR_MODEL, max_tokens=16384)


class Markdown(DocumentUrl):
    """Document → ``document_url`` → gateway OCR model → markdown.

    Inherits the ``document_url`` part encoding from :class:`DocumentUrl` and
    layers a model-parametrized OCR generate step on top. The ``generate``
    override sets the default model (``dots-mocr``); ``--model`` overrides it.
    """

    name = "markdown"
    kind = "document"
    generate = {"fast": _ocr_generate(), "accurate": _ocr_generate()}

    def encode(self, path: Path, **kwargs: Any) -> Iterable[Message]:
        yield document_url_message(path)


register(Markdown())
