"""Memoriser (walking-skeleton placeholder — NO real LLM yet).

Writes an approved memory candidate into the store, reusing the given tags. Returns
a short acknowledgment. No LLM expansion (authenticity comes from the message); a
real open-weight model swaps in behind the same signature later.
"""


def memorise(candidate, tags, memory, category="shared"):
    """candidate + tags + the memory store -> ack string (appends to the store).

    Assigns an access `category` at write time (skeleton default: "shared", the
    least-sensitive). A real Memoriser would classify sensitivity here; the Bouncer
    then enforces that category on every future read.
    """
    item = {"category": category, "tags": list(dict.fromkeys(tags)), "text": str(candidate)}
    memory.append(item)
    return f"stored {item['text']!r} [{category}] with tags {item['tags']}"
