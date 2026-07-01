"""
GOVhence pipeline agents — STUB backend (no open-weight model wired here yet).

The PRD's LLM roles (Classifier, Judge, Memoriser, Responder) as DETERMINISTIC, rule-based stubs
behind a small, stable interface. Swap any stub for a real open-weight model (via BasedAPIs) later
by re-implementing the same function signature -- the pipeline never changes.

SECURITY (absolute rule 2): NONE of these makes the ACCESS decision. Access is decided ONLY by
bouncer.check_item (`category in allowed`). These agents classify / judge / draft / respond. The
Memoriser assigns an access category at WRITE time (an LLM may LABEL at write time) -- that label
is then enforced by the deterministic gate on every future read.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# --- tag hygiene: canonical vocabulary, no near-duplicate proliferation (PRD step 12) ---
# Synonyms map alternative spellings onto ONE canonical tag so "week-end"/"weekend" don't both exist.
SYNONYMS = {"week-end": "weekend", "sandwiches": "food", "sandwich": "food"}


def normalise_tag(tag: str) -> str:
    """Canonical form: lowercased, trimmed, inner whitespace -> a single hyphen.
    So 'Location'/'location' -> 'location', and 'week end' -> 'week-end'."""
    t = "-".join(str(tag).strip().lower().split())
    return re.sub(r"-{2,}", "-", t).strip("-")


def canonical_tag(tag: str, known: set[str] | None = None) -> str:
    """Normalise, then fold known synonyms -- prefers reuse over a fresh near-duplicate."""
    t = SYNONYMS.get(normalise_tag(tag), normalise_tag(tag))
    return t


# small keyword -> tag map (the stub's 'understanding'); a real Classifier LLM replaces this.
KEYWORD_TAGS = {
    "sandwich": "food", "sandwiches": "food", "lunch": "food", "food": "food", "eat": "food",
    "coffee": "food", "deli": "food",
    "where": "location", "office": "office",
    "park": "parking", "parking": "parking",
    "hours": "hours", "open": "hours", "opening": "hours",
    "truck": "truck", "delivery": "delivery", "schedule": "schedule", "depart": "schedule",
    "revenue": "revenue", "finance": "finance", "financial": "finance", "margin": "finance",
    "contract": "contract", "legal": "legal", "penalty": "penalty",
}
# Place words -> a location tag AND a generic 'location' tag.
LOCATION_WORDS = {"london", "tokyo", "leeds", "here", "office"}
ROLE_DEPARTMENT = {"driver": "logistics", "exec": "leadership"}
_QUESTION_STARTS = ("where", "what", "who", "when", "why", "how", "which", "can", "could",
                    "is", "are", "do", "does", "should")
# Common words that shouldn't become content tags (keeps the salient-word pass from adding noise).
STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "with", "of", "to", "in", "on", "at", "was", "were", "be",
    "been", "you", "this", "that", "there", "here", "now", "not", "have", "has", "had", "your",
    "our", "new", "best", "good", "great", "free", "find", "get", "serves", "serve", "about", "from",
} | set(_QUESTION_STARTS)


@dataclass
class Classification:
    content_tags: tuple[str, ...]
    user_tags: tuple[str, ...]
    kind: str  # "query" or "statement"


@dataclass
class JudgeVerdict:
    is_write_candidate: bool
    reason: str


@dataclass
class MemoryDraft:
    text: str
    tags: tuple[str, ...]
    category: str


def _words(message: str) -> list[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z\-']+", str(message).lower())


def _dedupe(seq) -> tuple[str, ...]:
    return tuple(dict.fromkeys(t for t in seq if t))


def classify(message: str, role: str = "", known_tags: set[str] | None = None) -> Classification:
    """Classifier LLM (stub): message -> content tags + user tags + kind.
    Reuses `known_tags` (the existing vocabulary) so we don't proliferate near-duplicates."""
    known = {canonical_tag(t) for t in (known_tags or set())}
    words = _words(message)
    tags: list[str] = []
    for w in words:
        if w in KEYWORD_TAGS:
            tags.append(canonical_tag(KEYWORD_TAGS[w], known))
        if w in LOCATION_WORDS:
            tags.append(canonical_tag(w, known))
            tags.append(canonical_tag("location", known))
        # a salient content word becomes its own tag (so 'canteen', 'pho', ... are searchable)
        if len(w) >= 4 and w not in STOPWORDS:
            tags.append(canonical_tag(w, known))
    kind = "query" if (str(message).strip().endswith("?") or (words and words[0] in _QUESTION_STARTS)) \
        else "statement"
    user_tags = _dedupe(canonical_tag(x) for x in (role, ROLE_DEPARTMENT.get(role, "")) if x)
    return Classification(_dedupe(tags), user_tags, kind)


def judge_write_candidate(message: str, cls: Classification) -> JudgeVerdict:
    """Judge LLM (stub): is this worth adding to the corporate shared memory?
    A bare query with no asserted facts -> no. A statement that asserts reusable info -> yes."""
    if not cls.content_tags:
        return JudgeVerdict(False, "no recognisable topic -> not useful org-wide")
    if cls.kind == "query":
        return JudgeVerdict(False, "a query without new context -> limited org-wide usefulness")
    if len(_words(message)) < 3:
        return JudgeVerdict(False, "too short to be a useful memory")
    return JudgeVerdict(True, "a statement contributing reusable, org-relevant information")


# Sensitive topics get a tighter access category than corporate-'shared' (assigned at WRITE time).
_SENSITIVE = {"finance": "financials", "revenue": "financials", "margin": "financials",
              "legal": "legal", "contract": "legal", "penalty": "legal"}


def memorise(message: str, cls: Classification, known_tags: set[str] | None = None) -> MemoryDraft | None:
    """Memoriser (quality gate): distil a durable memory from the ORIGINAL message (no LLM
    expansion -- authenticity), refine tags (reuse existing), and assign the ACCESS category.
    Returns None if the candidate isn't quality memory content."""
    if cls.kind == "query":
        return None  # a bare question is not durable knowledge (defensive; the Judge also gates this)
    text = " ".join(str(message).split()).strip().rstrip(".!?") + "."
    if len(text) < 8 or not cls.content_tags:
        return None  # quality gate: reject thin content
    known = {canonical_tag(t) for t in (known_tags or set())}
    tags = _dedupe(canonical_tag(t, known) for t in cls.content_tags)
    category = "shared"
    for t in cls.content_tags:
        if t in _SENSITIVE:
            category = _SENSITIVE[t]
            break
    return MemoryDraft(text=text, tags=tags, category=category)


def respond(message: str, memories: list) -> str:
    """Responder LLM (stub): compose an answer from the user message + the MemoryLane memories.
    A real open-weight Responder replaces this; the stub proves the permitted memories reached it."""
    if memories:
        notes = "\n".join(f"  - {m.text}" for m in memories)
        return (f"Using what you're permitted to see in shared memory:\n{notes}\n"
                f"-> In answer to \"{str(message).strip()}\": see the relevant notes above.")
    return (f"I found no shared-memory notes you're permitted to see for \"{str(message).strip()}\". "
            f"Answering from your message alone.")
