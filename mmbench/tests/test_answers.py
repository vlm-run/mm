"""Tests for recovering the answer object from assistant output."""

from __future__ import annotations

from mmbench.answers import parse_answer


def test_parses_fenced_json_block():
    text = 'Here is my answer.\n```json\n{"duration_s": 2.0}\n```\n'
    assert parse_answer(text) == {"duration_s": 2.0}


def test_prefers_last_object_when_multiple():
    text = '{"draft": 1}\nthinking...\n{"file": "docs/contract.pdf"}'
    assert parse_answer(text) == {"file": "docs/contract.pdf"}


def test_ignores_braces_inside_strings():
    text = 'noise {"note": "a } brace in a string", "ok": true}'
    assert parse_answer(text) == {"note": "a } brace in a string", "ok": True}


def test_returns_none_without_json():
    assert parse_answer("no json here") is None
