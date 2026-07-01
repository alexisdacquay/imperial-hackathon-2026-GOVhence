"""Tests for the skeleton Bouncer's access property.

The point being proven: the Bouncer decides access by reading the user's allowed
categories DIRECTLY from users.json — given only the username. Content tags (which
GOVhence relays from the Classifier) drive relevance ONLY; they can never grant
access. So an LLM in the middle cannot smuggle access by passing tags.

Run:  ../.venv/bin/python -m pytest test_bouncer.py -v   (from team-one/)
"""
from pathlib import Path

import bouncer

USERS = Path(__file__).parent.parent / "data" / "users.json"

# a tiny memory set with access categories (independent of the seed file)
MEM = [
    {"category": "shared",     "tags": ["sandwich"], "text": "deli sandwiches"},
    {"category": "financials", "tags": ["revenue"],  "text": "Q3 revenue 4.2M"},
    {"category": "legal",      "tags": ["contract"], "text": "penalty clause"},
]


def _texts(lane):
    return {m["text"] for m in lane}


def test_driver_allowed_shared():
    # bob is a driver; 'shared' IS in the driver's allowed set in users.json.
    lane = bouncer.retrieve(["sandwich"], "bob", MEM, users_path=USERS)
    assert _texts(lane) == {"deli sandwiches"}


def test_driver_denied_legal_by_direct_read():
    # 'legal' is NOT in the driver's allowed set — the Bouncer denies it even though
    # the content tag matches, because it reads access straight from users.json.
    lane = bouncer.retrieve(["contract"], "bob", MEM, users_path=USERS)
    assert lane == []


def test_driver_denied_financials():
    lane = bouncer.retrieve(["revenue"], "bob", MEM, users_path=USERS)
    assert lane == []


def test_exec_allowed_financials():
    # alice is an exec (allow '*', deny 'legal') -> may see financials.
    lane = bouncer.retrieve(["revenue"], "alice", MEM, users_path=USERS)
    assert _texts(lane) == {"Q3 revenue 4.2M"}


def test_exec_still_denied_legal():
    # exec denies 'legal' explicitly -> even the exec cannot see it.
    lane = bouncer.retrieve(["contract"], "alice", MEM, users_path=USERS)
    assert lane == []


def test_access_cannot_be_smuggled_via_tags():
    # Passing 'legal'/'financials'/'exec' as CONTENT tags must NOT grant a driver
    # access. Access comes ONLY from the user's users.json entry, read by the Bouncer.
    lane = bouncer.retrieve(["contract", "revenue", "legal", "financials", "exec"],
                            "bob", MEM, users_path=USERS)
    assert all(m["category"] == "shared" for m in lane)  # never legal/financials


def test_unknown_user_fails_closed():
    lane = bouncer.retrieve(["sandwich"], "mallory", MEM, users_path=USERS)
    assert lane == []


def test_allowed_categories_read_from_users_json():
    # The allowed set is derived from users.json, not passed in.
    assert bouncer.allowed_categories("bob", USERS) == {
        "schedules", "opening-hours", "goods-weights-volumes", "shared"}
    assert "legal" not in bouncer.allowed_categories("alice", USERS)  # exec denies legal
