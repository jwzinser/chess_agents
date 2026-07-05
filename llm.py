"""
Shared LLM call helper for the chess agents demo.

Backend is chosen via the LLM_BACKEND env var:
  - "anthropic" (default): Claude, via the Anthropic API. Needs ANTHROPIC_API_KEY.
  - "ollama": a local open-weight model served by Ollama (https://ollama.com).
              Needs `ollama serve` running and the model pulled, e.g.:
                  ollama pull qwen2.5-coder:3b

server.py sets LLM_BACKEND=ollama by default so the chess app runs fully
local out of the box.
"""

import json
import os
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

# Falls back to the interview_prep-level .env if ANTHROPIC_API_KEY isn't
# already set in the environment.
load_dotenv(Path(__file__).parent.parent / ".env")

BACKEND = os.environ.get("LLM_BACKEND", "anthropic")

ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:3b")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

if BACKEND == "anthropic":
    import anthropic
    _client = anthropic.Anthropic()


def _call_anthropic(system: str, user: str, max_tokens: int) -> str:
    resp = _client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


def _call_ollama(system: str, user: str, max_tokens: int) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"num_predict": max_tokens},
    }
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read())
    return body["message"]["content"]


def call_llm(system: str, user: str, max_tokens: int = 1024) -> str:
    if BACKEND == "ollama":
        return _call_ollama(system, user, max_tokens)
    return _call_anthropic(system, user, max_tokens)
