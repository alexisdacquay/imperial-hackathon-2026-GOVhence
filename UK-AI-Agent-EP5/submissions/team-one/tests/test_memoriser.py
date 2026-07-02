"""Tests for the Memoriser — the write-time labeller.

Deterministic tests inject a FAKE llm (no network) to verify the two guardrails:
FAIL-CLOSED writes (offline/junk/invalid -> refused, store untouched) and the
WRITER CAP (labels must sit within the writer's own clearances). One live smoke
test calls the real model, skipped if no key is configured.
"""
import json

import pytest

import llm
import memoriser

# self-contained profile store: ben holds {shared, logistics}; max holds all three.
USERS = {
    "roles": {
        "driver":  {"department": "logistics",  "clearances": ["shared", "logistics"]},
        "auditor": {"department": "compliance", "clearances": ["shared", "financials", "legal"]},
    },
    "users": {"ben": "driver", "max": "auditor"},
}


@pytest.fixture
def users_path(tmp_path):
    p = tmp_path / "users.json"
    p.write_text(json.dumps(USERS), encoding="utf-8")
    return p


def _fake(reply):
    def _chat(system, user, **kw):
        return reply
    return _chat


# --- happy path -------------------------------------------------------------------

def test_stores_with_llm_labels(users_path):
    mem = []
    ack = memoriser.memorise("Depot closes early on Fridays", ["depot", "schedule", "depot"],
                             mem, "ben", users_path=users_path,
                             chat=_fake('{"labels": ["logistics"]}'))
    assert ack.startswith("stored")
    assert len(mem) == 1
    assert mem[0]["labels"] == ["logistics"]
    assert mem[0]["topics"] == ["depot", "schedule"]          # deduped, order kept
    assert mem[0]["text"] == "Depot closes early on Fridays"  # verbatim, no expansion


def test_multiple_labels_all_kept_most_restrictive(users_path):
    # max holds financials+legal; both labels stick -> readers must hold BOTH.
    mem = []
    memoriser.memorise("Acme settled for 250k", ["settlement"], mem, "max",
                       users_path=users_path,
                       chat=_fake('{"labels": ["financials", "legal"]}'))
    assert mem[0]["labels"] == ["financials", "legal"]


# --- the WRITER CAP (labels only) --------------------------------------------------

def test_label_above_writer_clearance_is_refused(users_path):
    # ben (driver) writes something the labeller calls financials -> refused.
    mem = []
    ack = memoriser.memorise("Q3 revenue was 4.2M", ["revenue"], mem, "ben",
                             users_path=users_path,
                             chat=_fake('{"labels": ["financials"]}'))
    assert ack.startswith("NOT stored") and "above the writer's clearance" in ack
    assert mem == []                                          # store untouched


def test_unknown_writer_cannot_store_anything(users_path):
    mem = []
    ack = memoriser.memorise("anything", ["x"], mem, "mallory",
                             users_path=users_path, chat=_fake('{"labels": ["shared"]}'))
    assert ack.startswith("NOT stored") and mem == []         # no clearances -> no cap passes


# --- vocabulary + validity (strict, fail-closed) -----------------------------------

def test_label_outside_vocabulary_is_refused(users_path):
    mem = []
    ack = memoriser.memorise("m", ["x"], mem, "ben", users_path=users_path,
                             chat=_fake('{"labels": ["topsecret"]}'))
    assert ack.startswith("NOT stored") and "vocabulary" in ack and mem == []


def test_label_case_mismatch_is_refused(users_path):
    # strict exact strings: 'Logistics' is NOT the label 'logistics'.
    mem = []
    ack = memoriser.memorise("m", ["x"], mem, "ben", users_path=users_path,
                             chat=_fake('{"labels": ["Logistics"]}'))
    assert ack.startswith("NOT stored") and mem == []


def test_empty_labels_refused(users_path):
    mem = []
    ack = memoriser.memorise("m", ["x"], mem, "ben", users_path=users_path,
                             chat=_fake('{"labels": []}'))
    assert ack.startswith("NOT stored") and mem == []


def test_non_list_labels_refused(users_path):
    mem = []
    ack = memoriser.memorise("m", ["x"], mem, "ben", users_path=users_path,
                             chat=_fake('{"labels": "shared"}'))
    assert ack.startswith("NOT stored") and mem == []


# --- fail-closed writes: offline / junk never store --------------------------------

def test_junk_json_refused_not_crash(users_path):
    mem = []
    ack = memoriser.memorise("m", ["x"], mem, "ben", users_path=users_path,
                             chat=_fake("not json at all"))
    assert ack.startswith("NOT stored") and "fail-closed" in ack and mem == []


def test_llm_offline_refused_not_crash(users_path):
    def boom(system, user, **kw):
        raise llm.LLMError("model offline")
    mem = []
    ack = memoriser.memorise("m", ["x"], mem, "ben", users_path=users_path, chat=boom)
    assert ack.startswith("NOT stored") and mem == []


# --- prompt & routing --------------------------------------------------------------

def test_routes_to_MEMORISER_component_and_prompt_content(users_path):
    seen = {}

    def rec(system, user, **kw):
        seen["component"] = kw.get("component")
        seen["user"] = user
        return '{"labels": ["shared"]}'

    memoriser.memorise("bread news", ["bread"], [], "ben", users_path=users_path, chat=rec)
    assert seen["component"] == "MEMORISER"
    assert "financials" in seen["user"]           # FULL vocabulary offered (cap is in code)
    assert "role=driver" in seen["user"]          # role+dept context sent...
    assert "ben" not in seen["user"]              # ...but NEVER the writer's name


# --- live smoke: the real model (skipped without a key) ----------------------------

def _memoriser_configured():
    key = llm._config("MEMORISER")[2]
    return bool(key) and not key.startswith("your-")


@pytest.mark.skipif(not _memoriser_configured(), reason="no MEMORISER LLM key configured (.env)")
def test_live_memoriser_smoke(users_path):
    mem = []
    ack = memoriser.memorise("The Watford depot accepts deliveries until 2pm on Fridays.",
                             ["delivery", "depot"], mem, "ben", users_path=users_path)
    # Whatever the model says, the deterministic guardrails hold:
    if mem:
        assert set(mem[0]["labels"]) <= {"shared", "logistics"}   # within ben's clearances
    else:
        assert ack.startswith("NOT stored")
