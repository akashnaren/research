from __future__ import annotations

import json

from harness.oracle import OracleClient

POLICY = [
    ("open_product", {"product_id": "tee-navy"}),
    ("set_size", {"size": "M"}),
    ("add_to_cart", {}),
]

MESSAGES = [
    {"role": "system", "content": "You are completing one shopping task."},
    {"role": "user", "content": "Task: buy a tee.\n\nCurrent observation only."},
]


def _oracle() -> OracleClient:
    return OracleClient("t01", POLICY)


def test_model_alias_is_oracle():
    assert _oracle().model == "oracle"


def test_c4_emits_json_content_and_advances_then_done():
    oracle = _oracle()
    seen = []
    for expected_name, expected_args in POLICY:
        result = oracle.chat(MESSAGES, json_object=True)
        message = result["message"]
        # C4 uses message.content (a JSON string), never tool_calls.
        assert "tool_calls" not in message
        action = json.loads(message["content"])
        assert action == {"name": expected_name, "arguments": expected_args}
        seen.append(action["name"])
    assert seen == [name for name, _ in POLICY]

    # Once the policy is exhausted, C4 returns the done action.
    exhausted = oracle.chat(MESSAGES, json_object=True)
    assert json.loads(exhausted["message"]["content"]) == {"name": "done", "arguments": {}}


def test_c3_emits_tool_calls_and_advances_then_stops():
    oracle = _oracle()
    for expected_name, expected_args in POLICY:
        result = oracle.chat(MESSAGES, tools=[{"type": "function"}])
        calls = result["message"]["tool_calls"]
        assert len(calls) == 1
        call = calls[0]
        assert call["id"] == "call_1"
        assert call["type"] == "function"
        assert call["function"]["name"] == expected_name
        # Arguments are a JSON string, as the real OpenAI tool-call shape.
        assert json.loads(call["function"]["arguments"]) == expected_args

    # Once the policy is exhausted, C3 returns empty tool_calls (loop = stop).
    stopped = oracle.chat(MESSAGES, tools=[{"type": "function"}])
    assert stopped["message"]["tool_calls"] == []


def test_usage_is_locally_tokenized_and_positive():
    oracle = _oracle()
    result = oracle.chat(MESSAGES, json_object=True)
    usage = result["usage"]
    assert usage["source"] == "local_tokenizer"
    assert usage["prompt_tokens"] > 0
    assert usage["completion_tokens"] > 0
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
    # No images in C3/C4: image tokens stay null like the real client's path.
    assert usage["image_tokens"] is None


def test_prompt_tokens_track_message_size():
    oracle = _oracle()
    short = oracle.chat([{"role": "user", "content": "hi"}], json_object=True)
    long = _oracle().chat(
        [{"role": "user", "content": "a much longer prompt " * 50}], json_object=True
    )
    assert long["usage"]["prompt_tokens"] > short["usage"]["prompt_tokens"]


def test_raw_marks_oracle_and_position():
    oracle = _oracle()
    result = oracle.chat(MESSAGES, json_object=True)
    assert result["raw"]["oracle"] is True
    assert result["raw"]["task_id"] == "t01"
    assert result["raw"]["policy_index"] == 1
