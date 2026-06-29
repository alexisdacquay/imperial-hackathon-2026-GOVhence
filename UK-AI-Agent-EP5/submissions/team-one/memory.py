"""
GOVhence MEM-Ø — M3/M5: loaders that turn config into inputs the bouncer understands.

The bouncer's job is unchanged. It still receives ONE plain set of allowed
categories and does its strict `category in allowed` check. This module is the
only thing that knows about roles, the "*" wildcard, and deny lists -- it
resolves all of that at LOAD time into that single set, so the security
chokepoint stays simple and deterministic.

KEY SECURITY CHOICE — the loader is FAIL-CLOSED, like the bouncer.
An unknown user, an unknown role, a "*" with no category list, or a broken file
raises a clear error instead of quietly returning a permissive set. A loader
that returned "everything" on a typo would be a fail-OPEN leak just as dangerous
as the substring trap the bouncer guards against.

DENY BEATS ALLOW (static version).
A role may list `allow` and `deny`. The final set is `allow - deny`. We subtract
the deny list here, at load time, so the bouncer never sees "deny" as a separate
idea -- the forbidden categories are simply already gone from the set it checks.
(The richer, lineage-based deny comes later in M5.)
"""

import json
from pathlib import Path

# The config files live next to this file so the demo and tests find them the same way.
USERS_PATH = Path(__file__).with_name("users.json")
LINEAGE_PATH = Path(__file__).with_name("lineage.json")

# A role using "allow": ["*"] means "every known category". The single source of
# truth for "every category" is the top-level "categories" list in users.json.
WILDCARD = "*"


class ConfigError(Exception):
    """Raised when users.json is missing, malformed, or names something unknown.

    The loader fails CLOSED: rather than guess (and risk handing back a
    permissive set), it stops with a clear, specific message. Callers treat this
    as "no access could be determined" -- the safe default.
    """


def load_config(path: Path = USERS_PATH) -> dict:
    """Read and minimally validate users.json. Returns the parsed config dict.

    We check the SHAPE here (the three sections exist and are the right type) so
    that every later lookup can trust the structure. Any problem -> ConfigError
    (fail-closed), never a half-loaded config.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"cannot read users config at {path}: {e}") from e

    try:
        config = json.loads(text)
    except json.JSONDecodeError as e:
        raise ConfigError(f"users config is not valid JSON: {e}") from e

    if not isinstance(config, dict):
        raise ConfigError("users config must be a JSON object at the top level")

    # The three sections we rely on, and the type each must be.
    for key, expected_type in (("categories", list), ("roles", dict), ("users", dict)):
        if key not in config:
            raise ConfigError(f"users config is missing the '{key}' section")
        if not isinstance(config[key], expected_type):
            raise ConfigError(f"'{key}' section must be a {expected_type.__name__}")

    return config


def categories_for_role(role_name: str, config: dict) -> set[str]:
    """Resolve ONE role into the exact set of categories it may see.

    Steps: look up the role, expand a "*" allow into every known category, then
    subtract the deny list (deny beats allow). Returns a plain set -- exactly
    what the bouncer expects. Unknown role / malformed role -> ConfigError.
    """
    roles = config["roles"]
    if role_name not in roles:
        raise ConfigError(f"unknown role '{role_name}' (not defined in users config)")

    role = roles[role_name]
    if not isinstance(role, dict):
        raise ConfigError(f"role '{role_name}' must be an object with 'allow'/'deny' lists")

    allow = role.get("allow", [])
    deny = role.get("deny", [])
    if not isinstance(allow, list) or not isinstance(deny, list):
        raise ConfigError(f"role '{role_name}': 'allow' and 'deny' must both be lists")

    all_categories = set(config["categories"])

    # Catch config typos: every category a role names (in allow or deny, ignoring
    # the "*" wildcard) MUST be a real, known category. A role granting access to
    # a category that doesn't exist is a silent misconfiguration -- in a
    # governance tool that should be flagged, not quietly accepted. Fail closed.
    named = (set(allow) | set(deny)) - {WILDCARD}
    unknown = named - all_categories
    if unknown:
        raise ConfigError(
            f"role '{role_name}' names unknown categor{'y' if len(unknown) == 1 else 'ies'} "
            f"{sorted(unknown)} -- not in the 'categories' list (typo?)")

    # Expand the wildcard. "*" means "every known category"; it is NOT a category
    # name itself, so it must never end up in the returned set.
    if WILDCARD in allow:
        allow_set = set(all_categories)
    else:
        allow_set = set(allow)

    deny_set = set(deny)

    # Deny beats allow: whatever is denied is removed, even if also allowed.
    return allow_set - deny_set


def allowed_categories_for_user(user: str, config: dict = None) -> set[str]:
    """The function callers actually use: username -> set of allowed categories.

    Looks up the user's role, then resolves that role to a set (with wildcard
    expanded and deny subtracted). Unknown user -> ConfigError (fail-closed):
    we never invent permissions for someone not in the directory.
    """
    if config is None:
        config = load_config()

    users = config["users"]
    if user not in users:
        raise ConfigError(f"unknown user '{user}' (not in users config)")

    return categories_for_role(users[user], config)


# --- M5: lineage-based revocation ----------------------------------------
# Memory items can be DERIVED_FROM other items. When a SOURCE item is revoked,
# the revocation must propagate to EVERY item derived from it, transitively.
# As with deny-beats-allow in M3, we resolve all of this HERE, at load time,
# into one flat set of revoked ids -- so the bouncer's gate stays a pure set
# lookup and never has to walk a graph.

def load_lineage(path: Path = LINEAGE_PATH) -> dict:
    """Read and minimally validate lineage.json. Returns the parsed dict.

    Shape: {"derived_from": {child: [parents...]}, "revoked": [ids...]}. Both
    sections are OPTIONAL (absent = empty), but when present their TYPES are
    strictly checked. Fail-closed like load_config: any read/parse/shape problem
    -> ConfigError, NEVER a silently-empty graph (an empty graph would mean
    "nothing revoked" -- the permissive, fail-open direction).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"cannot read lineage file at {path}: {e}") from e

    try:
        lineage = json.loads(text)
    except json.JSONDecodeError as e:
        raise ConfigError(f"lineage file is not valid JSON: {e}") from e

    if not isinstance(lineage, dict):
        raise ConfigError("lineage file must be a JSON object at the top level")

    derived = lineage.get("derived_from", {})
    revoked = lineage.get("revoked", [])
    if not isinstance(derived, dict):
        raise ConfigError("'derived_from' must be an object (child -> [parents])")
    if not isinstance(revoked, list):
        raise ConfigError("'revoked' must be a list of item ids")

    # Each derived_from value must itself be a list of parent ids, so the closure
    # traversal below can trust the structure it walks.
    for child, parents in derived.items():
        if not isinstance(parents, list):
            raise ConfigError(f"'derived_from[{child}]' must be a list of parent ids")

    return lineage


