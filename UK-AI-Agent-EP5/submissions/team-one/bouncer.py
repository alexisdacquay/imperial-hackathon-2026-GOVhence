"""
GOVhence MEM-Ø — M1: the deterministic "bouncer".

This is the heart of the whole project. Given a user's set of allowed
categories and a list of memory items (each tagged with one category),
it returns ONLY the items whose category the user is allowed to see.

The access decision is plain code -- one line: `item.category in allowed`.
No AI, no database, no network. That is exactly what the track requires:
the permission decision must be deterministic, never made by an LLM.
"""

from dataclasses import dataclass
from pathlib import Path

import audit


@dataclass
class MemoryItem:
    """One piece of memory in the shared store.

    - id:       a short name so we can refer to it (e.g. "item1")
    - category: the single tag that decides who may see it (e.g. "schedules")
    - text:     the actual content
    """
    id: str
    category: str
    text: str


@dataclass
class Decision:
    """The result of checking one item for one user: was it allowed, and why."""
    item: MemoryItem
    allowed: bool
    reason: str


def check_item(allowed_categories, item: MemoryItem,
               revoked_ids=frozenset()) -> Decision:
    """Decide whether ONE item may be seen, given the allowed categories.

    The rule is: the item's category must be in the allowed set AND the item must
    not be revoked. This is deterministic and explainable -- we always say *why*.

    This function is the single security chokepoint, so it is DEFENSIVE and
    TOTAL: it returns a Decision for *any* input and never raises. Anything it
    cannot evaluate as a genuine, exact, string-in-set match is DENIED
    (fail-closed) with a reason, so monitoring still explains the refusal.

    Why this matters: Python's `in` is overloaded. If `allowed_categories` were
    accidentally a *string* (not a set), `"x" in "xyz"` is a SUBSTRING test and
    would silently ALLOW the wrong thing -- a fail-open leak. We forbid that here
    once, so every caller (now and in later milestones) inherits the guarantee.

    revoked_ids (M5) is the pre-computed set of EVERY revoked item id, including
    every item transitively derived from a revoked source (the graph work is done
    once at load time, never here). It defaults to an empty frozenset -- the safe
    "nothing is revoked" base case -- so older callers keep working unchanged. A
    revoked item is DENIED even if its category is allowed ("revoked beats
    allowed").
    """
    category = item.category

    # The item's tag must be a real string. A None/number/list category is a
    # data error -> DENY (fail-closed), never a silent pass or a crash.
    if not isinstance(category, str):
        return Decision(item, False,
                        f"category is not a string (got {type(category).__name__}) -> denied")

    # The allowed set must be a genuine set/frozenset. We REFUSE str/list/None
    # so membership can never degrade into a substring or sequence scan, and so
    # a missing/empty profile fails closed instead of crashing.
    if not isinstance(allowed_categories, (set, frozenset)):
        return Decision(item, False,
                        f"allowed categories is not a set (got {type(allowed_categories).__name__}) "
                        f"-> denied")

    # The revoked set must ALSO be a genuine set/frozenset -- same substring-leak
    # risk as above. But note the asymmetry: a malformed revoked set must NOT be
    # treated as empty, because "empty" means "nothing revoked" -- the PERMISSIVE
    # (fail-open) direction. So a non-set DENIES the item (fail-closed). Because
    # the gate runs once per item, a corrupt revoked list locks the whole store
    # rather than opening it -- the correct, safe blast radius.
    if not isinstance(revoked_ids, (set, frozenset)):
        return Decision(item, False,
                        f"revoked set is not a set (got {type(revoked_ids).__name__}) -> denied")

    # Revoked beats allowed: a revoked item is denied even if its category would
    # otherwise be permitted. Pure set membership -- no graph traversal here.
    if item.id in revoked_ids:
        return Decision(item, False, f"item '{item.id}' is revoked -> denied")

    if category in allowed_categories:
        return Decision(item, True, f"category '{category}' is in the allowed set")
    return Decision(item, False, f"category '{category}' is NOT in the allowed set")


