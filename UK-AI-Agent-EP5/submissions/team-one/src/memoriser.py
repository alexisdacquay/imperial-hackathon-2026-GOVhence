"""Memoriser (walking-skeleton placeholder — NO real LLM yet).

Writes an approved memory candidate into the store, reusing the given topics.
Returns a short acknowledgment. No LLM expansion (authenticity comes from the
message); a real open-weight model swaps in behind the same signature later.
"""


def memorise(candidate, topics, memory, labels=("shared",)):
    """candidate + topics + the memory store -> ack string (appends to the store).

    Assigns the memory's security `labels` at write time (skeleton default:
    ["shared"], the least-sensitive). Real write-time classification — choosing
    labels from the writer's context — comes later; the Bouncer then requires a
    reader's clearances to cover ALL of these labels on every future read.
    """
    item = {"labels": list(labels), "topics": list(dict.fromkeys(topics)),
            "text": str(candidate)}
    memory.append(item)
    return f"stored {item['text']!r} {item['labels']} with topics {item['topics']}"
