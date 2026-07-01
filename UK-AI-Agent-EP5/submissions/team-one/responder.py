"""Responder (walking-skeleton placeholder — NO real LLM yet).

Given the message + MemoryLane (the memories the Bouncer allowed through), produces
the final response. A real open-weight model swaps in behind the same signature.
"""


def respond(message, memorylane):
    """message + MemoryLane -> response string."""
    if memorylane:
        notes = "; ".join(m["text"] for m in memorylane)
        return f"Re: {message!r} — from what I remember: {notes}"
    return f"Re: {message!r} — nothing in memory about that yet."
