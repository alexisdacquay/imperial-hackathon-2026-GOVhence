"""Judge (walking-skeleton placeholder — NO real LLM yet).

A PURE DECISION FUNCTION. Given message + tags it decides, and returns to GOVhence:
  - read?  should we check memory at all? (a bare "Hi" -> no)
  - write? is this worth remembering? and if so, the memory candidate.
It decides only; GOVhence does the routing.
"""
from dataclasses import dataclass


@dataclass
class Decision:
    read: bool
    write: bool
    candidate: str | None


_GREETINGS = {"hi", "hello", "hey", "yo", "thanks", "thank you"}
_QUESTION_STARTS = ("where", "what", "who", "when", "why", "how", "which",
                    "is", "are", "can", "do", "does", "should")


def judge(message, tags):
    """message + tags -> Decision(read, write, candidate)."""
    text = str(message).strip()
    low = text.lower()

    if low in _GREETINGS:
        return Decision(read=False, write=False, candidate=None)  # straight to Responder

    words = low.split()
    is_question = low.endswith("?") or (words and words[0] in _QUESTION_STARTS)

    # worth checking memory if it's a question or carries recognisable tags
    read = bool(is_question or tags)
    # worth remembering if it's a statement with some substance (not a question)
    write = (not is_question) and len(words) >= 3
    return Decision(read=read, write=write, candidate=(text if write else None))
