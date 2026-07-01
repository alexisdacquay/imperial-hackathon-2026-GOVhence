"""
M2 — Permanent, re-runnable tests for the bouncer and the access-layer audit log.

These promote the throwaway stress scenarios into real tests so the behaviour
can never silently break. Run with:  pytest -v

Two things are under test:
  1. The deterministic bouncer (strict, fail-closed category matching).
  2. The audit log (100% coverage, append-only, correct fields).

IMPORTANT: audit tests write to a TEMPORARY file (pytest's tmp_path), never the
real regulatory audit_log.csv. The real compliance record is never touched here.
"""

import json
import threading
import time

import pytest

import audit
import cli
import memory
from bouncer import MemoryItem, check_item, filter_allowed, retrieve


# A small, shared set of items used across many tests.
def sample_items():
    return [
        MemoryItem("item1", "schedules",             "Truck 4: 30 pallets to Leeds, 06:00"),
        MemoryItem("item2", "opening-hours",         "Warehouse open Mon-Fri 05:00-22:00"),
        MemoryItem("item3", "goods-weights-volumes", "Inbound: 12 tonnes, 40 m3"),
        MemoryItem("item4", "financials",            "Q3 revenue 4.2M, margin 18%"),
        MemoryItem("item5", "legal",                 "Contract penalty clause"),
    ]


BOB = {"schedules", "opening-hours", "goods-weights-volumes"}


# --- The bouncer: core behaviour -----------------------------------------

def test_allowed_category_is_returned():
    item = MemoryItem("x", "schedules", "...")
    assert check_item(BOB, item).allowed is True


def test_denied_category_is_excluded():
    item = MemoryItem("x", "legal", "...")
    assert check_item(BOB, item).allowed is False


def test_bob_sees_exactly_his_three_items():
    returned = filter_allowed(BOB, sample_items())
    assert [i.id for i in returned] == ["item1", "item2", "item3"]


def test_empty_allowed_set_returns_nothing():
    # A user with no permissions must see NOTHING (fail-closed).
    assert filter_allowed(set(), sample_items()) == []


def test_no_items_returns_nothing_and_does_not_crash():
    assert filter_allowed(BOB, []) == []


def test_duplicates_and_order_are_sane():
    items = [
        MemoryItem("a", "schedules", "1"),
        MemoryItem("b", "legal", "2"),
        MemoryItem("c", "schedules", "3"),
    ]
    returned = filter_allowed(BOB, items)
    # Allowed items kept in original order; denied dropped.
    assert [i.id for i in returned] == ["a", "c"]


# --- The QUINTESSENTIAL RULE: strict exact match, never interpret --------
# Once a tag is written it is matched EXACTLY. Any mismatch fails CLOSED (DENY).

def test_wrong_case_is_denied():
    # 'Schedules' (capital S) is NOT 'schedules'. Strict match -> DENY.
    item = MemoryItem("x", "Schedules", "...")
    assert check_item(BOB, item).allowed is False


def test_trailing_space_is_denied():
    # 'schedules ' (trailing space) is NOT 'schedules'. Strict match -> DENY.
    item = MemoryItem("x", "schedules ", "...")
    assert check_item(BOB, item).allowed is False


def test_unknown_category_is_denied():
    # A category nobody granted -> DENY (fail-closed, not fail-open).
    item = MemoryItem("x", "top-secret-typo", "...")
    assert check_item(BOB, item).allowed is False


# --- Adversarial / robustness: the gate must be TOTAL and FAIL-CLOSED ----
# These come from a penetration/robustness sweep. Every malformed input must
# DENY (never crash, never accidentally ALLOW). A security gate is only as
# strong as its worst input.

def test_non_string_category_is_denied_not_crash():
    # None / int / list as a category must DENY, never raise.
    for bad in [None, 123, ["schedules"], {"x": 1}, b"schedules"]:
        d = check_item(BOB, MemoryItem("x", bad, "..."))
        assert d.allowed is False


def test_allowed_set_passed_as_string_does_not_leak():
    # THE critical fail-open: if allowed is a STRING, Python's `in` is a
    # SUBSTRING test. 'schedule' in 'schedules-and-more' would wrongly ALLOW.
    # The gate must refuse a non-set and DENY.
    d = check_item("schedules-and-more", MemoryItem("x", "schedule", "..."))
    assert d.allowed is False


def test_allowed_set_none_or_list_is_denied_not_crash():
    for bad in [None, ["schedules"], "schedules"]:
        d = check_item(bad, MemoryItem("x", "schedules", "..."))
        assert d.allowed is False


def test_denial_reason_explains_why_for_monitoring():
    # Every refusal must carry a usable reason (auditor/monitoring requirement).
    d = check_item(BOB, MemoryItem("x", None, "..."))
    assert d.reason and "not a string" in d.reason
    d2 = check_item("notaset", MemoryItem("x", "schedules", "..."))
    assert d2.reason and "not a set" in d2.reason


