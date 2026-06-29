"""
Access-layer audit log (compliance + our own verification tool).

WHY THIS EXISTS
---------------
The track requires audit logs that meet *regulatory* standards -- not just
developer troubleshooting. The spec is specific:
  - "retrieval-layer access logging required by regulators and auditors"
  - access control (and therefore its logging) must live at the RETRIEVAL
    layer, NOT the application layer
  - 100% coverage: every retrieval decision logged
  - traceability: reconstruct "who saw what, when" for any item

So this logger is called from INSIDE the bouncer's decision point
(bouncer.check_item), not from some web/API layer above it. Every
ALLOW and every DENY is recorded -- auditors need blocked attempts too.

It is also our verification instrument: after running any step we can read
the log and prove each decision was correct, with its reason and timestamp.

FORMAT
------
Append-only CSV, one row per decision. CSV is human-readable, opens in any
spreadsheet, and is trivial to retain long-term (the spec mentions multi-year
retention). Append-only = we never rewrite history.

TAMPER-EVIDENCE (why the extra columns)
---------------------------------------
A plain append-only file proves nothing if someone with file access edits it.
So each row carries two extra fields that make tampering DETECTABLE:

  - seq:      a sequence number (0, 1, 2, ...). If a row is deleted, its number
              is missing -> a visible gap. You cannot quietly remove a record.
  - row_hash: a cryptographic fingerprint (SHA-256) of THIS row's contents
              PLUS the previous row's fingerprint. This links every row to the
              one before it, like a wax seal across pages. If anyone edits,
              deletes, inserts, or reorders ANY row, every later fingerprint
              stops matching -> verify() finds the exact break.

This is the standard, dependency-free way (NIST AU-9 integrity, SEC 17a-4
WORM-alternative) to turn an editable file into a tamper-evident record.
verify() recomputes the whole chain and reports the first broken row.
"""

import csv
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

# The log lives next to this file so it is easy to find during the demo.
LOG_PATH = Path(__file__).with_name("audit_log.csv")

# The columns, in order. seq + row_hash make the log tamper-evident.
FIELDS = ["seq", "timestamp", "user", "item_id", "category", "decision", "reason", "row_hash"]

# The first row chains from this fixed constant (the "genesis" link).
GENESIS_HASH = "0" * 64


def _utc_now() -> str:
    """Current time in UTC, ISO-8601 -- unambiguous across time zones for auditors."""
    return datetime.now(timezone.utc).isoformat()


def _defang(value) -> str:
    """Neutralise spreadsheet formula injection in audit values.

    The audit log is a regulatory record that auditors WILL open in Excel/Sheets.
    A cell starting with = + - @ (or tab/CR) is executed as a formula there, so an
    attacker-controlled field like '=cmd|calc!A1' could run code on the auditor's
    machine. We prefix such values with a single quote so the spreadsheet treats
    them as literal text. The stored value is still faithfully readable.
    """
    text = str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


class AuditError(Exception):
    """Raised when an access decision could NOT be written to the audit log.

    On a 100%-coverage compliance system, an unlogged access is a breach. So a
    logging failure must FAIL CLOSED: the access is refused, loudly, never served
    silently unlogged. Callers catch this to deny access with a clear reason.
    """


# The content fields that the hash protects (everything except the hash itself).
_HASHED_FIELDS = ["seq", "timestamp", "user", "item_id", "category", "decision", "reason"]


def _compute_row_hash(row: dict, prev_hash: str) -> str:
    """Fingerprint THIS row, chained to the previous row's fingerprint.

    We join the previous hash and this row's content fields with a separator that
    cannot appear in the values (a null byte), then SHA-256 it. Including prev_hash
    is what links the rows into a chain: change any earlier row and every later
    hash changes too.
    """
    parts = [prev_hash] + [str(row[f]) for f in _HASHED_FIELDS]
    blob = "\x00".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _last_link(path: Path) -> tuple[int, str]:
    """Return (next_seq, prev_hash) by reading the last row already in the log.

    For an empty/new log this is (0, GENESIS_HASH): the first record is seq 0 and
    chains from the genesis constant.
    """
    rows = read_log(path)
    if not rows:
        return 0, GENESIS_HASH
    last = rows[-1]
    return int(last["seq"]) + 1, last["row_hash"]


def log_decision(user: str, item_id: str, category: str, decision: str, reason: str,
                 path: Path = LOG_PATH) -> None:
    """Append exactly one decision row to the audit log.

    decision is the string "ALLOW" or "DENY". We write the header row once,
    when the file is first created, then only ever append.

    If the write fails for ANY reason (path missing, disk full, permissions),
    we raise AuditError so the caller can fail closed -- access must never be
    granted without a durable audit record.
    """
    try:
        new_file = not path.exists()
        # Find where we are in the chain: the next sequence number and the
        # previous row's hash to link to.
        seq, prev_hash = _last_link(path)

        # Build the row, then compute its hash from its content + the prev hash.
        row = {
            "seq": seq,
            "timestamp": _utc_now(),
            "user": _defang(user),
            "item_id": _defang(item_id),
            "category": _defang(category),
            "decision": _defang(decision),
            "reason": _defang(reason),
        }
        row["row_hash"] = _compute_row_hash(row, prev_hash)

        # newline="" is the documented way to use csv on all platforms (avoids blank rows on Windows).
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow(row)
            # Durable write: push this record to disk now so a crash cannot lose
            # the most recent decision (flush from Python, then fsync from the OS).
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        raise AuditError(f"could not write audit record for user={user!r} item={item_id!r}: {e}") from e


def read_log(path: Path = LOG_PATH) -> list[dict]:
    """Read the whole audit log back as a list of rows (for verification/traceability)."""
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def verify(path: Path = LOG_PATH) -> tuple[bool, str]:
    """Recompute the whole hash chain and confirm the log was not tampered with.

    Returns (True, "...") if every row's sequence and hash are intact, or
    (False, "<reason>") naming the first row where the chain breaks. This is the
    integrity-check an auditor runs: it detects any edit, deletion, insertion,
    or reordering of past records.
    """
    rows = read_log(path)
    if not rows:
        return True, "log is empty (nothing to verify)"

    prev_hash = GENESIS_HASH
    for i, row in enumerate(rows):
        # 1. Sequence must increase by exactly 1 each row (gaps = deleted rows).
        try:
            seq = int(row["seq"])
        except (KeyError, ValueError):
            return False, f"row {i}: missing or non-numeric seq"
        if seq != i:
            return False, f"row {i}: expected seq {i} but found {seq} (a record was deleted or inserted)"

        # 2. The stored hash must match a fresh recomputation (edits = mismatch).
        expected = _compute_row_hash(row, prev_hash)
        if row.get("row_hash") != expected:
            return False, f"row {i} (seq {seq}): hash mismatch -- this row or an earlier one was altered"

        prev_hash = row["row_hash"]

    return True, f"intact: {len(rows)} records form an unbroken chain"
