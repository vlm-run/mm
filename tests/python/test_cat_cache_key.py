"""Cache-key canonicalisation tests for ``mm cat``.

The L2 cache fragment for `mm cat` is built from the user's overrides. Dict-
valued overrides (notably ``strategy_opts``) preserve insertion order in
their default ``repr``, so without canonicalisation, two CLI invocations
with the same flags in a different order would produce different cache
keys and trigger a redundant LLM call on cache miss.
"""

from __future__ import annotations

from mm.commands.cat import _override_extra


def test_strategy_opts_order_independence():
    """Same overrides, different CLI order → identical cache fragment."""
    a = _override_extra({"strategy_opts": {"max_width": 768, "fps": 5}}, {}, {})
    b = _override_extra({"strategy_opts": {"fps": 5, "max_width": 768}}, {}, {})
    assert a == b, f"order changed cache key: {a!r} != {b!r}"


def test_naive_repr_would_have_differed():
    """Sanity guard: the underlying dicts genuinely render differently
    via ``str``/``repr``, so the helper's normalisation is doing real work
    (not relying on Python happening to hash dicts identically)."""
    d1 = {"max_width": 768, "fps": 5}
    d2 = {"fps": 5, "max_width": 768}
    assert str(d1) != str(d2)


def test_distinct_overrides_still_diverge():
    """Different values must still produce different cache fragments."""
    a = _override_extra({"strategy_opts": {"max_width": 768}}, {}, {})
    b = _override_extra({"strategy_opts": {"max_width": 1024}}, {}, {})
    assert a != b


def test_top_level_and_nested_keys_both_canonical():
    """Top-level keys are sorted; nested dict values are sorted too."""
    a = _override_extra(
        {"strategy": "tile", "strategy_opts": {"b": 2, "a": 1}},
        {"max_tokens": "512", "temperature": "0.5"},
        {},
    )
    b = _override_extra(
        {"strategy_opts": {"a": 1, "b": 2}, "strategy": "tile"},
        {"temperature": "0.5", "max_tokens": "512"},
        {},
    )
    assert a == b
