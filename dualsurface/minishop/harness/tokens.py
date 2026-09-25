"""Local token counts. Same reference tokenizer for the oracle and obs_cost."""

from __future__ import annotations

import json
from typing import Any


def encoder():
    import tiktoken

    try:
        return tiktoken.get_encoding("o200k_base")
    except Exception:  # pragma: no cover - environment dependent
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(enc, obj: Any) -> int:
    text = obj if isinstance(obj, str) else json.dumps(obj)
    return len(enc.encode(text))
