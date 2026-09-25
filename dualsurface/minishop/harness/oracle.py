"""Deterministic oracle LLM client for the C3/C4 control run.

This is a drop-in replacement for ``harness.openai_compat.OpenAICompat`` as
used by ``harness.model_loop.run_c3_c4``. It makes **no network call and is
never provider-billed**: instead of asking a model what to do, it replays the
hand-written scripted policy for one task (``harness.scripted.POLICIES``),
one action per ``chat()`` call. Its purpose is a *control condition* -- a
perfect agent -- and an end-to-end validation of the measurement apparatus
(loop -> HTTP -> traces -> report) before any paid model run.

Honesty notes (see also ``papers/agent-native-ui/research-plan.md``):

- The reported ``usage`` is **real but locally computed**, not provider usage.
  ``prompt_tokens`` is counted with ``tiktoken`` (``o200k_base``, the same
  reference tokenizer as ``harness/obs_cost.py``) over the exact ``messages``
  the loop passed to ``chat()``; ``completion_tokens`` over the returned
  content / tool-call JSON. Every usage dict is tagged ``"source":
  "local_tokenizer"`` and the model id is ``"oracle"`` so an oracle run can
  never be confused with a provider-billed one.
- Because only the ``messages`` are tokenized, the C3 tool schema (which the
  loop sends via the ``tools`` argument, not inside ``messages``) is **not**
  counted here, even though a real provider bills it. Oracle input-token
  counts are therefore a lower bound for C3 in particular; the deterministic
  ``harness/obs_cost.py`` baseline is the place that accounts for the schema.
- Scope is C3 and C4 only. C1 (screenshot) and C2 (accessibility tree) need
  pixel/element oracles and are intentionally out of scope here.
"""

from __future__ import annotations

import json
from typing import Any

from harness.tokens import encoder as get_encoder


class OracleClient:
    """Task-scoped, deterministic stand-in for ``OpenAICompat``.

    Construct one per (condition, task) run with that task's policy. It
    exposes the same ``chat(messages, *, tools=None, json_object=False)``
    interface, the same ``.model`` attribute, and returns the same shape
    (``{"message": {...}, "usage": {...}, "raw": {...}}``) as the real client.

    Dispatch mirrors how the loop calls the client:

    - C3 (flat tools): the loop passes ``tools=...``. We reply with a single
      ``tool_calls`` entry for the next policy step, and an empty
      ``tool_calls`` list (which the loop treats as "stop") once the policy
      is exhausted.
    - C4 (view document): the loop passes ``json_object=True`` and no tools.
      We reply with ``message.content`` = a JSON string
      ``{"name": <action>, "arguments": {...}}`` for the next step, and
      ``{"name": "done", "arguments": {}}`` once the policy is exhausted.

    The oracle advances exactly one policy step per ``chat()`` call.
    """

    def __init__(
        self,
        task_id: str,
        policy: list[tuple[str, dict[str, Any]]],
        *,
        model: str = "oracle",
        encoder: Any | None = None,
    ) -> None:
        self.model = model
        self.task_id = task_id
        self._policy = [(name, dict(arguments)) for name, arguments in policy]
        self._pos = 0
        self._enc = encoder if encoder is not None else get_encoder()

    def _next_step(self) -> tuple[str, dict[str, Any]] | None:
        """Pop the next policy step, or None if the policy is exhausted."""
        if self._pos >= len(self._policy):
            return None
        step = self._policy[self._pos]
        self._pos += 1
        return step

    def _count(self, text: str) -> int:
        return len(self._enc.encode(text))

    def _count_messages(self, messages: list[dict[str, Any]]) -> int:
        """Locally tokenize the exact messages the loop passed to ``chat()``.

        String content is tokenized directly; a list content (C1/C2 image
        blocks) is JSON-serialized first. This omits provider chat-template
        overhead and the C3 tool schema, so it is a faithful lower bound, not
        a provider bill.
        """
        total = 0
        for message in messages:
            role = message.get("role")
            if role:
                total += self._count(role)
            content = message.get("content")
            if isinstance(content, str):
                total += self._count(content)
            elif content is not None:
                total += self._count(json.dumps(content))
        return total

    def _usage(self, prompt_tokens: int, completion_text: str) -> dict[str, Any]:
        completion_tokens = self._count(completion_text)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cached_tokens": None,
            # No images in C3/C4; leave image tokens null like the real path.
            "image_tokens": None,
            "reasoning_tokens": None,
            # Marker so a reader (and report.py) can tell this is not a bill.
            "source": "local_tokenizer",
            "raw": {},
        }

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        json_object: bool = False,
    ) -> dict[str, Any]:
        prompt_tokens = self._count_messages(messages)
        step = self._next_step()

        if tools is not None:
            # C3 tool-calling path.
            if step is None:
                tool_calls: list[dict[str, Any]] = []
            else:
                name, arguments = step
                tool_calls = [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(arguments)},
                    }
                ]
            message = {"role": "assistant", "content": None, "tool_calls": tool_calls}
            completion_text = json.dumps(tool_calls)
        else:
            # C4 (and any json_object) path: a single JSON action object.
            if step is None:
                action: dict[str, Any] = {"name": "done", "arguments": {}}
            else:
                name, arguments = step
                action = {"name": name, "arguments": arguments}
            content = json.dumps(action)
            message = {"role": "assistant", "content": content}
            completion_text = content

        return {
            "message": message,
            "usage": self._usage(prompt_tokens, completion_text),
            "raw": {"oracle": True, "task_id": self.task_id, "policy_index": self._pos},
        }
