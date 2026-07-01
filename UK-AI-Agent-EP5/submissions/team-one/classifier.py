"""Classifier (walking-skeleton placeholder — NO real LLM yet).

Turns a message + profile into TWO separate things:
  - content_tags: what the message is ABOUT (relevance) — e.g. ["sandwich","london"]
  - user_tags:    role + department, taken STRAIGHT FROM THE PROFILE (context only)

Kept separate on purpose: content_tags drive relevance/retrieval; the user's ACCESS
is NOT decided from these tags — the Bouncer reads access directly from users.json.
A real open-weight model swaps in behind the same signature later.
"""
from dataclasses import dataclass

_STOP = {"the", "a", "an", "is", "are", "was", "were", "where", "what", "who", "when",
         "why", "how", "which", "can", "do", "does", "i", "to", "in", "of", "on", "at",
         "best", "no", "not", "we", "you", "it", "and", "or", "for", "my", "me"}


@dataclass
class Classification:
    content_tags: list   # relevance — what the message is about
    user_tags: list      # role + department (from the profile; context only, NOT access)


def classify(message, profile):
    """message + profile -> Classification(content_tags, user_tags)."""
    words = [w.strip("?.!,;:").lower() for w in str(message).split()]
    content = list(dict.fromkeys(w for w in words if w and w not in _STOP and len(w) >= 3))
    # user tags come DIRECTLY from the profile (never invented) — context, not access
    user_tags = [t for t in (profile.get("role", ""), profile.get("department", "")) if t]
    return Classification(content_tags=content, user_tags=user_tags)