# --- The CEO denylist shape: everything except legal ---------------------

def test_ceo_sees_financials_but_not_legal():
    items = sample_items()
    all_categories = {i.category for i in items}
    ceo_allowed = all_categories - {"legal"}      # exec: everything EXCEPT legal
    returned_ids = [i.id for i in filter_allowed(ceo_allowed, items)]
    assert "item4" in returned_ids                # financials: allowed
    assert "item5" not in returned_ids            # legal: denied


# --- The audit log: written at the access layer, temp file only ----------

def test_audit_logs_every_decision(tmp_path):
    log = tmp_path / "test_audit.csv"
    retrieve("bob", BOB, sample_items(), log_path=log)
    rows = audit.read_log(path=log)
    # 100% coverage: one row per item evaluated (5 items -> 5 rows).
    assert len(rows) == 5


def test_audit_logs_denies_too(tmp_path):
    log = tmp_path / "test_audit.csv"
    retrieve("bob", BOB, sample_items(), log_path=log)
    rows = audit.read_log(path=log)
    decisions = {r["item_id"]: r["decision"] for r in rows}
    assert decisions["item1"] == "ALLOW"          # schedules
    assert decisions["item4"] == "DENY"           # financials (blocked, but LOGGED)
    assert decisions["item5"] == "DENY"           # legal (blocked, but LOGGED)


def test_audit_row_has_all_fields(tmp_path):
    log = tmp_path / "test_audit.csv"
    retrieve("bob", BOB, sample_items(), log_path=log)
    row = audit.read_log(path=log)[0]
    for field in ["timestamp", "user", "item_id", "category", "decision", "reason"]:
        assert field in row and row[field] != ""


def test_audit_is_append_only(tmp_path):
    # Two runs must ACCUMULATE, never overwrite (a regulatory record is never erased).
    log = tmp_path / "test_audit.csv"
    retrieve("bob", BOB, sample_items(), log_path=log)
    retrieve("ceo", BOB, sample_items(), log_path=log)
    assert len(audit.read_log(path=log)) == 10    # 5 + 5


def test_read_log_on_missing_file_returns_empty(tmp_path):
    assert audit.read_log(path=tmp_path / "does_not_exist.csv") == []


def test_default_log_path_is_the_permanent_regulatory_log():
    # Safety check: the default must be the real compliance log, so the app
    # (not a test) writes to the retained record by default.
    assert audit.LOG_PATH.name == "audit_log.csv"


# --- Round 2 hardening: audit-log integrity & fail-closed logging --------

def test_unicode_homoglyph_category_is_denied():
    # Lookalike characters (Cyrillic/fullwidth/zero-width) must NOT match the
    # latin category. Strict match defeats homoglyph bypass.
    for fake in ["ѕchedules", "schedules​", "ｓchedules"]:
        assert check_item({"schedules"}, MemoryItem("x", fake, "...")).allowed is False


def test_csv_formula_injection_is_defanged(tmp_path):
    # A value starting with = + - @ must be stored so a spreadsheet treats it as
    # text (prefixed with '), not an executable formula.
    log = tmp_path / "audit.csv"
    audit.log_decision("=cmd|calc!A1", "i", "c", "DENY", "r", path=log)
    row = audit.read_log(path=log)[0]
    assert not row["user"].startswith("=")     # neutralised
    assert row["user"] == "'=cmd|calc!A1"       # stored faithfully as text


def test_csv_embedded_newline_cannot_forge_rows(tmp_path):
    # An embedded newline in a field must not create a phantom audit row.
    log = tmp_path / "audit.csv"
    audit.log_decision("u", "i", "real\nFORGED,row,here,ALLOW,x", "DENY", "r", path=log)
    assert len(audit.read_log(path=log)) == 1   # exactly one row, no forgery


def test_logging_failure_fails_closed(tmp_path):
    # If the audit record cannot be written, access must be REFUSED (raise),
    # never served silently unlogged. We point at an unwritable path.
    bad = tmp_path / "missing-dir" / "audit.csv"
    items = [MemoryItem("item1", "schedules", "x")]
    with pytest.raises(audit.AuditError):
        retrieve("bob", {"schedules"}, items, log_path=bad)


# --- R2: the audit write must be TOTAL -- adversarial values must not crash it ----
# The audit log is a legal record: a bad field must never raise a raw exception that
# escapes AuditError and leaves an access unlogged / bricks the log. Fail closed OR
# store safely -- never crash.

def test_oversized_field_does_not_crash_the_log(tmp_path):
    # A field far bigger than csv's 131072-byte limit used to raise csv.Error and
    # brick the log. It must now be capped/stored safely, and the log stays verifiable.
    log = tmp_path / "audit.csv"
    huge = "A" * 200_000
    audit.log_decision("bob", "item1", "schedules", "ALLOW", huge, path=log)  # must not raise
    rows = audit.read_log(path=log)
    assert len(rows) == 1
    assert len(rows[0]["reason"]) <= audit._MAX_FIELD_CHARS   # bounded
    ok, _ = audit.verify(log)
    assert ok is True                                         # chain still intact


