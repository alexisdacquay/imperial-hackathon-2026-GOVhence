"""Tests for the Classifier.

Deterministic tests inject a FAKE llm (no network) to verify framing/parsing/hygiene/
fallback. One live smoke test actually calls the local open-weight model (skipped if
it isn't running) so you can see real classification.

Run:  ../.venv/bin/python -m pytest test_classifier.py -v   (from team-one/)
"""
import json

import pytest

import classifier
import llm

BOB = {"role": "driver", "department": "logistics"}


def _fake(reply):
    """A fake chat() that ignores the prompt and returns a canned reply string."""
    def _chat(system, user, **kw):
        return reply
    return _chat


def test_returns_content_tags_from_the_llm():
    c = classifier.classify("where is the best sandwich in London?", BOB,
                            chat=_fake('{"content_tags": ["food", "london"]}'))
    assert c.content_tags == ["food", "london"]


def test_user_tags_come_from_profile_never_the_llm():
    c = classifier.classify("hi", BOB, chat=_fake('{"content_tags": ["greeting"]}'))
    assert c.user_tags == ["driver", "logistics"]     # straight from the profile
    assert "driver" not in c.content_tags             # profile tags never leak from the LLM


def test_hygiene_lowercases_hyphenates_dedupes():
    c = classifier.classify("m", BOB,
                            chat=_fake('{"content_tags": ["London Food", "food", "OPENING HOURS", "food"]}'))
    assert c.content_tags == ["london-food", "food", "opening-hours"]


def test_reuses_known_tag_no_near_duplicate():
    c = classifier.classify("m", BOB, known_tags=["location", "food"],
                            chat=_fake('{"content_tags": ["Location", "food"]}'))
    assert c.content_tags == ["location", "food"]      # 'Location' folded onto known 'location'


def test_profile_role_dept_used_as_context_but_not_name():
    captured = {}

    def rec(system, user, **kw):
        captured["user"] = user
        return '{"content_tags": ["food"]}'

    prof = {"name": "Bob Smith", "role": "driver", "department": "logistics"}
    classifier.classify("bread", prof, chat=rec)
    assert "driver" in captured["user"] and "logistics" in captured["user"]   # context sent
    assert "Bob" not in captured["user"] and "Smith" not in captured["user"]  # name NEVER sent


def test_content_tags_strip_role_and_department():
    # Even if the LLM emits role/department as content tags, they're stripped (identity, not content).
    c = classifier.classify("m", BOB, chat=_fake('{"content_tags": ["driver", "logistics", "food"]}'))
    assert c.content_tags == ["food"]


def test_caps_tag_count():
    many = json.dumps({"content_tags": [f"t{i}" for i in range(20)]})
    c = classifier.classify("m", BOB, chat=_fake(many))
    assert len(c.content_tags) <= 6


def test_bad_json_falls_back_gracefully():
    c = classifier.classify("sandwich in London", BOB, chat=_fake("not json at all"))
    assert "london" in c.content_tags                  # rule-based fallback, no crash
    assert c.user_tags == ["driver", "logistics"]


def test_llm_error_falls_back_gracefully():
    def _boom(system, user, **kw):
        raise llm.LLMError("model offline")
    c = classifier.classify("sandwich in London", BOB, chat=_boom)
    assert "london" in c.content_tags
    assert c.user_tags == ["driver", "logistics"]


# --- live smoke test: actually call the configured open-weight model (mor.org) ---
def _model_configured():
    key = llm._config()[2]
    return bool(key) and key != "your-key-here"


@pytest.mark.skipif(not _model_configured(), reason="no LLM_API_KEY configured (.env)")
def test_live_classification_smoke():
    c = classifier.classify("where is the best sandwich in London?", BOB,
                            known_tags=["food", "london", "location"])
    assert isinstance(c.content_tags, list) and c.content_tags        # got some tags
    for t in c.content_tags:                                          # hygiene holds
        assert t == t.lower() and " " not in t
    assert c.user_tags == ["driver", "logistics"]                    # from profile
