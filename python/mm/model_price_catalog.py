"""Model pricing catalog for cost estimation.

Loads a bundled price catalog (``python/mm/data/model-price-catalog.json``, sourced
from https://www.llm-prices.com/current-v1.json) and provides model
lookup + cost computation from token usage dicts.

Example::

    from mm.model_price_catalog import PriceCatalog

    catalog = PriceCatalog()
    cost = catalog.compute_cost(
        {"prompt_tokens": 1000, "completion_tokens": 500, "cached_tokens": 0, "total_tokens": 1500},
        model="google/gemini-2.5-flash",
    )
    if cost:
        print(f"${cost.total_cost:.4f}")
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_CATALOG_PATH = Path(__file__).parent / "data" / "model-price-catalog.json"


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """Pricing for a single model (per-million-token USD)."""

    id: str
    vendor: str
    name: str
    input_price: float
    output_price: float
    cached_price: float | None


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    """Computed cost from a token usage dict."""

    input_cost: float
    output_cost: float
    cached_cost: float
    total_cost: float
    model_id: str


def _normalize(model: str) -> str:
    """Normalize a model name for matching against catalog IDs.

    Strips vendor prefixes (``google/``, ``openai/``, etc.), lowercases,
    and removes common version/date suffixes that vary between providers.
    """
    s = model.lower().strip()
    if "/" in s:
        s = s.rsplit("/", 1)[-1]
    s = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", s)
    s = re.sub(r":\w+$", "", s)
    return s


class PriceCatalog:
    """In-memory price catalog loaded from the bundled JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        data_path = path or _CATALOG_PATH
        raw = json.loads(data_path.read_text())
        self._updated_at: str = raw.get("updated_at", "")
        self._prices: list[ModelPrice] = [
            ModelPrice(
                id=p["id"],
                vendor=p["vendor"],
                name=p["name"],
                input_price=float(p["input"]),
                output_price=float(p["output"]),
                cached_price=float(p["input_cached"])
                if p.get("input_cached") is not None
                else None,
            )
            for p in raw.get("prices", [])
        ]
        self._by_id: dict[str, ModelPrice] = {p.id: p for p in self._prices}
        self._by_norm: dict[str, ModelPrice] = {_normalize(p.id): p for p in self._prices}

    @property
    def updated_at(self) -> str:
        return self._updated_at

    @property
    def models(self) -> list[ModelPrice]:
        return list(self._prices)

    def lookup(self, model: str) -> ModelPrice | None:
        """Find a catalog entry for *model*.

        Tries exact ID match, then normalized match (stripping vendor
        prefixes and version suffixes), then substring match.
        """
        if not model:
            return None

        exact = self._by_id.get(model)
        if exact:
            return exact

        norm = _normalize(model)
        if not norm:
            return None

        normalized = self._by_norm.get(norm)
        if normalized:
            return normalized

        for pid, p in self._by_norm.items():
            if pid and (pid in norm or norm in pid):
                return p

        return None

    def compute_cost(self, usage: dict[str, int], model: str) -> CostBreakdown | None:
        """Compute cost from a token-usage dict and model name.

        Returns ``None`` when the model is not in the catalog.
        """
        price = self.lookup(model)
        if price is None:
            return None

        prompt = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)
        cached = usage.get("cached_tokens", 0)

        billable_input = max(prompt - cached, 0)
        input_cost = billable_input * price.input_price / 1_000_000

        if cached > 0 and price.cached_price is not None:
            cached_cost = cached * price.cached_price / 1_000_000
        elif cached > 0:
            cached_cost = cached * price.input_price / 1_000_000
        else:
            cached_cost = 0.0

        output_cost = completion * price.output_price / 1_000_000

        return CostBreakdown(
            input_cost=input_cost,
            output_cost=output_cost,
            cached_cost=cached_cost,
            total_cost=input_cost + cached_cost + output_cost,
            model_id=price.id,
        )


_catalog: PriceCatalog | None = None


def get_price_catalog() -> PriceCatalog:
    """Return the shared price catalog, built once from the bundled JSON."""
    global _catalog
    if _catalog is None:
        _catalog = PriceCatalog()
    return _catalog
