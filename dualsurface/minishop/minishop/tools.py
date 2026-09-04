from __future__ import annotations

from typing import Any


def tool_schemas() -> list[dict[str, Any]]:
    """OpenAI-style function tools for C3. Same grain as C4, plus list_products."""
    return [
        _fn(
            "list_products",
            "List catalog products: id, name, price, sizes, and stock. Does not change the view.",
            {},
        ),
        _fn(
            "open_product",
            "Open a product page by product id from list_products.",
            {"product_id": {"type": "string", "description": "Catalog product id"}},
            ["product_id"],
        ),
        _fn(
            "set_size",
            "Select a size on the open product. Size letters such as S, M, L, or OS.",
            {"size": {"type": "string", "description": "Size code"}},
            ["size"],
        ),
        _fn("add_to_cart", "Add the open product and selected size to the cart.", {}),
        _fn("go_catalog", "Go to the catalog.", {}),
        _fn("go_checkout", "Go to checkout.", {}),
        _fn(
            "set_address",
            "Set the shipping address. Requires checkout.",
            {"address": {"type": "string", "description": "Full shipping address"}},
            ["address"],
        ),
        _fn("pay", "Place the order. Requires a non-empty cart and an address on checkout.", {}),
    ]


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    parameters: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        parameters["required"] = required
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": parameters},
    }
