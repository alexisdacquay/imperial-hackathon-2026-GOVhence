"""
Tests for the GOVhence live pipeline (agents.py + pipeline.py).

Like the rest of the suite, any store/log goes to tmp_path -- the real audit log and the runtime
CocoShaMem store are never touched. The security invariant under test: RELEVANCE never bypasses
ACCESS (a memory that matches the query tags but sits in a forbidden category is still DENIED and
that DENY is logged).
"""
import json

import agents
import audit
import pipeline


def _seed_store(tmp_path):
    """Copy the committed seed into a tmp runtime store so writes never touch the repo."""
    store = tmp_path / "cocoshamem.json"
    store.write_text(pipeline.SEED_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return store


# --- agents: Classifier -----------------------------------------------------
def test_normalise_tag_unifies_case_and_space():
    assert agents.normalise_tag("Location") == "location"
    assert agents.normalise_tag("week end") == "week-end"


def test_canonical_tag_folds_synonyms():
    assert agents.canonical_tag("week-end") == "weekend"
    assert agents.canonical_tag("Sandwiches") == "food"


def test_classify_query_vs_statement():
    assert agents.classify("where can I find a sandwich?").kind == "query"
    assert agents.classify("We are in London, not Tokyo.").kind == "statement"


def test_classify_extracts_topic_tags():
    tags = set(agents.classify("where's a good sandwich in London?").content_tags)
    assert {"food", "london", "location"} <= tags


# --- agents: Judge ----------------------------------------------------------
def test_judge_query_is_not_a_write_candidate():
    m = "where can I find the best sandwich"
    assert agents.judge_write_candidate(m, agents.classify(m)).is_write_candidate is False


def test_judge_informative_statement_is_a_candidate():
    m = "No, no sandwiches in Tokyo, we are in London!"
    assert agents.judge_write_candidate(m, agents.classify(m)).is_write_candidate is True


# --- agents: Memoriser (quality gate + write-time access category) ----------
def test_memoriser_rejects_a_bare_query():
    m = "where can I find lunch?"
    assert agents.memorise(m, agents.classify(m)) is None


def test_memoriser_drafts_shared_memory_from_statement():
    m = "We are in London, not Tokyo."
    d = agents.memorise(m, agents.classify(m))
    assert d is not None and d.category == "shared" and "london" in d.tags


def test_memoriser_scopes_sensitive_content_tighter_than_shared():
    m = "Q3 revenue was 4.2M with a strong margin."
    d = agents.memorise(m, agents.classify(m))
    assert d is not None and d.category == "financials"


# --- pipeline: retrieval (the bouncer stays the sole gate) ------------------
def test_bob_retrieves_permitted_london_memories(tmp_path):
    store, log = _seed_store(tmp_path), tmp_path / "audit.csv"
    r = pipeline.handle("bob", "where can I get a sandwich in London?",
                        store_path=store, log_path=log, do_write=False)
    ids = {m.id for m in r.retrieved}
    assert "mem-lunch" in ids            # shared + food/london -> permitted
    assert "mem-financials" not in ids   # relevant (tagged london) but financials -> DENIED for a driver


def test_relevance_never_bypasses_access_deny_is_logged(tmp_path):
    store, log = _seed_store(tmp_path), tmp_path / "audit.csv"
    pipeline.handle("bob", "how is revenue in London?", store_path=store, log_path=log, do_write=False)
    decisions = {row["item_id"]: row["decision"] for row in audit.read_log(path=log)}
    assert decisions.get("mem-financials") == "DENY"   # the forbidden-but-relevant item was logged as DENY


def test_exec_sees_financials(tmp_path):
    store, log = _seed_store(tmp_path), tmp_path / "audit.csv"
    r = pipeline.handle("alice", "what was the London revenue?",
                        store_path=store, log_path=log, do_write=False)
    assert "mem-financials" in {m.id for m in r.retrieved}


def test_unknown_user_fails_closed(tmp_path):
    import pytest
    import memory
    with pytest.raises(memory.ConfigError):
        pipeline.handle("mallory", "hello", store_path=_seed_store(tmp_path),
                        log_path=tmp_path / "audit.csv", do_write=False)


# --- pipeline: the async write side-track -----------------------------------
def test_a_query_writes_nothing(tmp_path):
    store, log = _seed_store(tmp_path), tmp_path / "audit.csv"
    before = len(json.loads(store.read_text(encoding="utf-8"))["items"])
    r = pipeline.handle("bob", "where can I park at the London office?", store_path=store, log_path=log)
    assert r.memorised is None
    after = len(json.loads(store.read_text(encoding="utf-8"))["items"])
    assert after == before


def test_an_informative_statement_is_memorised(tmp_path):
    store, log = _seed_store(tmp_path), tmp_path / "audit.csv"
    before = len(json.loads(store.read_text(encoding="utf-8"))["items"])
    r = pipeline.handle("bob", "The London office now has a new coffee machine on floor two.",
                        store_path=store, log_path=log)
    assert r.memorised is not None and r.memorised_id
    after = len(json.loads(store.read_text(encoding="utf-8"))["items"])
    assert after == before + 1


# --- pipeline: relevance ranking + top-k cap --------------------------------
def test_retrieval_is_ranked_by_relevance(tmp_path):
    store, log = _seed_store(tmp_path), tmp_path / "audit.csv"
    r = pipeline.handle("bob", "lunch food in the London office",
                        store_path=store, log_path=log, do_write=False)
    ids = [m.id for m in r.retrieved]
    # mem-lunch overlaps food+location+london (3) -> ranks above london-only matches (2)
    assert ids and ids[0] == "mem-lunch"


def test_retrieval_caps_to_top_k(tmp_path):
    store, log = _seed_store(tmp_path), tmp_path / "audit.csv"
    r = pipeline.handle("bob", "London office", store_path=store, log_path=log,
                        do_write=False, top_k=2)
    assert len(r.retrieved) == 2
