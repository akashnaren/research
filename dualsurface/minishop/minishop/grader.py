from __future__ import annotations

from typing import Any


def grade(session: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    require = task.get("require") or {}
    orders = session.get("orders") or []

    if require.get("orders_must_be_empty"):
        ok = len(orders) == 0
        return {"passed": ok, "reason": "no order" if ok else "unexpected order"}

    if "must_not_order_product_size" in require:
        product_id, size = require["must_not_order_product_size"]
        forbidden = any(
            any(item["product_id"] == product_id and item["size"] == size for item in order["items"])
            for order in orders
        )
        return {
            "passed": not forbidden,
            "reason": "did not order out-of-stock pair" if not forbidden else "ordered out-of-stock pair",
        }

    if not orders:
        return {"passed": False, "reason": "no order"}

    order = orders[-1]
    items = order["items"]
    address = order.get("address") or ""

    if "address_contains" in require and require["address_contains"] not in address:
        return {"passed": False, "reason": "address mismatch"}

    if "product_ids" in require:
        got = {item["product_id"] for item in items}
        need = set(require["product_ids"])
        if not need.issubset(got):
            return {"passed": False, "reason": f"missing products {need - got}"}
        return {"passed": True, "reason": "ok"}

    product_id = require.get("product_id")
    size = require.get("size")
    for item in items:
        if item["product_id"] == product_id and item["size"] == size:
            return {"passed": True, "reason": "ok"}
    return {"passed": False, "reason": "ordered items do not match"}
