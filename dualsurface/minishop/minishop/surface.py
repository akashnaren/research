from __future__ import annotations

from typing import Any

from minishop.catalog import in_stock_sizes, product_by_id

ACTION_NAMES = (
    "open_product",
    "set_size",
    "add_to_cart",
    "go_catalog",
    "go_checkout",
    "set_address",
    "pay",
)


def build_surface(session: dict[str, Any], catalog: list[dict[str, Any]]) -> dict[str, Any]:
    view = session.get("view") or "catalog"
    product = product_by_id(catalog, session["product_id"]) if session.get("product_id") else None
    available = in_stock_sizes(product) if product else []
    selected = session.get("selected_size")
    cart = list(session.get("cart") or [])
    address = session.get("address") or ""
    product_ids = [item["id"] for item in catalog]

    add_enabled = view == "product" and bool(product) and selected in available
    pay_enabled = view == "checkout" and bool(cart) and bool(address.strip())

    entities: dict[str, Any]
    if view == "product" and product is not None:
        entities = {
            "product": {
                "id": product["id"],
                "name": product["name"],
                "price": product["price"],
                "sizes_in_stock": available,
            },
            "cart": cart,
        }
    elif view == "checkout":
        entities = {"cart": cart, "address": address}
    elif view == "confirmation":
        orders = session.get("orders") or []
        entities = {"order": orders[-1] if orders else None, "cart": cart}
    else:
        entities = {
            "products": [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "price": item["price"],
                    "sizes_in_stock": in_stock_sizes(item),
                }
                for item in catalog
            ],
            "cart": cart,
        }

    return {
        "view": view,
        "state": {
            "product_id": session.get("product_id"),
            "selected_size": selected,
            "cart_count": len(cart),
            "address": address,
            "order_count": len(session.get("orders") or []),
        },
        "entities": entities,
        "affordances": [
            {
                "id": "open_product",
                "enabled": True,
                "input": _object_schema({"product_id": {"type": "string", "enum": product_ids}}, ["product_id"]),
            },
            {
                "id": "set_size",
                "enabled": view == "product" and bool(available),
                "input": _object_schema({"size": {"type": "string", "enum": available}}, ["size"]),
            },
            {
                "id": "add_to_cart",
                "enabled": add_enabled,
                "input": _object_schema({}),
            },
            {
                "id": "go_catalog",
                "enabled": True,
                "input": _object_schema({}),
            },
            {
                "id": "go_checkout",
                "enabled": True,
                "input": _object_schema({}),
            },
            {
                "id": "set_address",
                "enabled": view == "checkout",
                "input": _object_schema({"address": {"type": "string"}}, ["address"]),
            },
            {
                "id": "pay",
                "enabled": pay_enabled,
                "input": _object_schema({}),
            },
        ],
    }


def validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> None:
    required = schema.get("required") or []
    properties = schema.get("properties") or {}
    for key in required:
        if key not in arguments:
            raise ValueError(f"missing {key}")
    if schema.get("additionalProperties") is False:
        extra = set(arguments) - set(properties)
        if extra:
            raise ValueError(f"unexpected arguments {sorted(extra)}")
    for key, value in arguments.items():
        spec = properties.get(key)
        if spec is None:
            continue
        expected_type = spec.get("type")
        if expected_type == "string" and not isinstance(value, str):
            raise ValueError(f"{key} must be a string")
        allowed = spec.get("enum")
        if allowed is not None and value not in allowed:
            raise ValueError(f"{key}={value!r} is not allowed")


def _object_schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema
