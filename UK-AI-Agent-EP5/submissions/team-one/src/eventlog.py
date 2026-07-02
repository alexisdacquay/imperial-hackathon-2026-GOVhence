"""Event log — the pipeline's activity feed, written for the GUI to graph.

One JSON object per line (JSONL), appended to data/events.jsonl (git-ignored
runtime artifact). Every record carries a UTC timestamp (ms precision), a
monotonic per-file sequence number, and the run id it belongs to — enough to
trace and order everything (audit-traceable-lite). The full tamper-evident
regulatory audit log (hash chain, fail-closed) is a SEPARATE deliverable
(PRD-security S1); this feed is for visibility, so it is BEST-EFFORT BY
DESIGN: a logging problem must never change what the pipeline does — emit()
swallows its own failures and the caller never knows.

What gets recorded (see govhence.py + bouncer.py):
  run.start / run.end        one user message end-to-end (with total ms)
  call / return              each GOVhence <-> component hop (returns carry ms;
                             the Memoriser's return carries status stored/refused)
  credentials                every user-profile clearance check by the Bouncer
  bouncer.read               every Bouncer read: topics, per-memory ALLOW/DENY
                             decisions, permitted/withheld counts, ms, failures

Durations are milliseconds with 3 decimals (e.g. 2036.412 = 2.036 s).
"""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

_PATH = Path(__file__).parent.parent / "data" / "events.jsonl"
_LOCK = threading.Lock()
_seq = None          # lazily initialised to the existing line count (continuity)
_run = None          # the current run id (single pipeline process; best-effort)


def _next_seq():
    """Next sequence number; on first use, continue from the existing file."""
    global _seq
    if _seq is None:
        try:
            with _PATH.open(encoding="utf-8") as f:
                _seq = sum(1 for _ in f)
        except OSError:
            _seq = 0
    n = _seq
    _seq += 1
    return n


def emit(ev, **fields):
    """Append one event record. BEST-EFFORT: never raises, never alters flow.

    Reserved keys written for every record: ts (UTC ISO-8601, ms), seq, run, ev.
    Everything else comes from **fields (use src/dst for hop endpoints, ms for
    durations in milliseconds).
    """
    try:
        with _LOCK:
            rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                   "seq": _next_seq(), "run": _run, "ev": ev}
            rec.update(fields)
            _PATH.parent.mkdir(parents=True, exist_ok=True)
            with _PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass                      # the feed must never break the pipeline


def start_run(user, **fields):
    """Open a run (one user message): sets the current run id that subsequent
    emits are stamped with, and writes the run.start record."""
    global _run
    _run = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%f')[:-3]}Z-{user}"
    emit("run.start", user=user, **fields)
    return _run


def end_run(**fields):
    """Write the run.end record and clear the current run id."""
    global _run
    emit("run.end", **fields)
    _run = None