def filter_allowed(allowed_categories: set[str], items: list[MemoryItem],
                   revoked_ids=frozenset()) -> list[MemoryItem]:
    """Return only the items this user is allowed to see (pure function, no side effects).

    This stays pure (no logging) so it is easy to test in isolation. The logged,
    audited version below is what the application actually calls.

    revoked_ids (M5) is threaded straight through to the gate; it defaults to the
    safe empty set, so existing callers are unaffected.
    """
    return [item for item in items if check_item(allowed_categories, item, revoked_ids).allowed]


def retrieve(user: str, allowed_categories: set[str], items: list[MemoryItem],
             log_path: Path = audit.LOG_PATH, revoked_ids=frozenset()) -> list[MemoryItem]:
    """The audited access path -- what real callers use.

    For EVERY item we make the deterministic decision AND write it to the audit
    log at this exact point (the access layer). Both ALLOWs and DENYs are logged,
    giving 100% coverage and full "who saw what, when" traceability.
    Returns only the allowed items.

    log_path defaults to the PERMANENT regulatory audit log. Tests pass a temp
    path so they never touch the real compliance record.

    revoked_ids (M5) is passed to the gate. A revocation DENY is logged by the
    SAME log_decision call below as any other denial -- so revocation needs no
    change to the audit log at all.
    """
    allowed_items: list[MemoryItem] = []
    for item in items:
        decision = check_item(allowed_categories, item, revoked_ids)
        verdict = "ALLOW" if decision.allowed else "DENY"
        # Audit FIRST, then grant. If the access cannot be recorded, it must not
        # be served -- an unlogged access breaks 100% audit coverage. We let
        # AuditError propagate (fail closed): no log => no access, loudly.
        audit.log_decision(user, item.id, item.category, verdict, decision.reason, path=log_path)
        if decision.allowed:
            allowed_items.append(item)
    return allowed_items


# --- A tiny demo so you can run this file and watch it work ---------------
# (Hardcoded here on purpose for M1. In M3 these move into a config file.)

if __name__ == "__main__":
    # Some fake memory items, each with a category tag.
    items = [
        MemoryItem("item1", "schedules",            "Truck 4: 30 pallets to Leeds, depart 06:00"),
        MemoryItem("item2", "opening-hours",        "Warehouse open Mon-Fri 05:00-22:00"),
        MemoryItem("item3", "goods-weights-volumes", "Inbound: 12 tonnes, 40 m3 of packaged goods"),
        MemoryItem("item4", "financials",           "Q3 revenue 4.2M, margin 18%"),
        MemoryItem("item5", "legal",                "Contract penalty clause for late delivery"),
    ]

    # Bob is a driver in logistics. These are the categories his role allows.
    bob_allowed = {"schedules", "opening-hours", "goods-weights-volumes"}

    # M5: item1 has been revoked (its source leaked, say). Even though 'schedules'
    # is in Bob's allowed categories, a revoked item must be DENIED -- "revoked
    # beats allowed". In the real app this set comes from memory.revoked_ids(),
    # which expands the lineage graph; here we hardcode it so the demo is
    # self-contained.
    revoked = {"item1"}

    user = "bob"
    print(f"User: {user} (driver, logistics)")
    print(f"Allowed categories: {sorted(bob_allowed)}")
    print(f"Revoked items:      {sorted(revoked)}")
    print("-" * 60)

    # Use the AUDITED access path: it makes each decision, logs it at the
    # access layer, and returns only the allowed items.
    returned = retrieve(user, bob_allowed, items, revoked_ids=revoked)

    # Show the same decisions on screen for convenience (the source of truth
    # is now the audit log, not this print-out).
    for item in items:
        decision = check_item(bob_allowed, item, revoked)
        verdict = "ALLOW" if decision.allowed else "DENY "
        print(f"{verdict} {item.id}  ({decision.reason})")

    print("-" * 60)
    print(f"Returned {len(returned)} of {len(items)} items")
    print(f"Every decision above was written to: {audit.LOG_PATH.name}")
