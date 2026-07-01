"""GOVhence — the SOLE orchestrator (walking-skeleton placeholder — NO real LLM yet).

BUILD TARGET #1 of PRD-2026-07-01.md: run the whole chain end-to-end with the
simplest possible components and NO security/audit burden, to prove the process
logic. Hub-and-spoke — everything routes through GOVhence, nothing bypasses it:

    User -> GOVhence -> Classifier -> GOVhence -> Judge -> GOVhence
         -> Bouncer (read) and/or Memoriser (write) -> Responder -> GOVhence -> User

Run:  python govhence.py bob "where is the best sandwich in London?"
      python govhence.py bob "No, not Tokyo, the office is in London"
      python govhence.py bob "Hi"
"""
import sys

import classifier
import judge
import bouncer
import memoriser
import responder

# --- placeholder stores (become the Profile Store + CocoShaMem later) ----------
PROFILES = {
    "bob":   {"role": "driver", "department": "logistics"},
    "alice": {"role": "exec",   "department": "leadership"},
}
MEMORY = [
    {"tags": ["sandwich", "london"], "text": "The deli on Carter Lane does great sandwiches."},
    {"tags": ["parking", "london"],  "text": "Visitor parking is on Friar Street."},
]


def handle(user, message):
    print(f"User -> GOVhence      | {user}: {message!r}")

    profile = PROFILES.get(user)
    if profile is None:
        print(f"GOVhence             | unknown user {user!r} -> refuse")
        return
    print(f"GOVhence             | profile (from store, never LLM) = {profile}")

    # GOVhence -> Classifier -> GOVhence
    tags = classifier.classify(message, profile)
    print(f"GOVhence -> Classifier | tags = {tags}")

    # GOVhence -> Judge -> GOVhence
    d = judge.judge(message, tags)
    print(f"GOVhence -> Judge      | read={d.read} write={d.write} candidate={d.candidate!r}")

    # GOVhence -> Bouncer (read path)
    lane = []
    if d.read:
        lane = bouncer.retrieve(tags, MEMORY)
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
        ack = memoriser.memorise(d.candidate, tags, MEMORY)
        print(f"GOVhence -> Memoriser  | (async) {ack}")


def main(argv):
    if len(argv) < 3:
        print('usage: python govhence.py <user> "<message>"')
        return 2
    handle(argv[1], " ".join(argv[2:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
