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
retention, e.g. 7 years). Append-only = we never rewrite history.
"""

import csv
from datetime import datetime, timezone
from pathlib import Path

# The log lives next to this file so it is easy to find during the demo.
LOG_PATH = Path(__file__).with_name("audit_log.csv")

# The columns, in order. "timestamp" is first so the file sorts chronologically.
FIELDS = ["timestamp", "user", "item_id", "category", "decision", "reason"]


def _utc_now() -> str:
    """Current time in UTC, ISO-8601 -- unambiguous across time zones for auditors."""
    return datetime.now(timezone.utc).isoformat()


def log_decision(user: str, item_id: str, category: str, decision: str, reason: str,
                 path: Path = LOG_PATH) -> None:
    """Append exactly one decision row to the audit log.

    decision is the string "ALLOW" or "DENY". We write the header row once,
    when the file is first created, then only ever append.
    """
    new_file = not path.exists()
    # newline="" is the documented way to use csv on all platforms (avoids blank rows on Windows).
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow({
            "timestamp": _utc_now(),
            "user": user,
            "item_id": item_id,
            "category": category,
            "decision": decision,
            "reason": reason,
        })


def read_log(path: Path = LOG_PATH) -> list[dict]:
    """Read the whole audit log back as a list of rows (for verification/traceability)."""
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
