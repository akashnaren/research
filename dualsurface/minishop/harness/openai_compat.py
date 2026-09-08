from __future__ import annotations

import json
import time
from typing import Any, Callable

import httpx

# Status codes worth retrying: provider rate limits (429) and transient
# server-side failures (500/502/503/504). Retrying is safe here because the
# request is idempotent at temperature 0 and no partial state is committed.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def extract_usage(payload: dict[str, Any]) -> dict[str, Any]:
    usage = payload.get("usage") or {}
    details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
    completion_details = usage.get("completion_tokens_details") or {}
    image_tokens = details.get("image_tokens")
    if image_tokens is None:
        image_tokens = usage.get("image_tokens")
    return {
        "prompt_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
        "completion_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cached_tokens": details.get("cached_tokens"),
        "image_tokens": image_tokens,
        "reasoning_tokens": completion_details.get("reasoning_tokens"),
        "raw": usage,
    }


class OpenAICompat:
    def __init__(
        self,
        api_key: str | Callable[[], str],
        base_url: str,
        model: str,
        *,
        max_retries: int = 5,
        backoff_base: float = 4.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        # Vertex access tokens expire after about an hour, so `api_key` may
        # be a callable that is invoked fresh on every request instead of a
        # fixed string. A plain string (e.g. OPENAI_API_KEY) still works.
        self._api_key = api_key
        # Transient 429/5xx responses are retried with exponential backoff so a
        # single rate-limit blip does not abort an entire condition's sweep.
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = sleep
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"Content-Type": "application/json"},
            timeout=120.0,
        )

    def _token(self) -> str:
        if callable(self._api_key):
            return self._api_key()
        return self._api_key

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        json_object: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if json_object:
            body["response_format"] = {"type": "json_object"}
        payload: Any = None
        response = None
        for attempt in range(self._max_retries + 1):
            headers = {"Authorization": f"Bearer {self._token()}"}
            response = self.client.post("/chat/completions", json=body, headers=headers)
            try:
                payload = response.json()
            except json.JSONDecodeError:
                payload = {"error": response.text}
            if response.status_code == 200:
                break
            if response.status_code in RETRYABLE_STATUS and attempt < self._max_retries:
                # Exponential backoff: 4s, 8s, 16s, ... capped at ~60s.
                self._sleep(min(self._backoff_base * (2 ** attempt), 60.0))
                continue
            raise RuntimeError(f"chat completions failed ({response.status_code}): {payload}")
        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return {
            "message": message,
            "usage": extract_usage(payload),
            "raw": payload,
        }
