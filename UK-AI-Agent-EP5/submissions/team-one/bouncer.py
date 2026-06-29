"""
M1 — The deterministic "bouncer".

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


def check_item(allowed_categories, item: MemoryItem) -> Decision:
    """Decide whether ONE item may be seen, given the allowed categories.

    The whole rule is: is the item's category in the allowed set?
    This is deterministic and explainable -- we always say *why*.

    This function is the single security chokepoint, so it is DEFENSIVE and
    TOTAL: it returns a Decision for *any* input and never raises. Anything it
    cannot evaluate as a genuine, exact, string-in-set match is DENIED
    (fail-closed) with a reason, so monitoring still explains the refusal.

    Why this matters: Python's `in` is overloaded. If `allowed_categories` were
    accidentally a *string* (not a set), `"x" in "xyz"` is a SUBSTRING test and
    would silently ALLOW the wrong thing -- a fail-open leak. We forbid that here
    once, so every caller (now and in later milestones) inherits the guarantee.
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

    if category in allowed_categories:
        return Decision(item, True, f"category '{category}' is in the allowed set")
    return Decision(item, False, f"category '{category}' is NOT in the allowed set")


def filter_allowed(allowed_categories: set[str], items: list[MemoryItem]) -> list[MemoryItem]:
    """Return only the items this user is allowed to see (pure function, no side effects).

    This stays pure (no logging) so it is easy to test in isolation. The logged,
    audited version below is what the application actually calls.
    """
    return [item for item in items if check_item(allowed_categories, item).allowed]


def retrieve(user: str, allowed_categories: set[str], items: list[MemoryItem],
             log_path: Path = audit.LOG_PATH) -> list[MemoryItem]:
    """The audited access path -- what real callers use.

    For EVERY item we make the deterministic decision AND write it to the audit
    log at this exact point (the access layer). Both ALLOWs and DENYs are logged,
    giving 100% coverage and full "who saw what, when" traceability.
    Returns only the allowed items.

    log_path defaults to the PERMANENT regulatory audit log. Tests pass a temp
    path so they never touch the real compliance record.
    """
    allowed_items: list[MemoryItem] = []
    for item in items:
        decision = check_item(allowed_categories, item)
        verdict = "ALLOW" if decision.allowed else "DENY"
        # Audit FIRST, then grant. If the access cannot be recorded, it must not
        # be served -- an unlogged access breaks 100% audit coverage. We let
        # AuditError propagate (fail closed): no log => no access, loudly.
        audit.log_decision(user, item.id, item.category, verdict, decision.reason, path=log_path)
        if decision.allowed:
            allowed_items.append(item)
    return allowed_items


# --- A tiny demo so you can run this file and watch it work ---------------
# (Hardcoded here on purpose for M1. In M3 these move into a YAML file.)

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

    user = "bob"
    print(f"User: {user} (driver, logistics)")
    print(f"Allowed categories: {sorted(bob_allowed)}")
    print("-" * 60)

    # Use the AUDITED access path: it makes each decision, logs it at the
    # access layer, and returns only the allowed items.
    returned = retrieve(user, bob_allowed, items)

    # Show the same decisions on screen for convenience (the source of truth
    # is now the audit log, not this print-out).
    for item in items:
        decision = check_item(bob_allowed, item)
        verdict = "ALLOW" if decision.allowed else "DENY "
        print(f"{verdict} {item.id}  ({decision.reason})")

    print("-" * 60)
    print(f"Returned {len(returned)} of {len(items)} items")
    print(f"Every decision above was written to: {audit.LOG_PATH.name}")
