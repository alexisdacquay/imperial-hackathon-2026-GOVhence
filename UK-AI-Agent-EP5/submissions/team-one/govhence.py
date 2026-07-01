"""GOVhence — the SOLE orchestrator. A deterministic SCRIPT by design, NOT an LLM:
its job is pure routing/sequencing/waiting, so it stays out of the trust path and
can't be prompt-injected. The intelligence lives in the LLM roles it calls.

BUILD TARGET #1 of PRD-2026-07-01.md: run the whole chain end-to-end with the
simplest possible components and NO security/audit burden, to prove the process
logic. Hub-and-spoke — everything routes through GOVhence, nothing bypasses it:

    User -> GOVhence -> Classifier -> GOVhence -> Judge -> GOVhence
         -> Bouncer (read) and/or Memoriser (write) -> Responder -> GOVhence -> User

Run:  python govhence.py bob "where is the best sandwich in London?"
      python govhence.py bob "No, not Tokyo, the office is in London"
      python govhence.py bob "Hi"
"""
import json
import sys
from pathlib import Path

import classifier
import judge
import bouncer
import memoriser
import responder

# --- data stores: loaded from JSON, never hardcoded in the script ---------------
_HERE = Path(__file__).parent
USERS_PATH = _HERE / "users.json"              # the user base / profile store
MEMORY_PATH = _HERE / "cocoshamem.seed.json"   # CocoShaMem seed (shared memories)


def _load_profiles(path=USERS_PATH):
    """name -> {role, department}, resolved from users.json (department via role)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    roles, users = data.get("roles", {}), data.get("users", {})
    return {name: {"role": role, "department": roles.get(role, {}).get("department", "")}
            for name, role in users.items()}


def _load_memory(path=MEMORY_PATH):
    """the seed shared memories (list of {tags, text}) from cocoshamem.seed.json."""
    return json.loads(path.read_text(encoding="utf-8")).get("memories", [])


PROFILES = _load_profiles()
MEMORY = _load_memory()


def handle(user, message):
    print(f"User -> GOVhence      | {user}: {message!r}")

    profile = PROFILES.get(user)
    if profile is None:
        print(f"GOVhence             | unknown user {user!r} -> refuse")
        return
    print(f"GOVhence             | profile (from store, never LLM) = {profile}")

    # GOVhence -> Classifier -> GOVhence
    cls = classifier.classify(message, profile)
    print(f"GOVhence -> Classifier | content_tags={cls.content_tags}  user_tags={cls.user_tags}")

    # GOVhence -> Judge -> GOVhence  (Judge decides on the CONTENT, not on access)
    d = judge.judge(message, cls.content_tags)
    print(f"GOVhence -> Judge      | read={d.read} write={d.write} candidate={d.candidate!r}")

    # GOVhence -> Bouncer (read path). GOVhence passes ONLY the content tags + the
    # username. It does NOT pass access rights — the Bouncer reads those directly
    # from users.json, so an LLM can never smuggle access via tags.
    lane = []
    if d.read:
        lane = bouncer.retrieve(cls.content_tags, user, MEMORY)
        print(f"GOVhence -> Bouncer    | MemoryLane = {[m['text'] for m in lane]}")
    else:
        print("GOVhence             | read not needed -> straight to Responder")

    # GOVhence -> Responder -> GOVhence
    answer = responder.respond(message, lane)
    print(f"GOVhence -> Responder  | {answer!r}")

    # GOVhence -> User  (answer goes out first)
    print(f"GOVhence -> User       | {answer}")

    # GOVhence -> Memoriser (write path) — AFTER the answer (async in real life)
    if d.write:
        ack = memoriser.memorise(d.candidate, cls.content_tags, MEMORY)
        print(f"GOVhence -> Memoriser  | (async) {ack}")


def main(argv):
    if len(argv) < 3:
        print('usage: python govhence.py <user> "<message>"')
        return 2
    handle(argv[1], " ".join(argv[2:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
