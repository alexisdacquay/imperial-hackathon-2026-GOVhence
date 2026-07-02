"""Tests for the event log (the GUI's activity feed) and its pipeline hooks.

Key properties under test:
  - append-only JSONL with ts / monotonic seq / run stamps (audit-traceable-lite);
  - BEST-EFFORT: a broken events path never raises, never changes behaviour;
  - the Bouncer records credential checks and per-memory read decisions with ms;
  - a Bouncer failure is recorded AND still raised (recording never softens it).

The conftest autouse fixture points eventlog._PATH at a temp file for every test.
"""
import json

import pytest

import bouncer
import eventlog

USERS = {
    "roles": {"driver": {"department": "logistics", "clearances": ["shared", "logistics"]}},
    "users": {"ben": "driver"},
}

MEMS = [
    {"labels": ["shared"],     "topics": ["bread"], "text": "public tip"},
    {"labels": ["financials"], "topics": ["bread"], "text": "secret numbers"},
]


@pytest.fixture
def users_path(tmp_path):
    p = tmp_path / "users.json"
    p.write_text(json.dumps(USERS), encoding="utf-8")
    return p


def _events():
    lines = eventlog._PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(ln) for ln in lines]


# --- the log itself ---------------------------------------------------------------

def test_emit_appends_jsonl_with_ts_seq_run():
    eventlog.start_run("ben", message="hello")
    eventlog.emit("call", src="GOVhence", dst="Judge")
    eventlog.end_run(status="ok", ms_total=12.5)
    evs = _events()
    assert [e["ev"] for e in evs] == ["run.start", "call", "run.end"]
    assert [e["seq"] for e in evs] == [0, 1, 2]                    # monotonic
    assert all(e["ts"].endswith("+00:00") for e in evs)            # UTC
    assert evs[0]["run"] == evs[1]["run"] is not None              # same run stamp
    eventlog.emit("orphan")
    assert _events()[-1]["run"] is None                            # run cleared by end_run


def test_seq_continues_from_existing_file():
    eventlog._PATH.parent.mkdir(parents=True, exist_ok=True)
    eventlog._PATH.write_text('{"seq": 0}\n{"seq": 1}\n', encoding="utf-8")
    eventlog.emit("x")
    assert _events()[-1]["seq"] == 2


def test_emit_is_best_effort_never_raises(monkeypatch, tmp_path):
    # unwritable path (a directory where the file should be) -> emit swallows it
    bad = tmp_path / "events.jsonl"
    bad.mkdir()
    monkeypatch.setattr(eventlog, "_PATH", bad)
    eventlog.emit("x", detail="anything")                          # must not raise


# --- Bouncer hooks: credentials + read decisions with ms ---------------------------

def test_credential_check_recorded_with_ms(users_path):
    bouncer.clearances_for("ben", users_path=users_path)
    ev = [e for e in _events() if e["ev"] == "credentials"][-1]
    assert ev["user"] == "ben" and ev["status"] == "ok" and ev["known"] is True
    assert ev["clearances"] == ["logistics", "shared"]
    assert isinstance(ev["ms"], float) and ev["ms"] >= 0


def test_unknown_user_credential_check_recorded(users_path):
    bouncer.clearances_for("mallory", users_path=users_path)
    ev = [e for e in _events() if e["ev"] == "credentials"][-1]
    assert ev["known"] is False and ev["clearances"] == []


def test_read_records_allow_and_deny_decisions(users_path):
    lane = bouncer.retrieve(["bread"], "ben", MEMS, users_path=users_path)
    assert [m["text"] for m in lane] == ["public tip"]             # behaviour unchanged
    ev = [e for e in _events() if e["ev"] == "bouncer.read"][-1]
    assert ev["status"] == "success" and ev["user"] == "ben"
    assert ev["relevant"] == 2 and ev["permitted"] == 1 and ev["withheld"] == 1
    assert isinstance(ev["ms"], float)
    by_text = {d["text"]: d for d in ev["decisions"]}
    assert by_text["public tip"]["decision"] == "ALLOW"
    denied = by_text["secret numbers"]
    assert denied["decision"] == "DENY" and "financials" in denied["reason"]


def test_read_failure_recorded_and_still_raised(users_path):
    bad_mem = [{"labels": "not-a-list", "topics": ["bread"], "text": "malformed"}]
    with pytest.raises(bouncer.ConfigError):
        bouncer.retrieve(["bread"], "ben", bad_mem, users_path=users_path)
    ev = [e for e in _events() if e["ev"] == "bouncer.read"][-1]
    assert ev["status"] == "failure" and "labels" in ev["error"]


def test_logging_failure_never_blocks_the_gate(users_path, monkeypatch, tmp_path):
    # even with a broken events path, retrieval works and decides identically
    bad = tmp_path / "evdir"
    bad.mkdir()
    monkeypatch.setattr(eventlog, "_PATH", bad)
    lane = bouncer.retrieve(["bread"], "ben", MEMS, users_path=users_path)
    assert [m["text"] for m in lane] == ["public tip"]
