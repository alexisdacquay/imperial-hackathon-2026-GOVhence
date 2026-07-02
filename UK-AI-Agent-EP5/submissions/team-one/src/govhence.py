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
import llm
import memoriser
import responder

# --- data stores: loaded from JSON, never hardcoded in the script ---------------
_DATA = Path(__file__).parent.parent / "data"  # sibling of src/
USERS_PATH = _DATA / "users.json"              # the user base / profile store


def _load_profiles(path=USERS_PATH):
    """name -> {role, department}, resolved from users.json (department via role)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    roles, users = data.get("roles", {}), data.get("users", {})
    return {name: {"role": role, "department": roles.get(role, {}).get("department", "")}
            for name, role in users.items()}


PROFILES = _load_profiles()
# CocoShaMem, read via the Bouncer's loader (runtime store if the Memoriser has
# written one, else the committed seed). GOVhence only READS; the Memoriser writes.
MEMORY = bouncer.load_memories()


def handle(user, message):
    print(f"User -> GOVhence      | {user}: {message!r}")

    profile = PROFILES.get(user)
    if profile is None:
        print(f"GOVhence             | unknown user {user!r} -> refuse")
        return
    print(f"GOVhence             | profile (from store, never LLM) = {profile}")

    # GOVhence -> Classifier -> GOVhence  (LLM-backed). Scope the reusable topic vocabulary
    # to what THIS user may see, so we never feed the model topics of memories they can't
    # access (clearance-scoped known topics; the Bouncer still independently enforces retrieval).
    clearances = bouncer.clearances_for(user)
    known = sorted({t for m in bouncer.filter_visible(MEMORY, clearances)
                    for t in m.get("topics", [])})
    cls = classifier.classify(message, profile, known_tags=known)
    print(f"GOVhence <- Classifier | content_tags={cls.content_tags}  user_tags={cls.user_tags}")

    # GOVhence -> Judge -> GOVhence  (Judge decides on the CONTENT, not on access).
    # No silent fallback: if the Judge LLM is down, refuse the message loudly —
    # this product has no offline backup, and faking a judgement would be worse.
    try:
        d = judge.judge(message, cls.content_tags)
    except llm.LLMError as e:
        print(f"GOVhence             | Judge unavailable ({e}) -> refuse, no silent fallback")
        print("GOVhence -> User       | Sorry — I can't handle messages right now; please try again shortly.")
        return
    print(f"GOVhence <- Judge      | read={d.read} write={d.write} candidate={d.candidate!r}")

    # GOVhence -> Bouncer (read path). GOVhence passes ONLY the topics + the
    # username. It does NOT pass access rights — the Bouncer reads clearances
    # directly from users.json, so an LLM can never smuggle access via topics.
    lane = []
    if d.read:
        lane = bouncer.retrieve(cls.content_tags, user, MEMORY)
        print(f"GOVhence <- Bouncer    | MemoryLane = {[m['text'] for m in lane]}")
    else:
        print("GOVhence             | read not needed -> straight to Responder")

    # GOVhence -> Responder -> GOVhence
    answer = responder.respond(message, lane)
    print(f"GOVhence <- Responder  | {answer!r}")

    # GOVhence -> User  (answer goes out first)
    print(f"GOVhence -> User       | {answer}")

    # GOVhence -> Memoriser (write path) — AFTER the answer (async in real life).
    # Passes the USERNAME only: the Memoriser reads the writer's clearances itself
    # (trusted path), labels the candidate, and fails closed if it cannot.
    if d.write:
        ack = memoriser.memorise(d.candidate, cls.content_tags, MEMORY, user)
        print(f"GOVhence <- Memoriser  | (async) {ack}")


def main(argv):
    if len(argv) < 3:
        print('usage: python govhence.py <user> "<message>"')
        return 2
    handle(argv[1], " ".join(argv[2:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
