"""Minimal LLM client (stdlib only) for an OpenAI-compatible chat endpoint.

Open-weight ONLY (never a closed model in the product loop). Defaults to a LOCAL
open-weight model via ollama; point it at BasedAPIs (or any OpenAI-compatible
open-weight endpoint) by setting the env vars — no code change:

  LLM_BASE_URL   (default http://localhost:11434/v1)
  LLM_MODEL      (default qwen3.6:latest)
  LLM_API_KEY    (default "ollama" — a local server ignores it)

No third-party dependency: uses urllib from the standard library.
"""
import json
import os
import urllib.error
import urllib.request


class LLMError(Exception):
    """The LLM call failed (network, HTTP, timeout, or malformed response).

    Callers must catch this and FALL BACK safely — the pipeline never crashes just
    because a model is slow or offline.
    """


def _config():
    return (
        os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/"),
        os.environ.get("LLM_MODEL", "qwen3.6:latest"),
        os.environ.get("LLM_API_KEY", "ollama"),
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