def test_unpaired_surrogate_does_not_crash_the_log(tmp_path):
    # An unpaired UTF-16 surrogate cannot encode to UTF-8; it used to crash both the
    # hash and the write. It must now be neutralised so the row writes and verifies,
    # and the hash chain stays consistent across a second appended row.
    log = tmp_path / "audit.csv"
    audit.log_decision("bob\ud800", "item1", "schedules", "ALLOW", "note\ud800here", path=log)
    audit.log_decision("bob", "item2", "schedules", "DENY", "second row", path=log)
    rows = audit.read_log(path=log)
    assert len(rows) == 2
    ok, _ = audit.verify(log)
    assert ok is True                                        # hashes consistent, no crash


# --- Tamper-evidence: the audit log must DETECT any alteration -----------

def _write_some(log):
    audit.log_decision("bob", "item1", "schedules", "ALLOW", "ok", path=log)
    audit.log_decision("bob", "item5", "legal", "DENY", "no", path=log)
    audit.log_decision("ceo", "item4", "financials", "ALLOW", "ok", path=log)


def test_intact_log_verifies(tmp_path):
    log = tmp_path / "audit.csv"
    _write_some(log)
    ok, msg = audit.verify(log)
    assert ok is True
    assert "intact" in msg


def test_rows_have_sequence_numbers(tmp_path):
    log = tmp_path / "audit.csv"
    _write_some(log)
    seqs = [r["seq"] for r in audit.read_log(log)]
    assert seqs == ["0", "1", "2"]   # consecutive, no gaps


def test_editing_a_row_is_detected(tmp_path):
    # Flip a DENY into an ALLOW directly in the file (the "cover my tracks" attack).
    log = tmp_path / "audit.csv"
    _write_some(log)
    text = log.read_text(encoding="utf-8").replace("item5,legal,DENY", "item5,legal,ALLOW")
    log.write_text(text, encoding="utf-8")
    ok, msg = audit.verify(log)
    assert ok is False
    assert "hash mismatch" in msg


def test_deleting_a_row_is_detected(tmp_path):
    # Remove a record entirely. The sequence gap (or broken chain) must be caught.
    log = tmp_path / "audit.csv"
    _write_some(log)
    lines = log.read_text(encoding="utf-8").splitlines()
    # Drop the middle data row (header is line 0, data rows follow).
    del lines[2]
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, msg = audit.verify(log)
    assert ok is False


def test_empty_log_verifies_trivially(tmp_path):
    ok, msg = audit.verify(tmp_path / "nothing.csv")
    assert ok is True


# --- M3: the users.json loader (memory.py) -------------------------------
# The loader turns "username" into the exact SET of allowed categories the
# bouncer checks. Like the bouncer, it is FAIL-CLOSED: anything malformed or
# unknown raises ConfigError instead of returning a permissive set.

def _write_config(tmp_path, config: dict):
    """Write a throwaway users.json so tests never depend on the real one."""
    path = tmp_path / "users.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


# A small, valid config reused by several tests: a driver and an exec-with-deny.
def sample_config():
    return {
        "categories": ["schedules", "opening-hours", "goods-weights-volumes",
                       "financials", "legal"],
        "roles": {
            "driver": {"allow": ["schedules", "opening-hours", "goods-weights-volumes"]},
            "exec": {"allow": ["*"], "deny": ["legal"]},
        },
        "users": {"bob": "driver", "alice": "exec"},
    }


def test_driver_role_resolves_to_its_three_categories():
    config = sample_config()
    allowed = memory.allowed_categories_for_user("bob", config)
    assert allowed == {"schedules", "opening-hours", "goods-weights-volumes"}


def test_exec_wildcard_expands_to_every_category():
    # "*" must become the real category names -- and "*" itself must NOT leak in
    # as a fake category.
    config = sample_config()
    config["roles"]["exec"]["deny"] = []          # no deny -> wildcard = all
    allowed = memory.allowed_categories_for_user("alice", config)
    assert allowed == set(config["categories"])
    assert "*" not in allowed


def test_exec_deny_beats_allow():
    # THE CEO rule: allow everything, deny legal. 'legal' must be absent even
    # though the wildcard allowed it.
    config = sample_config()
    allowed = memory.allowed_categories_for_user("alice", config)
    assert "financials" in allowed
    assert "legal" not in allowed                 # deny beats allow


def test_unknown_user_fails_closed():
    config = sample_config()
    with pytest.raises(memory.ConfigError):
        memory.allowed_categories_for_user("mallory", config)


def test_unknown_role_fails_closed():
    # A user mapped to a role that doesn't exist must raise, not return {}.
    config = sample_config()
    config["users"]["ghost"] = "nonexistent-role"
    with pytest.raises(memory.ConfigError):
        memory.allowed_categories_for_user("ghost", config)


