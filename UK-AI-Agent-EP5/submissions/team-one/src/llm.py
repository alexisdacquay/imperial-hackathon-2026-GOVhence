"""Minimal LLM client (stdlib only) for an OpenAI-compatible chat endpoint.

Open-weight ONLY (never a closed model in the product loop). Talks to mor.org
(OpenAI-compatible) by default; the API key comes from a local gitignored .env.
One key covers every model on mor.org. Override via env / .env — no code change:

  LLM_BASE_URL   (default https://api.mor.org/api/v1)
  LLM_MODEL      (default glm-5.2 — any OPEN-WEIGHT model on mor.org)
  LLM_API_KEY    (required — put it in .env)

No third-party dependency: uses urllib from the standard library.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

# Open-weight endpoints (esp. mor.org) intermittently return an EMPTY completion
# for a valid request — observed ~2-in-3 on glm-5.2 for a normal prompt. That is a
# transient server hiccup, not a real refusal, so we retry a few times with a short
# backoff before giving up. Retrying also covers transient network/HTTP errors.
_MAX_ATTEMPTS = 4
_BACKOFF_SECONDS = 0.6


def _load_dotenv():
    """Load KEY=VALUE lines from a local, gitignored `.env` (next to this file) into the
    environment. Keeps secrets out of code/git. Precedence: the REAL environment always
    wins over `.env`; within `.env`, the LAST occurrence of a key wins (so appending a
    new block cleanly overrides an earlier one instead of being silently ignored)."""
    env_file = Path(__file__).parent.parent / ".env"   # project root (team-one/)
    if not env_file.exists():
        return
    values = {}
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")   # last occurrence wins
    for key, value in values.items():
        os.environ.setdefault(key, value)                            # real env still wins


_load_dotenv()


class LLMError(Exception):
    """The LLM call failed (network, HTTP, timeout, or malformed response).

    Callers must catch this and FALL BACK safely — the pipeline never crashes just
    because a model is slow or offline.
    """


# Some open-weight models wrap JSON output in Markdown code fences (```json ... ```)
# even in json_mode. Strip a leading/trailing fence before parsing.
_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_json(text):
    """Parse a JSON object from an LLM reply, tolerating ```json ... ``` (or ``` ... ```)
    fences some models add. Raises ValueError (json.JSONDecodeError) if it still isn't valid
    JSON — callers already catch that and fall back safely."""
    return json.loads(_JSON_FENCE.sub("", str(text).strip()))


def _config(component=None):
    """Resolve (base_url, model, api_key). A component (e.g. 'JUDGE', 'CLASSIFIER') reads its
    own `<COMPONENT>_LLM_*` vars first, and falls back to the generic `LLM_*` vars — so each
    role can run a different open-weight model (a fast one for tagging, a clever one for the
    Judge) with no code change, just .env."""
    def pick(name, default):
        if component:
            specific = os.environ.get(f"{component}_{name}")
            if specific:
                return specific
        return os.environ.get(name, default)
    return (
        pick("LLM_BASE_URL", "https://api.mor.org/api/v1").rstrip("/"),
        pick("LLM_MODEL", "glm-5.2"),
        pick("LLM_API_KEY", ""),   # required; comes from .env
    )


def chat(system, user, *, component=None, json_mode=True, temperature=0.0, timeout=120,
         attempts=_MAX_ATTEMPTS, _sleep=time.sleep):
    """Send a system + user prompt; return the assistant's text. Raises LLMError on failure.

    component routes to that role's model (per-component env, generic fallback).
    json_mode asks the server for a strict JSON object (a guardrail for parseable output).
    temperature 0 keeps decisions stable/repeatable.

    Retries transient failures — a network/HTTP error OR an EMPTY completion (a known
    intermittent behaviour of some open-weight endpoints) — up to `attempts` times with
    a short linear backoff, then raises the last LLMError. An empty reply is transient,
    NOT a refusal, so retrying it (rather than failing the message) is what keeps the
    pipeline usable on a flaky endpoint.
    """
    base, model, key = _config(component)
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    data_bytes = json.dumps(body).encode("utf-8")

    last_err = None
    for attempt in range(max(1, attempts)):
        try:
            req = urllib.request.Request(
                f"{base}/chat/completions",
                data=data_bytes,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            if content and content.strip():
                return content
            last_err = LLMError(f"empty completion from {model!r} (attempt {attempt + 1})")
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError) as e:
            last_err = LLMError(f"LLM call failed: {e}")
        if attempt < attempts - 1:
            _sleep(_BACKOFF_SECONDS * (attempt + 1))
    raise last_err
