"""Classifier (walking-skeleton placeholder — NO real LLM yet).

Turns a message + profile into tags: content tags (from the message) + user tags
(role, department) taken STRAIGHT FROM THE PROFILE. A real open-weight model swaps
in here later behind the same signature.

Invariant (even in the skeleton): the user/access tags come from the profile,
never guessed by this component.
"""

_STOP = {"the", "a", "an", "is", "are", "was", "were", "where", "what", "who", "when",
         "why", "how", "which", "can", "do", "does", "i", "to", "in", "of", "on", "at",
         "best", "no", "not", "we", "you", "it", "and", "or", "for", "my", "me"}


def classify(message, profile):
    """message + profile -> list of tags (content tags first, then user tags)."""
    words = [w.strip("?.!,;:").lower() for w in str(message).split()]
    content = [w for w in words if w and w not in _STOP and len(w) >= 3]
    # user/access tags come DIRECTLY from the profile (never invented)
    user_tags = [t for t in (profile.get("role", ""), profile.get("department", "")) if t]
    # de-dupe, keep order
    return list(dict.fromkeys(content + user_tags))
