from __future__ import annotations

from typing import Any

import pytest

from harness.openai_compat import OpenAICompat, extract_usage


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    """Returns a queued sequence of responses for successive POSTs."""

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = responses
        self.calls = 0

    def post(self, *_args: Any, **_kwargs: Any) -> _FakeResponse:
        response = self._responses[self.calls]
        self.calls += 1
        return response


_OK = {"choices": [{"message": {"content": "{}"}}], "usage": {"prompt_tokens": 3}}


def _client(responses: list[_FakeResponse]) -> tuple[OpenAICompat, list[float]]:
    slept: list[float] = []
    llm = OpenAICompat("k", "http://x", "m", backoff_base=0.01, sleep=slept.append)
    llm.client = _FakeClient(responses)  # type: ignore[assignment]
    return llm, slept


def test_chat_retries_on_429_then_succeeds():
    llm, slept = _client(
        [
            _FakeResponse(429, {"error": "rate"}),
            _FakeResponse(429, {"error": "rate"}),
            _FakeResponse(200, _OK),
        ]
    )
    result = llm.chat([{"role": "user", "content": "hi"}])
    assert result["message"]["content"] == "{}"
    assert llm.client.calls == 3  # type: ignore[attr-defined]
    assert len(slept) == 2  # two backoff sleeps before the success


def test_chat_gives_up_after_max_retries():
    responses = [_FakeResponse(429, {"error": "rate"}) for _ in range(10)]
    llm, _ = _client(responses)
    llm._max_retries = 3
    with pytest.raises(RuntimeError, match="429"):
        llm.chat([{"role": "user", "content": "hi"}])
    assert llm.client.calls == 4  # initial + 3 retries  # type: ignore[attr-defined]


def test_chat_does_not_retry_on_400():
    llm, slept = _client([_FakeResponse(400, {"error": "bad"})])
    with pytest.raises(RuntimeError, match="400"):
        llm.chat([{"role": "user", "content": "hi"}])
    assert llm.client.calls == 1  # type: ignore[attr-defined]
    assert slept == []


def test_extract_usage_reads_image_tokens_when_present():
    usage = extract_usage({"usage": {"prompt_tokens": 100, "image_tokens": 40}})
    assert usage["prompt_tokens"] == 100
    assert usage["image_tokens"] == 40
