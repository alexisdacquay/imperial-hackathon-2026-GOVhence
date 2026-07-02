"""Tests for the Judge.

Deterministic tests inject a FAKE llm (no network) to verify parsing, the write/candidate
guardrail, per-component routing, and graceful fallback. One live smoke test calls the real
JUDGE model (glm-5.2), skipped if no JUDGE key is configured.
"""
import pytest

import judge
import llm


def _fake(reply):
    def _chat(system, user, **kw):
        return reply
    return _chat


def test_read_and_write_from_llm():
    d = judge.judge("The London office moved to Friar Street", ["london", "office"],
                    chat=_fake('{"read": true, "write": true, "candidate": "The London office moved to Friar Street."}'))
    assert d.read is True and d.write is True
    assert "Friar Street" in d.candidate


def test_query_reads_but_does_not_write():
    d = judge.judge("where is the best sandwich?", ["food"],
                    chat=_fake('{"read": true, "write": false, "candidate": null}'))
    assert d.read is True and d.write is False and d.candidate is None


def test_candidate_dropped_if_write_false():
    # even if the model returns a candidate, ignore it unless write is true
    d = judge.judge("x", [], chat=_fake('{"read": false, "write": false, "candidate": "junk"}'))
    assert d.write is False and d.candidate is None


def test_routes_to_JUDGE_component():
    seen = {}

    def rec(system, user, **kw):
        seen["component"] = kw.get("component")
        return '{"read": true, "write": false, "candidate": null}'

    judge.judge("anything?", ["x"], chat=rec)
    assert seen["component"] == "JUDGE"       # the Judge uses its own model, not the generic one


def test_bad_json_falls_back_to_rules():
    d = judge.judge("The canteen serves free noodles on Fridays", ["food"], chat=_fake("not json"))
    assert d.write is True                     # rule-based fallback: substantive statement -> write


def test_llm_error_falls_back_to_rules():
    def boom(system, user, **kw):
        raise llm.LLMError("model offline")
    d = judge.judge("Hi", [], chat=boom)
    assert d.read is False and d.write is False  # greeting -> nothing


# --- live smoke: the real JUDGE model (glm-5.2) ----------------------------------
def _judge_configured():
    key = llm._config("JUDGE")[2]
    return bool(key) and not key.startswith("your-")


@pytest.mark.skipif(not _judge_configured(), reason="no JUDGE LLM key configured (.env)")
def test_live_judge_smoke():
    d = judge.judge("The London office has moved to Friar Street.", ["london", "office"])
    assert isinstance(d.read, bool) and isinstance(d.write, bool)   # real JSON -> Decision
