from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

DEFAULT_SYNTHESIS_MODEL = "deepseek/deepseek-v4-flash-0731"
DEFAULT_ESCALATION_MODEL = "anthropic/haiku-4.5"


def synthesis_model() -> str:
    return os.environ.get("ARCHAEOLOGY_SYNTHESIS_MODEL", DEFAULT_SYNTHESIS_MODEL)


@dataclass(slots=True)
class Completion:
    content: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int


Poster = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]


def _default_poster(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    for attempt in range(2):
        response = httpx.post(url, json=payload, headers=headers, timeout=60.0)
        if response.status_code == 429 and attempt == 0:
            time.sleep(4.0)
            continue
        break
    if response.status_code >= 400:
        detail = response.text[:200]
        raise RuntimeError(f"OpenRouter error {response.status_code}: {detail}")
    result: dict[str, Any] = response.json()
    return result


def api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set; get one at https://openrouter.ai/keys")
    return key


def chat_completion(
    messages: list[dict[str, str]],
    model: str | None = None,
    max_tokens: int = 3000,
    temperature: float = 0.2,
    poster: Poster | None = None,
) -> Completion:
    chosen_model = model or synthesis_model()
    payload = {
        "model": chosen_model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    started = time.monotonic()
    attempts = 2
    raw: dict[str, Any] = {}
    for attempt in range(attempts):
        if poster is not None:
            raw = poster(OPENROUTER_URL, payload, {})
        else:
            headers = {
                "Authorization": f"Bearer {api_key()}",
                "Content-Type": "application/json",
            }
            raw = _default_poster(OPENROUTER_URL, payload, headers)
        choices = raw.get("choices") or []
        if choices and (choices[0]["message"].get("content") or "").strip():
            break
        if attempt == 0 and poster is None:
            time.sleep(2.0)
    latency_ms = int((time.monotonic() - started) * 1000)

    choices = raw.get("choices") or []
    content = choices[0]["message"]["content"] if choices else ""
    usage = raw.get("usage") or {}
    return Completion(
        content=(content or "").strip(),
        model=raw.get("model", chosen_model),
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        latency_ms=latency_ms,
    )
