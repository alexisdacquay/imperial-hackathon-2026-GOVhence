"""Tests for llm.parse_json — it must tolerate the Markdown code fences some open-weight
models wrap around JSON output (the #4 fix), while still rejecting genuine non-JSON —
and for llm.chat's retry, which absorbs the intermittent EMPTY completions some
open-weight endpoints (observed on mor.org glm-5.2) return for a valid request."""
import json

import pytest

import llm


# --- chat() retry on transient empty completions / errors ------------------------

class _FakeResp:
    """Minimal context-manager standing in for urlopen's response."""
    def __init__(self, content):
        self._body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._body


def _patch_urlopen(monkeypatch, replies):
    """Make urllib.request.urlopen yield each reply in turn: a str -> a response with
    that content; an Exception instance -> raised. Records the call count."""
    seq = iter(replies)
    calls = {"n": 0}

    def fake(req, timeout=None):
        calls["n"] += 1
        item = next(seq)
        if isinstance(item, Exception):
            raise item
        return _FakeResp(item)

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake)
    return calls


def test_chat_retries_past_empty_completions(monkeypatch):
    # two empty completions, then a real one -> chat returns the real one (3 calls).
    calls = _patch_urlopen(monkeypatch, ["", "   ", '{"read": true}'])
    monkeypatch.setenv("LLM_API_KEY", "x")
    out = llm.chat("sys", "usr", _sleep=lambda s: None)
    assert out == '{"read": true}' and calls["n"] == 3


def test_chat_retries_past_transient_error(monkeypatch):
    calls = _patch_urlopen(monkeypatch, [TimeoutError("slow"), '{"ok": 1}'])
    monkeypatch.setenv("LLM_API_KEY", "x")
    assert llm.chat("sys", "usr", _sleep=lambda s: None) == '{"ok": 1}' and calls["n"] == 2


def test_chat_raises_after_all_attempts_empty(monkeypatch):
    _patch_urlopen(monkeypatch, ["", "", "", ""])
    monkeypatch.setenv("LLM_API_KEY", "x")
    with pytest.raises(llm.LLMError):
        llm.chat("sys", "usr", attempts=4, _sleep=lambda s: None)


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