def revoked_closure(lineage: dict) -> frozenset[str]:
    """Resolve the lineage graph into EVERY revoked id, including transitives.

    The file stores child -> parents (author-friendly). To propagate a revoked
    SOURCE down to its derivatives we need parent -> children, so we invert the
    map once here, then walk outward from every revoked source.

    A `seen` set makes the walk TERMINATE even if the graph contains a cycle
    (A derived_from B, B derived_from A -- a data error that must never hang the
    loader). We use an explicit stack (not recursion) so a very long chain cannot
    raise RecursionError. Returns a frozenset -- the immutable set type the gate
    accepts.
    """
    derived_from = lineage.get("derived_from", {})
    revoked_sources = lineage.get("revoked", [])

    # Invert child -> parents  into  parent -> [children]  for outward traversal.
    children: dict[str, list[str]] = {}
    for child, parents in derived_from.items():
        for parent in parents:
            children.setdefault(parent, []).append(child)

    seen: set[str] = set()
    stack = list(revoked_sources)          # start from every revoked source
    while stack:
        node = stack.pop()
        if node in seen:                   # cycle / diamond guard: never revisit
            continue
        seen.add(node)
        stack.extend(children.get(node, []))   # enqueue this node's derivatives

    return frozenset(seen)


def revoked_ids(path: Path = LINEAGE_PATH) -> frozenset[str]:
    """Load the lineage file and return the full revoked closure as a frozenset.

    This is what callers hand to the bouncer. Fail-closed: a broken lineage file
    raises ConfigError (access cannot be safely determined); it never returns an
    empty 'nothing revoked' set on error.
    """
    return revoked_closure(load_lineage(path))


# --- A tiny demo so you can run this file and watch the resolution work ----

if __name__ == "__main__":
    config = load_config()
    print(f"Loaded users config from: {USERS_PATH.name}")
    print(f"Known categories: {sorted(config['categories'])}")
    print("-" * 60)
    for user in config["users"]:
        role = config["users"][user]
        allowed = allowed_categories_for_user(user, config)
        print(f"{user:6} (role: {role:7}) -> may see {sorted(allowed)}")

    # M5: show the lineage graph resolve to the full revoked set. Revoking one
    # SOURCE pulls in every item transitively derived from it.
    print("-" * 60)
    lineage = load_lineage()
    print(f"Loaded lineage from: {LINEAGE_PATH.name}")
    print(f"Revoked sources:     {sorted(lineage.get('revoked', []))}")
    print(f"Full revoked set:    {sorted(revoked_closure(lineage))}  (sources + all derivatives)")
