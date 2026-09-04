from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_catalog(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text())


def product_by_id(catalog: list[dict[str, Any]], product_id: str) -> dict[str, Any] | None:
    for item in catalog:
        if item["id"] == product_id:
            return item
    return None
