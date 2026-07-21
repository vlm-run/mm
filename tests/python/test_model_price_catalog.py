"""Tests for the pricing catalog and cost computation."""

from __future__ import annotations

from mm.model_price_catalog import PriceCatalog


def test_catalog_loads_bundled_file() -> None:
    catalog = PriceCatalog()
    assert catalog.updated_at
    assert len(catalog.models) > 50


def test_exact_id_match() -> None:
    catalog = PriceCatalog()
    price = catalog.lookup("gemini-2.5-flash")
    assert price is not None
    assert price.id == "gemini-2.5-flash"
    assert price.vendor == "google"
    assert price.input_price == 0.3
    assert price.output_price == 2.5
    assert price.cached_price == 0.03


def test_vendor_prefix_match() -> None:
    catalog = PriceCatalog()
    price = catalog.lookup("google/gemini-2.5-flash")
    assert price is not None
    assert price.id == "gemini-2.5-flash"


def test_case_insensitive_match() -> None:
    catalog = PriceCatalog()
    price = catalog.lookup("GEMINI-2.5-FLASH")
    assert price is not None
    assert price.id == "gemini-2.5-flash"


def test_ollama_tag_match() -> None:
    catalog = PriceCatalog()
    price = catalog.lookup("gpt-4o:latest")
    assert price is not None
    assert price.id == "gpt-4o"


def test_no_match_returns_none() -> None:
    catalog = PriceCatalog()
    assert catalog.lookup("qwen/qwen3.5-0.8b") is None
    assert catalog.lookup("") is None
    assert catalog.lookup("nonexistent-model-xyz") is None


def test_compute_cost_basic() -> None:
    catalog = PriceCatalog()
    usage = {
        "prompt_tokens": 1_000_000,
        "completion_tokens": 500_000,
        "cached_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 1_500_000,
    }
    cost = catalog.compute_cost(usage, "gemini-2.5-flash")
    assert cost is not None
    assert cost.model_id == "gemini-2.5-flash"
    assert cost.input_cost == 0.3
    assert cost.output_cost == 1.25
    assert cost.cached_cost == 0.0
    assert abs(cost.total_cost - 1.55) < 1e-9


def test_compute_cost_with_cached_tokens() -> None:
    catalog = PriceCatalog()
    usage = {
        "prompt_tokens": 1_000_000,
        "completion_tokens": 0,
        "cached_tokens": 800_000,
        "reasoning_tokens": 0,
        "total_tokens": 1_000_000,
    }
    cost = catalog.compute_cost(usage, "gemini-2.5-flash")
    assert cost is not None
    assert cost.input_cost == 0.06
    assert cost.cached_cost == 0.024
    assert abs(cost.total_cost - 0.084) < 1e-9


def test_compute_cost_cached_null_falls_back_to_input_price() -> None:
    catalog = PriceCatalog()
    price = catalog.lookup("gpt-4o")
    assert price is not None
    assert price.cached_price is not None

    usage = {
        "prompt_tokens": 1_000_000,
        "completion_tokens": 0,
        "cached_tokens": 500_000,
        "reasoning_tokens": 0,
        "total_tokens": 1_000_000,
    }
    cost = catalog.compute_cost(usage, "gpt-4o")
    assert cost is not None
    assert cost.input_cost == 1.25
    assert cost.cached_cost == 0.625
    assert abs(cost.total_cost - 1.875) < 1e-9


def test_compute_cost_model_not_in_catalog() -> None:
    catalog = PriceCatalog()
    usage = {
        "prompt_tokens": 1000,
        "completion_tokens": 500,
        "cached_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 1500,
    }
    assert catalog.compute_cost(usage, "nonexistent-model") is None


def test_compute_cost_small_usage() -> None:
    catalog = PriceCatalog()
    usage = {
        "prompt_tokens": 1121,
        "completion_tokens": 22,
        "cached_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 1143,
    }
    cost = catalog.compute_cost(usage, "gemini-3.1-flash-lite-preview")
    assert cost is not None
    assert cost.total_cost > 0
    assert cost.total_cost < 0.01