def test_missing_section_fails_closed(tmp_path):
    path = _write_config(tmp_path, {"roles": {}, "users": {}})   # no "categories"
    with pytest.raises(memory.ConfigError):
        memory.load_config(path)


def test_bad_json_fails_closed(tmp_path):
    path = tmp_path / "users.json"
    path.write_text("{ this is not valid json ", encoding="utf-8")
    with pytest.raises(memory.ConfigError):
        memory.load_config(path)


def test_missing_file_fails_closed(tmp_path):
    with pytest.raises(memory.ConfigError):
        memory.load_config(tmp_path / "does_not_exist.json")


def test_loader_feeds_bouncer_end_to_end():
    # The whole point of M3: the loader's set drives the unchanged bouncer.
    # alice (exec) must get everything EXCEPT legal back from the gate.
    config = sample_config()
    allowed = memory.allowed_categories_for_user("alice", config)
    returned_ids = [i.id for i in filter_allowed(allowed, sample_items())]
    assert "item4" in returned_ids                # financials: allowed
    assert "item5" not in returned_ids            # legal: denied by deny-list


def test_loader_set_is_a_real_set_for_the_bouncer():
    # The bouncer REFUSES a non-set allowed-list (fail-closed). The loader must
    # therefore hand it a genuine set/frozenset, never a list/string.
    config = sample_config()
    allowed = memory.allowed_categories_for_user("bob", config)
    assert isinstance(allowed, (set, frozenset))


# --- M5: lineage-based revocation ----------------------------------------
# Revoking a SOURCE item must propagate to EVERY item derived from it,
# transitively. A revoked item is DENIED even if its category is allowed
# ("revoked beats allowed"). The graph closure is computed at load time; the
# gate just does set membership. Like everything else, this is FAIL-CLOSED.

# A 2-hop chain so transitivity is actually exercised:
#   itemC derived_from itemB,  itemB derived_from itemA,  revoke itemA
#   -> closure must be {itemA, itemB, itemC}
def sample_lineage():
    return {
        "derived_from": {"itemB": ["itemA"], "itemC": ["itemB"]},
        "revoked": ["itemA"],
    }


def test_direct_revocation_denies_even_allowed_category():
    # 'schedules' IS in BOB, but item1 is revoked -> DENY (revoked beats allowed).
    item = MemoryItem("item1", "schedules", "...")
    d = check_item(BOB, item, revoked_ids={"item1"})
    assert d.allowed is False
    assert "revoked" in d.reason


def test_default_empty_revoked_set_changes_nothing():
    # No revoked_ids passed -> behaves exactly as before (backward compatible).
    item = MemoryItem("item1", "schedules", "...")
    assert check_item(BOB, item).allowed is True


def test_revoked_beats_allowed_through_retrieve(tmp_path):
    # End-to-end: a revoked item is absent from the returned set, even though its
    # category is allowed.
    log = tmp_path / "audit.csv"
    returned = retrieve("bob", BOB, sample_items(), log_path=log, revoked_ids={"item1"})
    ids = [i.id for i in returned]
    assert "item1" not in ids                     # schedules, but revoked
    assert "item2" in ids                          # opening-hours, not revoked


def test_transitive_two_hop_closure():
    # Revoking the source itemA must pull in itemB (1 hop) and itemC (2 hops).
    closure = memory.revoked_closure(sample_lineage())
    assert closure == {"itemA", "itemB", "itemC"}
    # And the gate denies the 2-hop leaf using that closure.
    leaf = MemoryItem("itemC", "schedules", "...")
    assert check_item(BOB, leaf, revoked_ids=closure).allowed is False


def test_non_set_revoked_ids_fails_closed():
    # A non-set revoked list must DENY (never coerce to empty = "nothing revoked",
    # which would be fail-OPEN). Mirrors the allowed-set guard.
    item = MemoryItem("item1", "schedules", "...")
    for bad in [None, ["item1"], "item1"]:
        d = check_item(BOB, item, revoked_ids=bad)
        assert d.allowed is False
        assert "not a set" in d.reason


def test_revocation_is_id_scoped_not_category_scoped():
    # Two items share the 'schedules' category; revoking ONE by id must not
    # revoke the other. Proves revocation targets the item, not the category.
    items = [MemoryItem("a", "schedules", "1"), MemoryItem("b", "schedules", "2")]
    returned = filter_allowed(BOB, items, revoked_ids={"a"})
    assert [i.id for i in returned] == ["b"]


def test_closure_terminates_on_a_cycle():
    # A <-> B cycle is a data error; the closure must still terminate (and this
    # test completing at all is the proof it does not infinite-loop).
    cyclic = {"derived_from": {"itemA": ["itemB"], "itemB": ["itemA"]},
              "revoked": ["itemA"]}
    assert memory.revoked_closure(cyclic) == {"itemA", "itemB"}


