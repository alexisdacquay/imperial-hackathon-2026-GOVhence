"""testboard.py — an ASCII dashboard of the team-one tests + a live classification.

Shows, at a glance: which MODEL is actually wired, every test with pass/fail, and one
REAL classification (message + profile -> tags) from the live open-weight model.

Run:  ../.venv/bin/python testboard.py        (from team-one/)
"""
import re
import subprocess
import sys
from pathlib import Path

import classifier
import llm

HERE = Path(__file__).parent
PY = sys.executable
W = 62  # inner content width

G, R, Y, DIM, B, END = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m"


def _row(text, pad=W):
    return f"│ {text}{' ' * max(0, pad - _vlen(text))} │"


def _vlen(s):  # visible length (ignore ANSI escapes)
    return len(re.sub(r"\033\[[0-9;]*m", "", s))


def _top(title):
    t = f" {title} "
    return "┌─" + t + "─" * max(0, W - _vlen(t)) + "┐"


def _bot():
    return "└" + "─" * (W + 2) + "┘"


def _run(args):
    r = subprocess.run([PY, "-m", "pytest", *args, "-v", "--tb=line", "-p", "no:cacheprovider"],
                       cwd=HERE, capture_output=True, text=True)
    out = r.stdout + r.stderr
    tests = [(m.group(1), m.group(2))
             for line in out.splitlines()
             for m in [re.search(r"::(\S+)\s+(PASSED|FAILED|SKIPPED|ERROR)", line)] if m]
    return tests


def _pretty(name):
    return (name[5:] if name.startswith("test_") else name).replace("_", " ")


def _section(title, tests):
    icon = {"PASSED": f"{G}✓{END}", "FAILED": f"{R}✗{END}",
            "SKIPPED": f"{Y}○{END}", "ERROR": f"{R}✗{END}"}
    print(_top(title))
    for name, status in tests:
        print(_row(f"{icon.get(status, '?')} {_pretty(name)[:W-4]}"))
    print(_bot())


def main():
    base, model, key = llm._config()
    live_ok = True
    try:
        c = classifier.classify("where is the best sandwich in London?",
                                 {"role": "driver", "department": "logistics"},
                                 known_tags=["food", "london", "location", "parking", "schedule"])
    except Exception:
        live_ok = False
        c = None

    bouncer_tests = _run(["test_bouncer.py"])
    classifier_tests = _run(["test_classifier.py", "-k", "not live"])
    allt = bouncer_tests + classifier_tests
    passed = sum(1 for _, s in allt if s == "PASSED")
    failed = sum(1 for _, s in allt if s in ("FAILED", "ERROR"))

    # header
    print("╔" + "═" * (W + 2) + "╗")
    print(f"║ {B}GOVhence MEM-Ø · test board{END}{' ' * (W - 27)} ║")
    print("╠" + "═" * (W + 2) + "╣")
    glm_note = f"{Y}requested GLM5.2 — no key found; using local open-weight{END}"
    print(_row(f"{DIM}model {END}{model}", W).replace("│", "║"))
    print(_row(f"{DIM}base  {END}{base}", W).replace("│", "║"))
    print(_row(f"{DIM}key   {END}{key}", W).replace("│", "║"))
    print(_row(glm_note, W).replace("│", "║"))
    print("╚" + "═" * (W + 2) + "╝")
    print()

    _section("Bouncer · access read directly from users.json", bouncer_tests)
    _section("Classifier · LLM tagging (deterministic, fake LLM)", classifier_tests)

    print(_top("LIVE classification · real open-weight model"))
    if live_ok and c:
        print(_row(f"{DIM}message{END} where is the best sandwich in London?"))
        print(_row(f"{DIM}profile{END} driver / logistics"))
        print(_row(f"{G}content_tags{END} {c.content_tags}  {DIM}(LLM){END}"))
        print(_row(f"{G}user_tags   {END} {c.user_tags}  {DIM}(profile, not LLM){END}"))
    else:
        print(_row(f"{R}model unreachable — classifier fell back to rule-based{END}"))
    print(_bot())
    print()

    bar = f"{G}{'█' * passed}{END}{R}{'█' * failed}{END}"
    verdict = f"{G}ALL PASS{END}" if failed == 0 else f"{R}{failed} FAILED{END}"
    print(f"  RESULT  {bar}  {passed} passed · {failed} failed   {verdict}")


if __name__ == "__main__":
    main()
