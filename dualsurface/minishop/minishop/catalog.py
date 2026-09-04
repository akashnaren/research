from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_catalog(path: Path | None = None) -> list[dict[str, Any]]:
    catalog_path = path or (DATA_DIR / "catalog.json")
    return json.loads(catalog_path.read_text())


def load_tasks(path: Path | None = None) -> list[dict[str, Any]]:
    tasks_path = path or (DATA_DIR / "tasks.json")
    return json.loads(tasks_path.read_text())


def product_by_id(catalog: list[dict[str, Any]], product_id: str) -> dict[str, Any] | None:
    for item in catalog:
        if item["id"] == product_id:
            return item
    return None


def in_stock_sizes(product: dict[str, Any]) -> list[str]:
    stock = product.get("stock") or {}
    return [size for size in product["sizes"] if int(stock.get(size, 0)) > 0]


def compact_products(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "price": item["price"],
            "sizes": list(item["sizes"]),
            "stock": dict(item["stock"]),
        }
        for item in catalog
    ]
