"""Memoriser (walking-skeleton placeholder — NO real LLM yet).

Writes an approved memory candidate into the store, reusing the given tags. Returns
a short acknowledgment. No LLM expansion (authenticity comes from the message); a
real open-weight model swaps in behind the same signature later.
"""


def memorise(candidate, tags, memory):
    """candidate + tags + the memory store -> ack string (appends to the store)."""
    item = {"tags": list(dict.fromkeys(tags)), "text": str(candidate)}
    memory.append(item)
    return f"stored {item['text']!r} with tags {item['tags']}"
