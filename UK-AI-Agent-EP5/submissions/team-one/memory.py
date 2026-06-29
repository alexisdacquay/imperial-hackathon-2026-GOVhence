"""
M3 — Loaders: turn the users.json config into inputs the bouncer understands.

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

# The config lives next to this file so the demo and tests find it the same way.
USERS_PATH = Path(__file__).with_name("users.json")

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