def test_revocation_is_logged_with_a_reason(tmp_path):
    # 100% audit coverage: the revoked item's row is a DENY whose reason says why.
    log = tmp_path / "audit.csv"
    retrieve("bob", BOB, sample_items(), log_path=log, revoked_ids={"item1"})
    rows = {r["item_id"]: r for r in audit.read_log(path=log)}
    assert rows["item1"]["decision"] == "DENY"
    assert "revoked" in rows["item1"]["reason"]


def test_closure_is_a_real_set_for_the_gate():
    # The gate REFUSES a non-set revoked list. The loader must hand it a genuine
    # set/frozenset, never a list/string.
    assert isinstance(memory.revoked_closure(sample_lineage()), (set, frozenset))


# --- M5 loader: fail-closed parity with the M3 loader --------------------

def test_load_lineage_reads_a_valid_file(tmp_path):
    path = tmp_path / "lineage.json"
    path.write_text(json.dumps(sample_lineage()), encoding="utf-8")
    assert memory.revoked_ids(path) == {"itemA", "itemB", "itemC"}


def test_load_lineage_missing_file_fails_closed(tmp_path):
    with pytest.raises(memory.ConfigError):
        memory.load_lineage(tmp_path / "nope.json")


def test_load_lineage_bad_json_fails_closed(tmp_path):
    path = tmp_path / "lineage.json"
    path.write_text("{ not valid json ", encoding="utf-8")
    with pytest.raises(memory.ConfigError):
        memory.load_lineage(path)


def test_load_lineage_rejects_wrong_shapes(tmp_path):
    # Each malformed shape must raise (fail-closed), never return a permissive
    # (empty = nothing-revoked) graph.
    bad_configs = [
        "[]",                                          # top level not an object
        json.dumps({"derived_from": ["not", "a", "dict"]}),   # derived_from wrong type
        json.dumps({"revoked": "itemA"}),              # revoked not a list
        json.dumps({"derived_from": {"itemB": "itemA"}}),     # a value not a list
    ]
    for raw in bad_configs:
        path = tmp_path / "lineage.json"
        path.write_text(raw, encoding="utf-8")
        with pytest.raises(memory.ConfigError):
            memory.load_lineage(path)


# --- M6: the cli.py entrypoint (load_items + main wiring) ----------------
# M6 added ONE command-line entrypoint that wires the real loaders to the real
# gate, retiring the hardcoded user / allowed-set / revoked-set / items. These
# tests pin (a) the new load_items() store loader -- fail-closed exactly like the
# memory.py loaders -- and (b) main()'s end-to-end wiring and fail-closed exit
# codes. Like every other test here, any file/log goes to tmp_path; the real
# audit_log.csv is never touched (main() takes a log_path seam for exactly this).

def _write_store(tmp_path, data):
    """Write a throwaway memory_store.json so tests never depend on the real one."""
    path = tmp_path / "memory_store.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _allowed_ids_from_stdout(out: str) -> list[str]:
    """Pull the ids on ALLOW lines out of cli.main()'s printed output.

    A decision line is 'ALLOW <id> <reason>' or 'DENY  <id> <reason>'. Only an
    ALLOW decision line starts with the all-caps 'ALLOW ' token (the 'Allowed
    categories:' header does not, because match is case-sensitive)."""
    return sorted(line.split()[1] for line in out.splitlines() if line.startswith("ALLOW "))


# --- load_items: the happy path ------------------------------------------

def test_load_items_reads_the_real_demo_store():
    # The shipped memory_store.json loads into the 6 expected MemoryItems, with
    # categories passed through verbatim. Pins the demo store against silent drift.
    items = cli.load_items()                       # default real STORE_PATH (read-only)
    assert all(isinstance(i, MemoryItem) for i in items)
    assert [i.id for i in items] == ["item1", "item2", "item3", "item3-summary",
                                     "item4", "item5"]
    by_id = {i.id: i.category for i in items}
    assert by_id["item1"] == "schedules"
    assert by_id["item5"] == "legal"


def test_load_items_valid_store_builds_correct_memoryitems(tmp_path):
    store = {"items": [{"id": "a", "category": "schedules", "text": "hi"},
                       {"id": "b", "category": "legal", "text": "bye"}]}
    items = cli.load_items(_write_store(tmp_path, store))
    assert [(i.id, i.category, i.text) for i in items] == [("a", "schedules", "hi"),
                                                           ("b", "legal", "bye")]


def test_load_items_comment_key_is_ignored(tmp_path):
    # The leading '_comment' pseudo-comment (JSON has no real comments) sits beside
    # 'items' and must neither become an item nor cause a failure.
    store = {"_comment": "a note, not data",
             "items": [{"id": "item1", "category": "schedules", "text": "x"}]}
    items = cli.load_items(_write_store(tmp_path, store))
    assert [i.id for i in items] == ["item1"]


def test_load_items_empty_store_is_allowed_and_returns_empty(tmp_path):
    # A structurally valid but empty store is the SAFE direction (the user simply
    # sees nothing). It must NOT raise -- only structural problems are errors.
    assert cli.load_items(_write_store(tmp_path, {"items": []})) == []


