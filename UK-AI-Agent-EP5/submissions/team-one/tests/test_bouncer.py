"""Tests for the REAL Bouncer: whitelist labels/clearances access over CocoShaMem.

Vocabulary (definitive): topics = content, ANY-match, relevance only, from the LLM;
labels = security labels a memory CARRIES; clearances = labels a user HOLDS.
Rule: returned <=> labels non-empty AND labels ⊆ clearances AND topics ∩ query ≠ ∅.

Two layers of tests:
  1. self-contained — tiny users.json + memory written to a TEMP dir (tmp_path),
     so every rule is provable independent of the demo seed data;
  2. real-data smoke — retrieve() with defaults loads the actual data/users.json
     and data/cocoshamem.seed.json from disk (the real search path).

Run:  ../.venv/bin/python -m pytest tests/ -v   (from team-one/)
"""
import json

import pytest

import bouncer
from bouncer import ConfigError

# --- self-contained fixture data (independent of the demo seed) -------------------

USERS = {
    "roles": {
        "driver":  {"department": "logistics",  "clearances": ["shared", "logistics"]},
        "lawyer":  {"department": "legal",      "clearances": ["shared", "legal"]},
        "auditor": {"department": "compliance", "clearances": ["shared", "financials", "legal"]},
    },
    "users": {"ben": "driver", "lea": "lawyer", "max": "auditor"},
}

MEMS = [
    {"labels": ["shared"],              "topics": ["bread", "food"],  "text": "bakery tip"},
    {"labels": ["logistics"],           "topics": ["bread", "route"], "text": "bread van route"},
    {"labels": ["financials", "legal"], "topics": ["settlement"],     "text": "confidential settlement"},
    {"labels": [],                      "topics": ["bread"],          "text": "unlabelled orphan"},
]


@pytest.fixture
def users_path(tmp_path):
    p = tmp_path / "users.json"
    p.write_text(json.dumps(USERS), encoding="utf-8")
    return p


def _texts(lane):
    return {m["text"] for m in lane}


# --- relevance: topics ANY-match, and topics are NOT credentials ------------------

def test_topics_any_match_and_need_no_topic_in_profile(users_path):
    # ben's clearances are {shared, logistics} — 'bread' is NOT among them, and it
    # doesn't need to be: topics are relevance only. ANY overlap matches.
    lane = bouncer.retrieve(["bread"], "ben", MEMS, users_path=users_path)
    assert _texts(lane) == {"bakery tip", "bread van route"}


def test_no_topic_overlap_means_no_result(users_path):
    lane = bouncer.retrieve(["weather"], "ben", MEMS, users_path=users_path)
    assert lane == []


# --- permission: ALL labels must be held (labels ⊆ clearances) --------------------

def test_all_labels_required_missing_one_denies(users_path):
    # lea holds {shared, legal} but the settlement carries {financials, legal} —
    # one label short -> denied, even though the topic matches.
    lane = bouncer.retrieve(["settlement"], "lea", MEMS, users_path=users_path)
    assert lane == []


def test_all_labels_held_grants(users_path):
    # max holds {shared, financials, legal} — covers BOTH labels -> permitted.
    lane = bouncer.retrieve(["settlement"], "max", MEMS, users_path=users_path)
    assert _texts(lane) == {"confidential settlement"}


def test_empty_labels_fail_closed_for_everyone(users_path):
    # A memory with NO labels is visible to NOBODY (empty set would otherwise pass
    # every subset check — that would be fail-open).
    for user in USERS["users"]:
        lane = bouncer.retrieve(["bread"], user, MEMS, users_path=users_path)
        assert "unlabelled orphan" not in _texts(lane)


def test_unknown_user_fails_closed(users_path):
    assert bouncer.retrieve(["bread"], "mallory", MEMS, users_path=users_path) == []


def test_topics_cannot_smuggle_access(users_path):
    # Passing label names as TOPICS must not grant anything: ben queries with
    # 'legal'/'financials'/'settlement' as topics and still sees nothing new.
    lane = bouncer.retrieve(["legal", "financials", "settlement"], "ben", MEMS,
                            users_path=users_path)
    assert lane == []


def test_matching_is_strict_and_case_sensitive():
    # The pure chokepoint: 'Logistics' != 'logistics'; empty labels never visible.
    assert bouncer.visible({"logistics"}, {"logistics"}) is True
    assert bouncer.visible({"Logistics"}, {"logistics"}) is False
    assert bouncer.visible(set(), {"logistics"}) is False


