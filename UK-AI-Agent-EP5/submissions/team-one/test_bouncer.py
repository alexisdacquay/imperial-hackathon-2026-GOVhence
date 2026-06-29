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

import pytest

import audit
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