# --- load_items: fail-closed, exactly like the memory.py loaders ----------

def test_load_items_missing_file_fails_closed(tmp_path):
    with pytest.raises(memory.ConfigError):
        cli.load_items(tmp_path / "does_not_exist.json")


def test_load_items_bad_json_fails_closed(tmp_path):
    path = tmp_path / "memory_store.json"
    path.write_text("{ not valid json ", encoding="utf-8")
    with pytest.raises(memory.ConfigError):
        cli.load_items(path)


def test_load_items_top_level_not_dict_fails_closed(tmp_path):
    path = tmp_path / "memory_store.json"
    path.write_text(json.dumps(["item1", "item2"]), encoding="utf-8")   # a list, not an object
    with pytest.raises(memory.ConfigError):
        cli.load_items(path)


def test_load_items_missing_or_nonlist_items_fails_closed(tmp_path):
    # No 'items' key, or 'items' is the wrong type -> fail closed (never an empty load).
    for bad in [{}, {"items": "notalist"}, {"items": {"id": "x"}}]:
        with pytest.raises(memory.ConfigError):
            cli.load_items(_write_store(tmp_path, bad))


def test_load_items_entry_not_a_dict_fails_closed(tmp_path):
    # A single bad entry locks the WHOLE store (fail-closed, no partial load) -- the
    # first entry here is valid to prove the good one is not returned regardless.
    store = {"items": [{"id": "ok", "category": "schedules", "text": "x"}, "i-am-a-string"]}
    with pytest.raises(memory.ConfigError):
        cli.load_items(_write_store(tmp_path, store))


def test_load_items_entry_missing_id_fails_closed(tmp_path):
    store = {"items": [{"category": "schedules", "text": "no id here"}]}
    with pytest.raises(memory.ConfigError):
        cli.load_items(_write_store(tmp_path, store))


def test_load_items_non_string_or_empty_id_fails_closed(tmp_path):
    # REGRESSION (fail-open leak): 'id' is the audit key AND the revocation key. A
    # non-string or empty id must FAIL CLOSED -- a numeric/None id would corrupt the
    # audit trail and silently escape id-based revocation. (Before the M6 hardening,
    # a non-string id was passed straight through and served on its category.)
    for bad_id in [123, None, "", ["item1"], {"x": 1}]:
        store = {"items": [{"id": bad_id, "category": "schedules", "text": "x"}]}
        with pytest.raises(memory.ConfigError):
            cli.load_items(_write_store(tmp_path, store))


# --- load_items: the critical security property (untagged => DENY) --------

def test_load_items_missing_category_is_denied_end_to_end(tmp_path):
    # An item with no 'category' loads (category becomes None -- the loader invents
    # nothing) but is DENIED by the gate, and the DENY is still logged. Untagged
    # content is never retrievable, even for a permitted user.
    store = {"items": [{"id": "untagged", "text": "secret with no tag"}]}
    items = cli.load_items(_write_store(tmp_path, store))
    assert items[0].category is None               # passed through, not invented
    log = tmp_path / "audit.csv"
    assert retrieve("bob", BOB, items, log_path=log) == []   # denied
    d = check_item(BOB, items[0])
    assert d.allowed is False and "not a string" in d.reason
    assert len(audit.read_log(path=log)) == 1      # the DENY was still logged (100% coverage)


def test_load_items_non_string_category_is_denied_end_to_end(tmp_path):
    # A present-but-non-string category (e.g. a list from a malformed file) is passed
    # through verbatim and DENIED by the gate -- read time never coerces/repairs a tag.
    store = {"items": [{"id": "badtag", "category": ["schedules"], "text": "x"}]}
    items = cli.load_items(_write_store(tmp_path, store))
    assert items[0].category == ["schedules"]      # unmodified
    log = tmp_path / "audit.csv"
    assert retrieve("bob", BOB, items, log_path=log) == []
    assert check_item(BOB, items[0]).allowed is False


# --- main(): end-to-end wiring against the real config --------------------

def test_cli_bob_exit_zero_and_logs_every_decision(tmp_path):
    # Happy path: a known user runs through loader+gate+audit, exits 0, and EVERY
    # store item's decision is written to the temp log (100% coverage), intact.
    log = tmp_path / "audit.csv"
    assert cli.main(["bob"], log_path=log) == 0
    assert len(audit.read_log(path=log)) == 6      # one row per store item
    ok, _ = audit.verify(log)
    assert ok is True


def test_cli_bob_returns_only_item2(tmp_path, capsys):
    # bob (driver): item1/item3/item3-summary revoked, item4/item5 outside his
    # categories -> only item2 (opening-hours) is allowed.
    assert cli.main(["bob"], log_path=tmp_path / "audit.csv") == 0
    assert _allowed_ids_from_stdout(capsys.readouterr().out) == ["item2"]


