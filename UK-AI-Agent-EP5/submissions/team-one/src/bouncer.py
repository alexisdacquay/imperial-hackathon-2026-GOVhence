"""Bouncer — the deterministic access gate over CocoShaMem (real, not a stub).

DEFINITIVE VOCABULARY (repo-wide — two very different kinds of "tags", never mixed):
  topics     — what a memory/query is ABOUT (content). Produced by the LLM
               (Classifier). Used ONLY for relevance: ANY overlap matches.
               A topic can never grant access.
  labels     — security labels a memory CARRIES (data side): who may see it.
  clearances — security labels a user HOLDS via their role (users.json).

ACCESS RULE (whitelist-only, government-classification style, fail-closed):
  permitted  <=>  labels is non-empty  AND  labels ⊆ clearances   (ALL labels held)
  relevant   <=>  topics ∩ query_topics is non-empty              (ANY topic shared)
  returned   <=>  permitted AND relevant

No deny list, no wildcard: access exists only where explicitly granted, so a new
label grants nobody anything until a role lists it. A memory with NO labels is
visible to nobody (the empty set would otherwise pass every subset check — that
would be fail-open). Matching is strict string equality (case-sensitive).

CRUCIAL SECURITY PROPERTY: clearances are read directly from users.json by the
Bouncer itself, given only the username. GOVhence passes topics + username,
never access rights — so access cannot be smuggled via topics and no LLM sits
in the permission decision (spec: enforcement must be deterministic).

Malformed config or memory data raises ConfigError (loud, fail-closed) rather
than leaking a bare TypeError from inside set operations.
"""
import json
from pathlib import Path

_DATA = Path(__file__).parent.parent / "data"
_USERS_PATH = _DATA / "users.json"
_MEMORY_PATH = _DATA / "cocoshamem.seed.json"


class ConfigError(Exception):
    """users.json or memory data is malformed. Nothing is served (fail-closed)."""


# --- validation helpers (totality: element TYPES checked, not just containers) ---

def _str_set(value, what):
    """value must be a list of strings -> set of them; anything else -> ConfigError."""
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ConfigError(f"{what} must be a list of strings, got {value!r}")
    return set(value)


def _item_sets(item):
    """memory item -> (labels, topics) as sets; malformed item -> ConfigError."""
    if not isinstance(item, dict):
        raise ConfigError(f"memory item must be an object, got {item!r}")
    labels = _str_set(item.get("labels"), "memory 'labels'")
    topics = _str_set(item.get("topics"), "memory 'topics'")
    return labels, topics


def _topic_set(query_topics):
    """query topics -> set of strings. Rejects a bare string (it would silently
    split into characters) and anything non-iterable or non-string-elemented."""
    if isinstance(query_topics, str):
        raise ConfigError("query topics must be a list of strings, not a single string")
    try:
        as_list = list(query_topics)
    except TypeError:
        raise ConfigError(f"query topics must be a list of strings, got {query_topics!r}")
    return _str_set(as_list, "query topics")


# --- the permission side (labels vs clearances; topics play NO part here) --------

def visible(labels, clearances):
    """THE permission chokepoint: non-empty labels, ALL held. Pure set maths."""
    return bool(labels) and labels <= clearances


def clearances_for(user, users_path=_USERS_PATH):
    """Read the user's clearances DIRECTLY from users.json (name -> role -> clearances).

    Unknown or invalid user -> empty set (fail-closed). A role with a missing or
    malformed 'clearances' list is a config bug -> ConfigError (loud, fail-closed).
    """
    data = json.loads(Path(users_path).read_text(encoding="utf-8"))
    users, roles = data.get("users", {}), data.get("roles", {})
    if not isinstance(users, dict) or not isinstance(roles, dict):
        raise ConfigError("users.json: 'users' and 'roles' must be objects")
    if not isinstance(user, str):
        return set()                                   # invalid identity -> no access
    role = users.get(user)
    if role is None:
        return set()                                   # unknown user -> no access
    rdef = roles.get(role)
    if not isinstance(rdef, dict) or "clearances" not in rdef:
        raise ConfigError(f"users.json: role {role!r} has no 'clearances' list")
    return _str_set(rdef["clearances"], f"role {role!r} 'clearances'")


def filter_visible(memories, clearances):
    """Permission HALF only (no relevance) — e.g. for scoping the Classifier's
    known-topics vocabulary to what this user may see."""
    return [m for m in memories if visible(_item_sets(m)[0], clearances)]


# --- the memory store + the full retrieval path ----------------------------------

def load_memories(memory_path=_MEMORY_PATH):
    """Load CocoShaMem from disk, validating every item at the door."""
    raw = json.loads(Path(memory_path).read_text(encoding="utf-8")).get("memories", [])
    if not isinstance(raw, list):
        raise ConfigError("memory store: 'memories' must be a list")
    for item in raw:
        _item_sets(item)                               # malformed item -> ConfigError
    return raw


def retrieve(query_topics, user, memories=None, users_path=_USERS_PATH,
             memory_path=_MEMORY_PATH):
    """query topics (relevance, from the LLM) + user (identity) -> the MemoryLane:
    memories that are BOTH permitted (labels ⊆ clearances) and relevant (ANY topic).

    If `memories` is None the store is loaded from cocoshamem — the real search
    path. Access is decided ONLY by labels vs the user's clearances (read here
    from users.json), never by anything in `query_topics`.
    """
    want = _topic_set(query_topics)
    clearances = clearances_for(user, users_path)
    if memories is None:
        memories = load_memories(memory_path)
    lane = []
    for m in memories:
        labels, topics = _item_sets(m)
        if visible(labels, clearances) and (topics & want):
            lane.append(m)
    return lane
