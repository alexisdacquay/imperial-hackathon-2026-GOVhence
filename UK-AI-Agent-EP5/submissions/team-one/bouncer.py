"""Bouncer (FRESH walking-skeleton version — script, NO LLM).

Minimal tag matcher: returns the memories whose tags overlap the query tags.
NO security, NO RBAC/ACL, NO audit yet — that is the whole point of the skeleton
(prove the chain/logic first). The returned list is the "MemoryLane".

The mature, tamper-evident, fail-closed, RBAC/ACL bouncer is preserved in
`bouncer_v0.1.py` and snaps back into THIS step later (its `check_item` /
`retrieve` are drop-in) once the chain is proven.
"""


def retrieve(tags, memory):
    """tags + the memory store -> list of matching memories (the MemoryLane)."""
    want = set(tags)
    return [m for m in memory if want & set(m.get("tags", []))]