def test_cli_alice_sees_financials_not_legal_not_revoked(tmp_path, capsys):
    # alice (exec, allow * deny legal): sees financials, NOT legal (deny beats
    # allow), NOT the revoked items -> exactly {item2, item4}.
    log = tmp_path / "audit.csv"
    assert cli.main(["alice"], log_path=log) == 0
    assert _allowed_ids_from_stdout(capsys.readouterr().out) == ["item2", "item4"]
    decisions = {r["item_id"]: r["decision"] for r in audit.read_log(path=log)}
    assert decisions["item4"] == "ALLOW"           # financials: allowed
    assert decisions["item5"] == "DENY"            # legal: denied (deny beats allow)
    assert decisions["item1"] == "DENY"            # revoked source
    assert decisions["item3-summary"] == "DENY"    # revoked transitively (2 hops)


def test_cli_summary_reports_the_actual_log_path(tmp_path, capsys):
    # REGRESSION: the summary line must name the log it ACTUALLY wrote to, not the
    # hardcoded default -- a legal record must not misstate its own location.
    assert cli.main(["bob"], log_path=tmp_path / "my_temp_audit.csv") == 0
    out = capsys.readouterr().out
    assert "my_temp_audit.csv" in out
    assert "audit_log.csv" not in out


# --- main(): fail-closed exit codes ---------------------------------------

def test_cli_unknown_user_fails_closed_exit_2_no_log(tmp_path, capsys):
    # An unknown user is refused BEFORE any retrieval: exit 2, and NOTHING is logged
    # (no access was even attempted).
    log = tmp_path / "audit.csv"
    assert cli.main(["mallory"], log_path=log) == 2
    assert "ACCESS DENIED" in capsys.readouterr().err
    assert audit.read_log(path=log) == []          # nothing served or logged


def test_cli_unwritable_log_fails_closed_exit_3(tmp_path, capsys):
    # No log -> no access: if the audit record cannot be written, the run is refused
    # (exit 3), never served unlogged. Parent dir is absent so the open() fails.
    bad = tmp_path / "missing-dir" / "audit.csv"
    assert cli.main(["bob"], log_path=bad) == 3
    assert "ACCESS DENIED" in capsys.readouterr().err
    assert not bad.exists()


def test_cli_missing_user_argument_exits(tmp_path):
    # argparse contract: no positional 'user' -> SystemExit (usage error), never a
    # normal return or a run with a missing principal.
    with pytest.raises(SystemExit):
        cli.main([], log_path=tmp_path / "audit.csv")


# --- Loader totality: malformed-but-list config must still fail CLOSED ----
# Red-team finding (SEM-3): a list whose ELEMENTS are the wrong type slips past the
# "is it a list?" check and raises a raw, unhashable TypeError inside set(...), which
# is NOT a ConfigError -- so it would crash cli.main (which catches only ConfigError)
# instead of failing closed with exit 2. The loader must be TOTAL over malformed input.

def test_role_allow_with_unhashable_element_fails_closed():
    config = sample_config()
    config["roles"]["driver"]["allow"] = ["schedules", ["nested"]]   # a list inside the list
    with pytest.raises(memory.ConfigError):
        memory.allowed_categories_for_user("bob", config)


def test_role_deny_with_dict_element_fails_closed():
    config = sample_config()
    config["roles"]["exec"]["deny"] = [{"legal": True}]              # a dict inside the list
    with pytest.raises(memory.ConfigError):
        memory.allowed_categories_for_user("alice", config)


def test_non_string_category_entry_fails_closed(tmp_path):
    bad = {"categories": ["schedules", ["oops"]],                   # a list as a category entry
           "roles": {"d": {"allow": ["schedules"]}}, "users": {"u": "d"}}
    path = _write_config(tmp_path, bad)
    with pytest.raises(memory.ConfigError):
        memory.load_config(path)


# --- Checkpoint / running-tally: O(1) appends + TRUNCATION detection ------
# A bare hash chain cannot detect rows lopped off the END of the log (the remaining
# rows still chain cleanly). The checkpoint records (count, head-hash) after every
# write, is itself an append-only hash chain, and is mirrored to an off-host anchor.
# verify() cross-checks all three, so a trailing truncation is now CAUGHT.

def _write_n(log, n):
    for i in range(n):
        audit.log_decision(f"u{i}", f"it{i}", "schedules", "ALLOW", "ok", path=log)


def test_checkpoint_and_anchor_are_created_and_verify(tmp_path):
    log = tmp_path / "audit.csv"
    _write_n(log, 3)
    assert (tmp_path / "audit.csv.checkpoint").exists()
    assert (tmp_path / "audit.csv.anchor").exists()
    ok, msg = audit.verify(log)
    assert ok is True and "checkpoint-sealed" in msg


def test_trailing_truncation_is_detected_by_the_checkpoint(tmp_path):
    # THE headline: shave the most-recent row off the LOG only. The chain still
    # looks intact, but the checkpoint remembers there should be 5 rows -> CAUGHT.
    log = tmp_path / "audit.csv"
    _write_n(log, 5)
    assert audit.verify(log)[0] is True
    rows = log.read_text(encoding="utf-8").splitlines()
    log.write_text("\n".join(rows[:-1]) + "\n", encoding="utf-8")     # drop the last record
    ok, msg = audit.verify(log)
    assert ok is False and "truncated" in msg


