"""Tests for llm.parse_json — it must tolerate the Markdown code fences some open-weight
models wrap around JSON output (the #4 fix), while still rejecting genuine non-JSON."""
import pytest

import llm


def test_plain_json():
    assert llm.parse_json('{"read": true, "write": false}') == {"read": True, "write": False}


def test_json_fence_multiline():
    assert llm.parse_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_bare_fence():
    assert llm.parse_json('```\n{"a": 1}\n```') == {"a": 1}


def test_fence_inline():
    # exactly the shape glm-5.2 returned in the live Judge test
    assert llm.parse_json('```json {"read": true, "write": false, "candidate": null} ```') == {
        "read": True, "write": False, "candidate": None}


def test_surrounding_whitespace():
    assert llm.parse_json('  {"a": 1}  ') == {"a": 1}


def test_genuine_non_json_still_raises():
    with pytest.raises(ValueError):
        llm.parse_json("not json at all")
