"""
GOVhence live pipeline (PRD.md) -- working-first scaffold.

Reuses the deterministic core: the BOUNCER is the access gate (= the PRD's DeterminExtractor);
memory.py resolves RBAC/ACL + revocation; audit.py logs every access decision. The LLM roles are
rule-based stubs in agents.py (swap for a real open-weight model later).

READ PATH (blocks the answer):
    verify user -> classify -> relevance pre-filter (tag intersection, NO LLM)
    -> bouncer access filter (AUDITED) -> MemoryLane -> Responder
WRITE PATH (side-track; here it runs after the answer is composed, so the read path never waits on
it -- true threading is a later increment):
    Judge write-candidate? -> Memoriser quality-gate -> append to the runtime CocoShaMem store
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import agents
import audit
import bouncer
import cli
import memory

SEED_PATH = Path(__file__).with_name("cocoshamem.seed.json")   # committed demo seed
STORE_PATH = Path(__file__).with_name("cocoshamem.json")       # runtime store (git-ignored)


def _ensure_store(store_path: Path, seed_path: Path) -> None:
    """The runtime store is seeded from the committed seed on first use, so no runtime artifact
    is ever committed (the seed is the only tracked copy)."""
    if not store_path.exists() and seed_path.exists():
        store_path.write_text(seed_path.read_text(encoding="utf-8"), encoding="utf-8")


def load_memories(store_path: Path = STORE_PATH, seed_path: Path = SEED_PATH) -> list:
    """CocoShaMem as a list of MemoryItem (reuses cli.load_items, which is fail-closed)."""
    _ensure_store(store_path, seed_path)
    src = store_path if store_path.exists() else seed_path
    return cli.load_items(src)


def known_tags(memories: list) -> set[str]:
    """The existing tag vocabulary (so agents reuse tags instead of proliferating near-duplicates)."""
    return {t for m in memories for t in m.tags}


def extract(user: str, message_tags, memories: list, allowed: set, revoked, log_path: Path) -> list:
    """The DeterminExtractor == the BOUNCER. Relevance PRE-filter (tag intersection, NO LLM), then
    the audited access filter -- a forbidden item is never returned even when it is relevant, and
    every access decision we make is logged (pre-filter, not post-filter)."""
    want = set(message_tags)
    candidates = [m for m in memories if want & set(m.tags)]
    return bouncer.retrieve(user, allowed, candidates, log_path=log_path, revoked_ids=revoked)


def memory_lane(memories: list) -> str:
    """The 'MemoryLane' preamble GOVhence prepends to the Responder's input."""
    if not memories:
        return "MemoryLane: no permitted memories matched."
    body = "\n".join(f"  - [{m.category}] {m.text}" for m in memories)
    return "MemoryLane -- relevant shared memories you may see:\n" + body


def _append_memory(store_path: Path, seed_path: Path, draft: "agents.MemoryDraft") -> str:
    """Append a new memory to the runtime store (atomic write). Returns the new id."""
    _ensure_store(store_path, seed_path)
    data = json.loads(store_path.read_text(encoding="utf-8")) if store_path.exists() else {"items": []}
    items = data.setdefault("items", [])
    new_id = f"mem-w{len(items) + 1:04d}"
    items.append({"id": new_id, "category": draft.category, "tags": list(draft.tags), "text": draft.text})
    tmp = store_path.with_name(store_path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, store_path)      # atomic on every OS
    return new_id


@dataclass
class Result:
    user: str
    allowed: list
    classification: object
    retrieved: list
    memory_lane: str
    answer: str
    verdict: object
    memorised: object   # MemoryDraft or None
    memorised_id: str   # "" if nothing written


def handle(user: str, message: str, *, store_path: Path = STORE_PATH, seed_path: Path = SEED_PATH,
           log_path: Path = audit.LOG_PATH, do_write: bool = True) -> Result:
    """Run one message end-to-end. Fail-closed: an unknown user / broken config raises
    memory.ConfigError (the caller refuses access)."""
    # (3) verify user + resolve RBAC/ACL -- load config ONCE and reuse it.
    config = memory.load_config()
    allowed = memory.allowed_categories_for_user(user, config)
    revoked = memory.revoked_ids()
    role = config["users"].get(user, "")

    memories = load_memories(store_path, seed_path)
    vocab = known_tags(memories)

    # (6-8) classify the message
    cls = agents.classify(message, role=role, known_tags=vocab)

    # (10 + 13) READ PATH: retrieve permitted, relevant memories -> MemoryLane -> Responder
    retrieved = extract(user, cls.content_tags, memories, allowed, revoked, log_path)
    lane = memory_lane(retrieved)
    answer = agents.respond(message, retrieved)

    # (9, 11-12, 16) WRITE PATH (side-track): judge -> memorise -> append
    verdict = agents.judge_write_candidate(message, cls)
    draft, new_id = None, ""
    if do_write and verdict.is_write_candidate:
        draft = agents.memorise(message, cls, known_tags=vocab)
        if draft is not None:
            new_id = _append_memory(store_path, seed_path, draft)
    return Result(user, sorted(allowed), cls, retrieved, lane, answer, verdict, draft, new_id)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="pipeline.py",
        description="GOVhence live pipeline: answer a user message using the memories they may see.")
    p.add_argument("user", help="username (e.g. bob, alice)")
    p.add_argument("message", help="the user's message, in quotes")
    p.add_argument("--no-write", action="store_true", help="skip the memory-write side-track")
    args = p.parse_args(argv)
    try:
        r = handle(args.user, args.message, do_write=not args.no_write)
    except memory.ConfigError as e:
        print(f"ACCESS DENIED -- {e}", file=sys.stderr)
        return 2
    print(f"User: {r.user}   allowed: {r.allowed}")
    print(f"Classified: kind={r.classification.kind}  tags={list(r.classification.content_tags)}  "
          f"user_tags={list(r.classification.user_tags)}")
    print("-" * 72)
    print(r.memory_lane)
    print("-" * 72)
    print(r.answer)
    print("-" * 72)
    verdict = "WRITE-CANDIDATE" if r.verdict.is_write_candidate else "no-write"
    print(f"Judge: {verdict} -- {r.verdict.reason}")
    if r.memorised is not None:
        print(f"Memorised -> {r.memorised_id} [{r.memorised.category}] "
              f"{r.memorised.text}  tags={list(r.memorised.tags)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