# --- totality: malformed data raises ConfigError, never a bare TypeError ----------

def test_malformed_clearances_raise_configerror(tmp_path):
    bad = {"roles": {"driver": {"clearances": ["shared", 42]}}, "users": {"ben": "driver"}}
    p = tmp_path / "users.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ConfigError):
        bouncer.clearances_for("ben", users_path=p)


def test_role_without_clearances_raises_configerror(tmp_path):
    bad = {"roles": {"driver": {"department": "logistics"}}, "users": {"ben": "driver"}}
    p = tmp_path / "users.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ConfigError):
        bouncer.clearances_for("ben", users_path=p)


def test_malformed_memory_labels_raise_configerror(users_path):
    bad_mem = [{"labels": "logistics", "topics": ["bread"], "text": "labels not a list"}]
    with pytest.raises(ConfigError):
        bouncer.retrieve(["bread"], "ben", bad_mem, users_path=users_path)


def test_memory_missing_labels_key_raises_configerror(users_path):
    bad_mem = [{"topics": ["bread"], "text": "no labels key at all"}]
    with pytest.raises(ConfigError):
        bouncer.retrieve(["bread"], "ben", bad_mem, users_path=users_path)


def test_query_topics_as_bare_string_rejected(users_path):
    # A bare string would silently split into characters — reject it loudly.
    with pytest.raises(ConfigError):
        bouncer.retrieve("bread", "ben", MEMS, users_path=users_path)


def test_broken_users_file_raises_configerror_not_raw_errors(tmp_path):
    # Missing file, invalid JSON, and a non-object top level must all surface as
    # ConfigError — never a bare FileNotFoundError/JSONDecodeError/AttributeError.
    with pytest.raises(ConfigError):
        bouncer.clearances_for("ben", users_path=tmp_path / "nope.json")
    bad = tmp_path / "users.json"
    bad.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        bouncer.clearances_for("ben", users_path=bad)
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ConfigError):
        bouncer.clearances_for("ben", users_path=bad)


def test_broken_memory_store_raises_configerror_not_raw_errors(tmp_path):
    with pytest.raises(ConfigError):
        bouncer.load_memories(memory_path=tmp_path / "nope.json")
    bad = tmp_path / "mem.json"
    bad.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        bouncer.load_memories(memory_path=bad)
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ConfigError):
        bouncer.load_memories(memory_path=bad)


# --- store resolution: runtime store (Memoriser-written) preferred, seed fallback --

def test_resolve_memory_path_prefers_runtime_store(tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text("{}", encoding="utf-8")
    store = tmp_path / "store.json"
    # no runtime store yet -> the seed
    assert bouncer.resolve_memory_path(store, seed) == seed
    # once the Memoriser has written one -> the store wins
    store.write_text("{}", encoding="utf-8")
    assert bouncer.resolve_memory_path(store, seed) == store


# --- real-data smoke: the actual data/users.json + the committed SEED ------------
# Pinned to the SEED file explicitly: a live run creates the runtime store
# (data/cocoshamem.json, git-ignored) and these assertions must not depend on
# whatever was taught at runtime.

SEED = bouncer._SEED_PATH


def test_real_store_driver_sees_shared():
    lane = bouncer.retrieve(["sandwich"], "bob", memory_path=SEED)   # real files
    assert _texts(lane) == {"The deli on Carter Lane does great sandwiches."}


def test_real_store_driver_denied_legal():
    assert bouncer.retrieve(["contract"], "bob", memory_path=SEED) == []


def test_real_store_exec_sees_financials():
    lane = bouncer.retrieve(["revenue"], "alice", memory_path=SEED)
    assert _texts(lane) == {"Q3 revenue for the London office was 4.2M."}


def test_real_store_exec_lacks_legal_by_omission():
    # No deny list anymore: alice simply does not HOLD the 'legal' clearance.
    assert bouncer.retrieve(["contract"], "alice", memory_path=SEED) == []


def test_real_store_counsel_sees_legal():
    lane = bouncer.retrieve(["contract"], "carol", memory_path=SEED)
    assert _texts(lane) == {"The Acme supplier contract has a late-delivery penalty clause."}


def test_real_store_dual_label_memory_hidden_from_all_seed_users():
    # {financials, legal} — no seed user holds both -> invisible to everyone.
    for user in ("bob", "alice", "carol"):
        assert bouncer.retrieve(["settlement", "acme"], user, memory_path=SEED) == []
