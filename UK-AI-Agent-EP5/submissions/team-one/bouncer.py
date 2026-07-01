"""Bouncer (walking-skeleton version — script, NO LLM).

Returns the memories that are BOTH:
  1. relevant   — content tags overlap the query's content tags (supplied by GOVhence), and
  2. permitted  — the memory's access `category` is in the user's allowed set.

CRUCIAL SECURITY PROPERTY: the user's allowed categories are read **directly from
users.json by the Bouncer itself**, given only the username. GOVhence (an LLM) never
supplies access rights — it passes the content tags + the username, nothing more. So
access cannot be smuggled in via tags, and no LLM sits in the access-trust path.

Still skeleton-grade: no audit, no tamper-evidence. The mature RBAC/ACL + audited
bouncer is preserved in v0.1/bouncer.py and snaps back into this step later.
"""
import json
from pathlib import Path

_USERS_PATH = Path(__file__).with_name("users.json")


def allowed_categories(user, users_path=_USERS_PATH):
    """Read the user's allowed access categories DIRECTLY from users.json.

    Unknown user -> empty set (fail-closed). `*` in allow expands to every category;
    `deny` is then subtracted (deny beats allow).
    """
    data = json.loads(Path(users_path).read_text(encoding="utf-8"))
    role = data.get("users", {}).get(user)
    if role is None:
        return set()                                   # unknown user -> no access
    rdef = data.get("roles", {}).get(role, {})
    allow = set(rdef.get("allow", []))
    if "*" in allow:
        allow = set(data.get("categories", []))
    return allow - set(rdef.get("deny", []))


def retrieve(content_tags, user, memory, users_path=_USERS_PATH):
    """content_tags (relevance, from GOVhence) + user (identity) + memory store
    -> permitted matching memories (the MemoryLane).

    Access is decided ONLY by the user's allowed categories (read here from users.json),
    never by anything in `content_tags`.
    """
    allowed = allowed_categories(user, users_path)
    want = set(content_tags)
    return [m for m in memory
            if (want & set(m.get("tags", [])))          # relevant
            and m.get("category") in allowed]           # permitted (direct read)
