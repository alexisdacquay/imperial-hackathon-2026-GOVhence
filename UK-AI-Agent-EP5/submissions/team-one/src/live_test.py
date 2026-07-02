"""Manual LIVE test console for GOVhence — real LLM calls (needs keys in .env).

Run it, then just type messages:

    .venv/bin/python src/live_test.py          (macOS/Linux, from team-one/)
    .venv\\Scripts\\python src\\live_test.py     (Windows)

The point: ask the SAME question as different ben-* users (one per clearance
level) and watch the MemoryLane change — that's the access control working.
Suggested tour:
    /user ben-staff     ->  "what does the Acme contract say about penalties?"   (denied)
    /user ben-legal     ->  same question                                        (sees it)
    /user ben-auditor   ->  "how did the Acme dispute settle?"   (ONLY user who can see
                             the dual-label financials+legal memory)
Teach something as ben-driver, /user to another driver-clearance user, ask it back
(persists across restarts via the runtime store).

Commands:  /users            list every user + clearances
           /user <name>      switch who you are testing as
           /quit             leave (Ctrl-C / Ctrl-D also work)
Anything else is sent through the real pipeline: Classifier -> Judge ->
Bouncer/Memoriser -> Responder, with the full hop-by-hop trace printed.
"""
import bouncer
import govhence


def _show_users():
    print()
    print(f"{'user':12} | {'role':8} | {'department':10} | clearances")
    print("-" * 66)
    for name, prof in sorted(govhence.PROFILES.items()):
        clear = ", ".join(sorted(bouncer.clearances_for(name)))
        print(f"{name:12} | {prof['role']:8} | {prof['department']:10} | {clear}")
    print()


def main():
    print(__doc__)
    _show_users()
    user = "ben-driver"
    print(f"Current user: {user}   (switch with /user <name>)")
    while True:
        try:
            msg = input(f"\n{user}> ").strip()
        except (EOFError, KeyboardInterrupt):    # Ctrl-D / Ctrl-C: leave quietly
            print()
            return 0
        if not msg:
            continue
        if msg in ("/quit", "/q", "/exit"):
            return 0
        if msg == "/users":
            _show_users()
            continue
        if msg.startswith("/user"):
            parts = msg.split(maxsplit=1)
            candidate = parts[1].strip() if len(parts) == 2 else ""
            if candidate in govhence.PROFILES:
                user = candidate
                print(f"Now testing as: {user}   "
                      f"(clearances: {sorted(bouncer.clearances_for(user))})")
            else:
                print(f"unknown user {candidate!r} — /users lists everyone")
            continue
        print("-" * 72)
        govhence.handle(user, msg)               # the real pipeline, full trace
        print("-" * 72)


if __name__ == "__main__":
    raise SystemExit(main())
