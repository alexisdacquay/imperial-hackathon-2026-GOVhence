"""
GOVhence MEM-Ø — access-layer audit log (compliance + our own verification tool).

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
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# The log lives next to this file so it is easy to find during the demo.
LOG_PATH = Path(__file__).with_name("audit_log.csv")

# The columns, in order. seq + row_hash make the log tamper-evident.
FIELDS = ["seq", "timestamp", "user", "item_id", "category", "decision", "reason", "row_hash"]

# The first row chains from this fixed constant (the "genesis" link).
GENESIS_HASH = "0" * 64


# --- Tamper-evident CHECKPOINT (the "running tally") ----------------------
# After every appended row we also append a tiny CHECKPOINT row recording
# (count, head-hash). This is exactly what production verifiable-log systems do
# (Certificate Transparency's "Signed Tree Head", AWS CloudTrail "digest files",
# Amazon QLDB's "ledger digest"). It does double duty:
#   1. SPEED -- the next append reads only this tally's TAIL, not the whole log,
#      so appending stays O(1) no matter how large the log grows.
#   2. TRUNCATION ALARM -- the tally remembers how many rows there SHOULD be, so
#      lopping rows off the END (which a bare hash chain provably cannot detect)
#      is caught by verify().
# The checkpoint is ITSELF an append-only SHA-256 chain -- the tamper-detector is
# itself tamper-evident (the CloudTrail trick). The latest tally is also mirrored
# to a separate ANCHOR file (meant to live OFF-HOST) -- a miniature of full
# external anchoring (roadmap #1).
GENESIS_CP_HASH = "0" * 64


def _checkpoint_path(path: Path) -> Path:
    return path.with_name(path.name + ".checkpoint")


def _anchor_path(path: Path) -> Path:
    return path.with_name(path.name + ".anchor")


def _tail_line(path: Path) -> "str | None":
    """Return the last non-empty line of a file, or None -- O(1) (reads only the tail).

    Safe because checkpoint/anchor rows are a fixed numeric+hex format with NO
    embedded newlines (unlike the CSV log, whose quoted fields can contain them, so
    the log itself can never be safely tail-read -- which is the whole reason this
    clean-format side file exists).
    """
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            end = f.tell()
            if end == 0:
                return None
            f.seek(max(0, end - 1024))      # a tally row is < 200 bytes; 1 KB always
            chunk = f.read()                # contains the final COMPLETE line
    except OSError:
        return None
    # strip() drops any trailing \r so a \r\n-written file reads back identically to
    # how splitlines() reads it elsewhere (Windows line-ending consistency).
    lines = [ln.strip() for ln in chunk.decode("utf-8").split("\n") if ln.strip()]
    return lines[-1] if lines else None


def _compute_cp_hash(prev_cp_hash: str, count: int, head_hash: str) -> str:
    """Chain this tally to the previous one (same idea as the row chain)."""
    blob = "\x00".join([prev_cp_hash, str(count), head_hash]).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _read_cp_head(cp_path: Path) -> "tuple[int, str, int, str] | None":
    """Parse the latest checkpoint row -> (count, head_hash, cp_seq, cp_hash), or None."""
    line = _tail_line(cp_path)
    if not line:
        return None
    parts = line.split(",")
    if len(parts) != 4:
        return None
    try:
        return int(parts[1]), parts[2], int(parts[0]), parts[3]
    except ValueError:
        return None


def _read_all_checkpoints(cp_path: Path) -> "list[tuple[int, int, str, str]]":
    """Every checkpoint row as (cp_seq, count, head_hash, cp_hash); [] if absent."""
    try:
        text = cp_path.read_text(encoding="utf-8")
    except OSError:
        return []
    out: "list[tuple[int, int, str, str]]" = []
    for ln in text.splitlines():
        if not ln.strip():
            continue
        parts = ln.split(",")
        if len(parts) != 4:
            break
        try:
            out.append((int(parts[0]), int(parts[1]), parts[2], parts[3]))
        except ValueError:
            break
    return out


def _replace_with_retry(src: Path, dst: Path, attempts: int = 5, _sleep=time.sleep) -> None:
    """os.replace(src, dst), retried on a TRANSIENT Windows PermissionError -- the atomic rename can
    briefly lose to an AV/indexer holding the just-written target under rapid writes. Only this
    IDEMPOTENT rename is retried (never the appends). After the last attempt the error RE-RAISES, so a
    genuine failure still propagates (-> OSError -> AuditError -> fail-closed). No effect off-Windows."""
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            _sleep(0.02 * (i + 1))


def _append_checkpoint(path: Path, seq: int, head_hash: str) -> None:
    """Append one tally row (chained) + refresh the off-host anchor mirror. O(1)."""
    cp_path = _checkpoint_path(path)
    prev = _read_cp_head(cp_path)
    prev_cp_seq, prev_cp_hash = (prev[2], prev[3]) if prev else (-1, GENESIS_CP_HASH)
    cp_seq = prev_cp_seq + 1
    count = seq + 1
    cp_hash = _compute_cp_hash(prev_cp_hash, count, head_hash)
    cp_line = f"{cp_seq},{count},{head_hash},{cp_hash}\n"
    # newline="" keeps the format \n-only (no Windows \r\n translation), so the tail
    # read and the splitlines() read agree byte-for-byte on the chained hash.
    with cp_path.open("a", encoding="utf-8", newline="") as cf:
        cf.write(cp_line)
        cf.flush()
        os.fsync(cf.fileno())
    # Mirror the latest tally to a separate anchor file (atomic write-then-rename).
    anchor = _anchor_path(path)
    tmp = anchor.with_name(anchor.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as af:
        af.write(cp_line)
        af.flush()
        os.fsync(af.fileno())
    _replace_with_retry(tmp, anchor)   # retry the atomic rename on transient Windows locks


def _utc_now() -> str:
    """Current time in UTC, ISO-8601 -- unambiguous across time zones for auditors."""
    return datetime.now(timezone.utc).isoformat()


# A single field is capped well under Python's csv limit (131072 bytes) so one
# adversarial value can never raise csv.Error and brick the append-only log. The
# cap is on characters; even all-4-byte chars stay under the byte limit.
_MAX_FIELD_CHARS = 8192
_TRUNCATED = "...[truncated]"


def _defang(value) -> str:
    """Make an audit value SAFE to hash and write, then neutralise formula injection.

    Three things, in order, so the same string is what we hash AND store (keeping
    the hash chain self-consistent):

    1. Encode-safe: an unpaired UTF-16 surrogate (e.g. '\\ud800') cannot encode to
       UTF-8 and would crash both _compute_row_hash and the CSV write. We replace
       such code points so encoding can never raise -- a logging crash would fail
       OPEN of the audit, the worst outcome for a legal record.
    2. Bounded: cap length so an oversized field can't trip csv's field-size limit.
    3. Formula-defanged: the audit log is a regulatory record auditors WILL open in
       Excel/Sheets. A cell starting with = + - @ (or tab/CR) is executed as a
       formula there, so an attacker-controlled '=cmd|calc!A1' could run code on the
       auditor's machine. We prefix such values with a single quote so the
       spreadsheet treats them as literal text. The stored value stays readable.
    """
    # 1. Neutralise unpaired surrogates so the value always encodes to UTF-8.
    text = str(value).encode("utf-8", "replace").decode("utf-8")
    # 2. Cap length (leave room for the marker) so csv.Error can't brick the log.
    if len(text) > _MAX_FIELD_CHARS:
        text = text[: _MAX_FIELD_CHARS - len(_TRUNCATED)] + _TRUNCATED
    # 3. Neutralise spreadsheet formula injection (run last, on the final text).
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
    # FAST PATH: read only the checkpoint's tail (O(1)) instead of the whole log.
    head = _read_cp_head(_checkpoint_path(path))
    if head is not None:
        count, head_hash, _cp_seq, _cp_hash = head
        return count, head_hash
    # Fallback (rare): no checkpoint (a pre-existing or externally-built log) ->
    # rebuild the link from the log itself. Truncation is caught by verify(), not here.
    rows = read_log(path)
    if not rows:
        return 0, GENESIS_HASH
    last = rows[-1]
    return int(last["seq"]) + 1, last["row_hash"]


# One in-process lock serialises the whole write so concurrent threads cannot read
# the same seq+hash and append it twice (a duplicate seq forks the chain and makes
# verify() cry tamper on an honest log -- R1). Held across the read->append->checkpoint
# section below, it makes each writer see the previous writer's committed row. A crash
# never leaves it stuck (Python releases it on stack unwind), so there is no stale-lock
# failure mode. It does NOT cover two SEPARATE OS processes writing one log at once --
# out of scope here (see TODO.md); every writer in this system runs in one process.
_WRITE_LOCK = threading.Lock()


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
        # Serialise the whole read->append->checkpoint section: the seq read and the
        # header decision must both be inside the lock so two writers can never fork
        # the chain or both write a header (R1).
        with _WRITE_LOCK:
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

            # Append the tamper-evident checkpoint (running tally) + refresh the anchor.
            # Inside the SAME try: a checkpoint/anchor write failure also FAILS CLOSED.
            _append_checkpoint(path, seq, row["row_hash"])
    # OSError covers file failures (disk full, permissions). csv.Error / UnicodeError
    # / ValueError are defence-in-depth: _defang already makes every value encode-safe
    # and bounded, but if any risky value ever slips past we still FAIL CLOSED with an
    # AuditError rather than crash the caller and leave an access unlogged.
    except (OSError, csv.Error, UnicodeError, ValueError) as e:
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

    # --- checkpoint / anchor cross-check: catches a TRAILING TRUNCATION (rows
    # lopped off the END) that the row chain alone provably cannot detect. ------
    cp_rows = _read_all_checkpoints(_checkpoint_path(path))
    if cp_rows:
        prev_cp = GENESIS_CP_HASH
        for i, (cp_seq, count, head_hash, cp_hash) in enumerate(cp_rows):
            if cp_seq != i:
                return False, f"checkpoint row {i}: seq {cp_seq} (a tally record was dropped)"
            if _compute_cp_hash(prev_cp, count, head_hash) != cp_hash:
                return False, f"checkpoint row {i}: hash mismatch (the tally itself was altered)"
            prev_cp = cp_hash
        _, latest_count, latest_head, _ = cp_rows[-1]
        if latest_count != len(rows):
            return False, (f"checkpoint expects {latest_count} records but the log has "
                           f"{len(rows)} -- records were truncated from the end or inserted")
        if latest_head != rows[-1]["row_hash"]:
            return False, "checkpoint head-hash != log head -- the log was altered"
        anchor_line = _tail_line(_anchor_path(path))
        if anchor_line:
            a = anchor_line.split(",")
            if len(a) == 4 and (a[1] != str(latest_count) or a[2] != latest_head):
                return False, "external anchor disagrees with the log -- tampering detected"
        return True, f"intact: {len(rows)} records, checkpoint-sealed + anchored"

    return True, f"intact: {len(rows)} records form an unbroken chain"
