from __future__ import annotations

import copy
import uuid
from typing import Any


class Store:
    """In-memory sessions. Human UI, tools, and the view document share this."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}

    def new_session(self) -> str:
        session_id = uuid.uuid4().hex
        self._sessions[session_id] = {
            "view": "catalog",
            "product_id": None,
            "selected_size": None,
            "cart": [],
            "address": "",
            "orders": [],
        }
        return session_id

    def get(self, session_id: str) -> dict[str, Any]:
        if session_id not in self._sessions:
            raise KeyError(session_id)
        return self._sessions[session_id]

    def snapshot(self, session_id: str) -> dict[str, Any]:
        return copy.deepcopy(self.get(session_id))
