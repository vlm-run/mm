"""Pydantic request/response schemas for the mm API surface."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

CatMode = Literal["metadata", "fast", "accurate"]


class EncodeOverrides(BaseModel):
    """Overrides for the encode stage of a cat pipeline."""

    strategy: Optional[str] = Field(default=None, description="Override encoder name")
    pyfunc: Optional[str] = Field(
        default=None, description="Custom Python transform (.py file or inline code)"
    )
    strategy_opts: Optional[dict[str, Any]] = Field(
        default=None,
        description="Per-encoder strategy options merged into spec.encode.strategy_opts",
    )


class GenerateOverrides(BaseModel):
    """Overrides for the generate stage of a cat pipeline."""

    prompt: Optional[str] = None
    max_tokens: Optional[str] = None
    temperature: Optional[str] = None
    json_mode: Optional[str] = None


class CatRequest(BaseModel):
    """``POST /cat`` body."""

    path: str = Field(description="File path, absolute or relative to data dir")
    mode: CatMode = Field(default="metadata", description="metadata | fast | accurate")
    profile: Optional[str] = Field(
        default=None,
        description="Profile to use for this call (overrides the active profile)",
    )
    n: Optional[int] = Field(default=None, description="Line limit: positive=head, negative=tail")
    pipeline: Optional[list[str]] = Field(
        default=None, description="Pipeline YAML paths or registered encoder names"
    )
    no_cache: bool = False
    encode: Optional[EncodeOverrides] = None
    generate: Optional[GenerateOverrides] = None
    verbose: bool = False


class CatResponse(BaseModel):
    path: str
    mode: CatMode
    content: str
    bytes_processed: int
    cached: bool


class GrepRequest(BaseModel):
    """``POST /grep`` body."""

    pattern: str = Field(description="Regex pattern (or natural-language query if semantic=True)")
    directory: Optional[str] = Field(
        default=None, description="Directory to search (defaults to API data dir)"
    )
    kind: Optional[str] = Field(default=None, description="Filter by file kind, comma-separated")
    ext: Optional[str] = Field(default=None, description="Filter by extension(s)")
    context_lines: int = Field(default=0, ge=0, description="Lines of context around matches")
    count: bool = False
    semantic: bool = Field(
        default=False, description="Run semantic vector search alongside regex (-s)"
    )
    pre_index: bool = Field(
        default=False, description="Index unindexed files before semantic search (--pre-index)"
    )
    ignore_case: bool = False
    no_ignore: bool = False
    limit: int = Field(default=200, ge=1, le=10_000, description="Max matches returned")


class GrepMatch(BaseModel):
    path: str
    line_number: int
    line: str
    context: Optional[list[str]] = None


class GrepResponse(BaseModel):
    pattern: str
    total_matches: int
    file_counts: dict[str, int]
    matches: list[GrepMatch]


class ListDirectoryResponse(BaseModel):
    """Tree response for ``/list-directory``, mirroring ``mm find --tree --format json``."""

    root: str
    files: int
    bytes: int
    tree: dict[str, Any]


class ProfileBase(BaseModel):
    name: str
    base_url: str
    api_key: str = ""
    model: str


class ProfileSummary(BaseModel):
    """Profile entry as returned by ``/profiles`` (api_key masked)."""

    name: str
    base_url: str
    model: str
    api_key: str = ""
    is_active: bool = False


class ProfileListResponse(BaseModel):
    active: str
    profiles: list[ProfileSummary]


class ProfileCreateRequest(BaseModel):
    name: str
    base_url: str
    model: str
    api_key: str = ""


class ProfileUpdateRequest(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
