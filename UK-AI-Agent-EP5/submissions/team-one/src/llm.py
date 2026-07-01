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
import urllib.error
import urllib.request
from pathlib import Path


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


def _config():
    return (
        os.environ.get("LLM_BASE_URL", "https://api.mor.org/api/v1").rstrip("/"),
        os.environ.get("LLM_MODEL", "glm-5.2"),
        os.environ.get("LLM_API_KEY", ""),   # required; comes from .env
    )


def chat(system, user, *, json_mode=True, temperature=0.0, timeout=120):
    """Send a system + user prompt; return the assistant's text. Raises LLMError on failure.

    json_mode asks the server for a strict JSON object (a guardrail for parseable output).
    temperature 0 keeps tagging stable/repeatable.
    """
    base, model, key = _config()
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

    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError) as e:
        raise LLMError(f"LLM call failed: {e}") from e