def test_tampering_the_checkpoint_itself_is_detected(tmp_path):
    # The tamper-detector is itself tamper-evident: editing a tally row breaks the
    # checkpoint's own hash chain.
    log = tmp_path / "audit.csv"
    _write_n(log, 3)
    cp = tmp_path / "audit.csv.checkpoint"
    lines = cp.read_text(encoding="utf-8").splitlines()
    parts = lines[-1].split(",")
    parts[1] = str(int(parts[1]) + 99)                               # forge the count
    lines[-1] = ",".join(parts)
    cp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert audit.verify(log)[0] is False


def test_external_anchor_disagreement_is_flagged(tmp_path):
    # If the off-host anchor disagrees with the log+checkpoint, verify() flags it --
    # so hiding a truncation requires rewriting the anchor too (which lives off-host).
    log = tmp_path / "audit.csv"
    _write_n(log, 3)
    anchor = tmp_path / "audit.csv.anchor"
    a = anchor.read_text(encoding="utf-8").strip().split(",")
    a[1] = str(int(a[1]) + 1)                                        # anchor now disagrees
    anchor.write_text(",".join(a) + "\n", encoding="utf-8")
    ok, msg = audit.verify(log)
    assert ok is False and "anchor" in msg


# --- anchor rename robustness: transient Windows lock retried, real failure re-raised ---
# The intense stress found that under rapid writes on Windows the anchor's atomic os.replace can
# briefly lose to an AV/indexer (transient PermissionError). We retry it -- but a PERSISTENT failure
# must still propagate so the audit write fails closed (no leak, just a refused access).

def test_anchor_replace_retries_a_transient_permission_error(tmp_path, monkeypatch):
    src = tmp_path / "a.tmp"
    src.write_text("new", encoding="utf-8")
    dst = tmp_path / "a"
    calls = {"n": 0}
    real = audit.os.replace

    def flaky(s, d):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("target locked by scanner")
        return real(s, d)

    monkeypatch.setattr(audit.os, "replace", flaky)
    audit._replace_with_retry(src, dst, _sleep=lambda _s: None)
    assert calls["n"] == 3 and dst.read_text(encoding="utf-8") == "new"   # retried, then succeeded


def test_anchor_replace_reraises_after_giving_up(tmp_path, monkeypatch):
    src = tmp_path / "a.tmp"
    src.write_text("new", encoding="utf-8")

    def always_locked(s, d):
        raise PermissionError("always locked")

    monkeypatch.setattr(audit.os, "replace", always_locked)
    with pytest.raises(PermissionError):   # persistent failure still propagates (fail-closed)
        audit._replace_with_retry(src, tmp_path / "a", attempts=3, _sleep=lambda _s: None)


# --- R1: concurrent writes must not fork the chain -----------------------
# Two threads writing at once must never read the same seq+hash and append it
# twice (duplicate seq -> forked SHA-256 chain -> verify() falsely cries tamper).
# log_decision serialises its critical section with an in-process lock so the
# next writer always reads the previous writer's committed seq.

def test_concurrent_writes_keep_chain_intact(tmp_path, monkeypatch):
    # Force the read->append window to OVERLAP so the test has teeth: we widen the
    # gap between "read the last seq" and "append the row" with a tiny sleep (which
    # releases the GIL). WITHOUT the lock, every thread reads the same seq inside
    # that gap -> duplicate seqs / broken chain. WITH the lock, entry is serialised
    # so each thread reads a fresh seq -> a clean 0..N-1 chain.
    log = tmp_path / "race_audit.csv"
    # NOTE: couples to the private audit._last_link on purpose -- that IS the read half
    # of the race. If it is ever renamed/inlined, update this hook (the test would then
    # just stop widening the window, silently weakening -- so keep them in sync).
    real_last_link = audit._last_link

    def slow_last_link(path):
        result = real_last_link(path)
        time.sleep(0.01)          # yields the GIL, letting peers reach their own read
        return result

    monkeypatch.setattr(audit, "_last_link", slow_last_link)

    N = 16
    barrier = threading.Barrier(N)      # release all threads into the section together

    def writer(k):
        barrier.wait()
        audit.log_decision("u", f"item{k}", "shared", "ALLOW", "r", path=log)

    threads = [threading.Thread(target=writer, args=(k,)) for k in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    seqs = [int(row["seq"]) for row in audit.read_log(path=log)]
    assert len(seqs) == N                    # every write landed
    assert len(set(seqs)) == N               # no DUPLICATE seq -- the exact R1 symptom
    assert sorted(seqs) == list(range(N))    # a clean, gap-free 0..N-1 chain
    ok, msg = audit.verify(log)
    assert ok, msg                           # hash chain not forked
