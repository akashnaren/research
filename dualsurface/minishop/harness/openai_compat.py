from __future__ import annotations

import json
from typing import Any

import httpx


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
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=120.0,
        )

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
        response = self.client.post("/chat/completions", json=body)
        try:
            payload = response.json()
        except json.JSONDecodeError:
            payload = {"error": response.text}
        if response.status_code != 200:
            raise RuntimeError(f"chat completions failed ({response.status_code}): {payload}")
        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return {
            "message": message,
            "usage": extract_usage(payload),
            "raw": payload,
        }
