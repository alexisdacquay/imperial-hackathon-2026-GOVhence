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
import os
import threading
import time
from pathlib import Path

import eventlog

_DATA = Path(__file__).parent.parent / "data"
_USERS_PATH = _DATA / "users.json"
_SEED_PATH = _DATA / "cocoshamem.seed.json"  # committed demo seed (never written at runtime)
_STORE_PATH = _DATA / "cocoshamem.json"      # runtime store (git-ignored; the Memoriser writes it)


class ConfigError(Exception):
    """users.json or memory data is malformed. Nothing is served (fail-closed)."""


# --- validation helpers (totality: element TYPES checked, not just containers) ---

def _load_json(path, what):
    """Read a JSON object from disk. Missing/unreadable file, invalid JSON, or a
    non-object top level all raise ConfigError (loud, fail-closed) — never a bare
    FileNotFoundError/JSONDecodeError leaking to callers who catch ConfigError."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ConfigError(f"{what}: cannot read {path}: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{what}: top level must be an object, got {type(data).__name__}")
    return data


# --- users.json (the ACL source) cache -------------------------------------------
# The profile store is read on the HOT path — up to 3x per request (GOVhence
# pre-scope, Bouncer read, Memoriser writer-cap) plus all_labels — so we keep the
# parsed+validated config in memory and only re-read from disk when the cached copy
# is older than a short TTL (default 5s, env GOVHENCE_ACL_TTL_SECONDS). This is the
# spec's "stay synchronized with source permissions under concurrent updates": an
# edit to users.json takes effect within TTL, with NO restart. Trade-off (accepted):
# a revoked clearance keeps working for up to TTL seconds (the staleness window) —
# keep TTL small. ttl=0 forces a fresh read every call (the pre-cache behaviour;
# used by tests). Reads only; the file is edited out of band.
_ACL_TTL = float(os.environ.get("GOVHENCE_ACL_TTL_SECONDS", "5.0"))
_users_cache = {}                                # resolved path -> (loaded_at_monotonic, parsed dict)
_ACL_LOCK = threading.Lock()                     # a long-lived session may be multi-threaded


def _users_config(path=_USERS_PATH, ttl=None):
    """Parsed+validated users.json, from memory when fresh, else re-read from disk.

    Fail-closed preserved: a malformed/missing file raises ConfigError (via
    _load_json) and the cache entry is NOT updated, so the next call retries at
    once — a stale-but-valid copy is never served over a now-broken file.
    """
    if ttl is None:
        ttl = _ACL_TTL
    key = str(path)                              # cheap key (no resolve() syscall); callers
    with _ACL_LOCK:                              # pass a stable path, so the raw string is enough
        hit = _users_cache.get(key)
        if hit is not None and (time.monotonic() - hit[0]) < ttl:
            return hit[1]                        # fresh enough -> serve from memory
        data = _load_json(path, "users.json")    # raises ConfigError -> propagate, cache untouched
        _users_cache[key] = (time.monotonic(), data)
        return data


def _reset_acl_cache():
    """Drop all cached users configs (used by tests for a cold start each run)."""
    with _ACL_LOCK:
        _users_cache.clear()


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


def clearances_for(user, users_path=_USERS_PATH, by="Bouncer", ttl=None):
    """Read the user's clearances from the cached users.json (name -> role -> clearances).

    Unknown or invalid user -> empty set (fail-closed). A role with a missing or
    malformed 'clearances' list is a config bug -> ConfigError (loud, fail-closed).
    `by` names the component that requested this check (GOVhence for the pre-scope
    read, Bouncer on the read path, Memoriser on the writer-cap check) — recorded
    so the console attributes the credential read to the right component. `ttl`
    overrides the ACL cache freshness window (ttl=0 = always re-read from disk).

    Every check is recorded to the event log with its duration (best-effort:
    emit args are pre-stringified with eventlog.safe so recording can NEVER raise
    into this gate).
    """
    t0 = time.perf_counter()
    try:
        data = _users_config(users_path, ttl)
        users, roles = data.get("users", {}), data.get("roles", {})
        if not isinstance(users, dict) or not isinstance(roles, dict):
            raise ConfigError("users.json: 'users' and 'roles' must be objects")
        if not isinstance(user, str):
            clearances = set()                         # invalid identity -> no access
        else:
            role = users.get(user)
            if role is None:
                clearances = set()                     # unknown user -> no access
            else:
                rdef = roles.get(role)
                if not isinstance(rdef, dict) or "clearances" not in rdef:
                    raise ConfigError(f"users.json: role {role!r} has no 'clearances' list")
                clearances = _str_set(rdef["clearances"], f"role {role!r} 'clearances'")
    except ConfigError as e:
        eventlog.emit("credentials", component=by, user=eventlog.safe(user, 80),
                      status="failure", error=eventlog.safe(e),
                      ms=round((time.perf_counter() - t0) * 1000, 3))
        raise
    eventlog.emit("credentials", component=by, user=eventlog.safe(user, 80),
                  status="ok", known=bool(clearances) or (isinstance(user, str) and user in users),
                  clearances=sorted(clearances),
                  ms=round((time.perf_counter() - t0) * 1000, 3))
    return clearances


def all_labels(users_path=_USERS_PATH, ttl=None):
    """The known security-label vocabulary: the union of every role's clearances in
    users.json. This is what a write-time labeller may choose from — a label nobody
    could ever hold cannot be assigned. Malformed config -> ConfigError. Reads via
    the ACL cache (ttl overrides the freshness window)."""
    data = _users_config(users_path, ttl)
    roles = data.get("roles")
    if not isinstance(roles, dict):
        raise ConfigError("users.json: 'roles' must be an object")
    labels = set()
    for role, rdef in roles.items():
        if not isinstance(rdef, dict) or "clearances" not in rdef:
            raise ConfigError(f"users.json: role {role!r} has no 'clearances' list")
        labels |= _str_set(rdef["clearances"], f"role {role!r} 'clearances'")
    return labels


def filter_visible(memories, clearances):
    """Permission HALF only (no relevance) — e.g. for scoping the Classifier's
    known-topics vocabulary to what this user may see."""
    return [m for m in memories if visible(_item_sets(m)[0], clearances)]


# --- the memory store + the full retrieval path ----------------------------------

def resolve_memory_path(store_path=_STORE_PATH, seed_path=_SEED_PATH):
    """Which file to READ memories from: the runtime store once the Memoriser has
    written one, else the committed seed. (The Memoriser owns all WRITING.)"""
    store = Path(store_path)
    return store if store.exists() else Path(seed_path)


def load_memories(memory_path=None):
    """Load CocoShaMem from disk, validating every item at the door.

    memory_path=None (the normal case) resolves to the runtime store if it
    exists, else the committed seed — so 'teach, restart, recall' works."""
    if memory_path is None:
        memory_path = resolve_memory_path()
    raw = _load_json(memory_path, "memory store").get("memories", [])
    if not isinstance(raw, list):
        raise ConfigError("memory store: 'memories' must be a list")
    for item in raw:
        _item_sets(item)                               # malformed item -> ConfigError
    return raw


def retrieve(query_topics, user, memories=None, users_path=_USERS_PATH,
             memory_path=None):
    """query topics (relevance, from the LLM) + user (identity) -> the MemoryLane:
    memories that are BOTH permitted (labels ⊆ clearances) and relevant (ANY topic).

    If `memories` is None the store is loaded from disk (runtime store, falling
    back to the seed — see resolve_memory_path). Access is decided ONLY by labels
    vs the user's clearances (read here from users.json), never by `query_topics`.

    Every read is recorded to the event log — request, per-memory ALLOW/DENY
    decisions (for the relevant ones), permitted/withheld counts, duration in ms,
    and failures — best-effort: recording can never change the decision.
    """
    t0 = time.perf_counter()
    try:
        want = _topic_set(query_topics)
        clearances = clearances_for(user, users_path)
        if memories is None:
            memories = load_memories(memory_path)
        lane, decisions = [], []
        for m in memories:
            labels, topics = _item_sets(m)
            matched = topics & want
            if not matched:
                continue                               # not relevant -> not evaluated
            permitted = visible(labels, clearances)
            if permitted:
                lane.append(m)
                reason = "all labels held"
            elif not labels:
                reason = "no labels -> visible to nobody (fail-closed)"
            else:
                reason = f"missing clearance(s) {sorted(labels - clearances)}"
            # SECURITY: the events feed has no access control, so a WITHHELD body
            # here would be an ungoverned copy that defeats the gate. Record the
            # body ONLY for ALLOW (the requester was served it anyway); redact it
            # for DENY, keeping labels + reason for the audit trail.
            decisions.append({"text": eventlog.safe(m.get("text", ""), 160) if permitted else "[withheld]",
                              "labels": sorted(labels), "matched": sorted(matched),
                              "decision": "ALLOW" if permitted else "DENY",
                              "reason": reason})
    except ConfigError as e:
        eventlog.emit("bouncer.read", user=eventlog.safe(user, 80), status="failure",
                      error=eventlog.safe(e), ms=round((time.perf_counter() - t0) * 1000, 3))
        raise
    eventlog.emit("bouncer.read", user=eventlog.safe(user, 80), status="success",
                  topics=sorted(want), clearances=sorted(clearances),
                  relevant=len(decisions), permitted=len(lane),
                  withheld=len(decisions) - len(lane), decisions=decisions,
                  ms=round((time.perf_counter() - t0) * 1000, 3))
    return lane
