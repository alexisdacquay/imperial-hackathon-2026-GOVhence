"""
GOVhence MEM-Ø — M6: the single command-line entrypoint.

This wires the three existing pieces together for a REAL run -- nothing about
the access decision is hardcoded here:

  memory.py  -> turns a username into the exact SET of allowed categories,
                and turns the lineage graph into the full REVOKED set
  bouncer.py -> the deterministic gate; retrieve() = decide each item AND
                log it at the retrieval layer (the single chokepoint)
  audit.py   -> the tamper-evident log every decision is written to
                (called from inside retrieve(), not from here)

Run it:
    python cli.py bob
    python cli.py alice

The username is the ONLY input. Who-may-see-what comes from users.json, what is
revoked comes from lineage.json, and the memory items come from memory_store.json.
cli.py never invents a permission, a tag, or a revocation -- it only wires the
real loaders to the real gate, exactly as a production caller would.
"""

import argparse
import json
import sys
from pathlib import Path

import audit
import bouncer
import memory

# The shared memory store lives next to this file: items are DATA, not code, so
# they are no longer hardcoded -- the same philosophy as users.json / lineage.json.
STORE_PATH = Path(__file__).with_name("memory_store.json")


def load_items(path: Path = STORE_PATH) -> list[bouncer.MemoryItem]:
    """Read memory_store.json into a list of MemoryItem -- fail-closed on any problem.

    Shape: {"items": [{"id", "category", "text"}, ...]}. Like the loaders in
    memory.py, ANY read/parse/shape problem raises memory.ConfigError rather than
    returning a partial list. A STRUCTURALLY VALID but empty store ({"items": []})
    is allowed and returns [] -- the safe, fail-closed direction (the user simply
    sees nothing); only a missing/non-list "items" or a malformed entry is an error.
    MemoryItem is defined in bouncer.py, so this loader lives here in the wiring
    layer rather than in memory.py -- that keeps memory.py free of any dependency
    on the bouncer.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise memory.ConfigError(f"cannot read memory store at {path}: {e}") from e

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise memory.ConfigError(f"memory store is not valid JSON: {e}") from e

    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise memory.ConfigError("memory store must be a JSON object with an 'items' list")

    items: list[bouncer.MemoryItem] = []
    for entry in data["items"]:
        # 'id' is the audit key AND the revocation key (revocation is `item.id in
        # revoked_ids`). A non-string or empty id would corrupt the audit trail and
        # silently ESCAPE id-based revocation -- a fail-OPEN risk -- so we fail
        # closed on it here, consistent with memory.py's strict typing.
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
            raise memory.ConfigError(
                "each store item must be an object with a non-empty string 'id'")
        # 'category', by contrast, is passed through EXACTLY as the file has it (even
        # if missing or the wrong type). We never fix it up here: read time must
        # never invent or repair a tag. A missing/bad tag simply reaches the bouncer,
        # which denies it (fail-closed) -- untagged content is never retrievable.
        # 'tags' are CONTENT tags for relevance matching only (never access). A malformed tags
        # value degrades to no tags -> the item just won't match a query (safe, not a leak).
        raw_tags = entry.get("tags", ())
        tags = tuple(t for t in raw_tags if isinstance(t, str)) if isinstance(raw_tags, (list, tuple)) else ()
        items.append(bouncer.MemoryItem(entry["id"], entry.get("category"),
                                        entry.get("text", ""), tags))
    return items


def main(argv=None, *, log_path=None) -> int:
    """Resolve a user's allowed view from config, run it through the audited gate,
    and print every decision. Returns a process exit code (0 = ok, non-zero = an
    access could not be safely served -- we fail closed and say why).

    log_path defaults to the PERMANENT regulatory audit log (audit.LOG_PATH) -- the
    real app writes there. Tests pass a temporary path so they never touch the real
    compliance record (and so the fail-closed 'no log -> no access' path can be
    exercised against a deliberately unwritable location)."""
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="GOVhence MEM-0: retrieve the shared-memory items a user is allowed to see.")
    parser.add_argument("user", help="the username to retrieve memory for (e.g. bob, alice)")
    args = parser.parse_args(argv)

    # Resolve EVERYTHING from config, fail-closed. If anything cannot be determined
    # safely (unknown user, broken file), we print a clear error and return a
    # non-zero code: no access is served on any doubt.
    try:
        allowed = memory.allowed_categories_for_user(args.user)
        revoked = memory.revoked_ids()
        items = load_items()
    except memory.ConfigError as e:
        print(f"ACCESS DENIED -- configuration error: {e}", file=sys.stderr)
        return 2

    print(f"User: {args.user}")
    print(f"Allowed categories:            {sorted(allowed)}")
    print(f"Revoked items (incl. derived): {sorted(revoked)}")
    print("-" * 72)

    # The AUDITED path: retrieve() makes each deterministic decision AND writes it
    # to the tamper-evident log at the retrieval layer, then returns only the
    # allowed items. If the log cannot be written, it raises AuditError -- no log,
    # no access -- which we surface as a fail-closed non-zero exit.
    # Capture the effective log destination ONCE so the run, and the summary line
    # that reports where the record was written, can never disagree (a legal record
    # must not misstate its own location).
    effective_log = log_path or audit.LOG_PATH
    try:
        returned = bouncer.retrieve(args.user, allowed, items, revoked_ids=revoked,
                                    log_path=effective_log)
    except audit.AuditError as e:
        print(f"ACCESS DENIED -- could not write the audit log: {e}", file=sys.stderr)
        return 3

    # Show every decision on screen for convenience. The SOURCE OF TRUTH is the
    # audit log just written by retrieve(); this re-derives the same verdict +
    # reason with the pure check_item() (no logging) purely to display it.
    for item in items:
        decision = bouncer.check_item(allowed, item, revoked)
        verdict = "ALLOW" if decision.allowed else "DENY "
        print(f"{verdict} {item.id:14} {decision.reason}")

    print("-" * 72)
    print(f"Returned {len(returned)} of {len(items)} items "
          f"-- every decision above was written to {effective_log.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
