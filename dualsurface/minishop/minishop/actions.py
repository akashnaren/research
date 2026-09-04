from __future__ import annotations

from typing import Any

from minishop.catalog import compact_products, in_stock_sizes, product_by_id
from minishop.surface import ACTION_NAMES, build_surface, validate_arguments


class IllegalAction(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def apply_action(
    store: Any,
    catalog: list[dict[str, Any]],
    session_id: str,
    name: str,
    arguments: dict[str, Any] | None,
    *,
    enforce_surface: bool,
) -> dict[str, Any]:
    session = store.get(session_id)
    arguments = arguments or {}
    if not isinstance(arguments, dict):
        raise IllegalAction("arguments must be an object")

    if name == "list_products":
        if enforce_surface:
            raise IllegalAction("list_products is not available on the view-document condition")
        return {"status": "ok", "products": compact_products(catalog)}

    if name not in ACTION_NAMES:
        raise IllegalAction(f"unknown action {name!r}")

    if enforce_surface:
        surface = build_surface(session, catalog)
        affordance = next((item for item in surface["affordances"] if item["id"] == name), None)
        if affordance is None:
            raise IllegalAction(f"action {name} is not in the current view")
        if not affordance["enabled"]:
            raise IllegalAction(f"action {name} is disabled")
        try:
            validate_arguments(affordance["input"], arguments)
        except ValueError as exc:
            raise IllegalAction(str(exc)) from exc

    if name == "open_product":
        _open_product(session, catalog, arguments)
    elif name == "set_size":
        _set_size(session, catalog, arguments)
    elif name == "add_to_cart":
        _add_to_cart(session, catalog)
    elif name == "go_catalog":
        session["view"] = "catalog"
        session["product_id"] = None
        session["selected_size"] = None
    elif name == "go_checkout":
        session["view"] = "checkout"
        session["product_id"] = None
        session["selected_size"] = None
    elif name == "set_address":
        _set_address(session, arguments)
    elif name == "pay":
        _pay(session)
    else:
        raise IllegalAction(f"unknown action {name!r}")

    return {
        "status": "ok",
        "view": session["view"],
        "selected_size": session.get("selected_size"),
        "cart_count": len(session.get("cart") or []),
    }


def _open_product(session: dict[str, Any], catalog: list[dict[str, Any]], arguments: dict[str, Any]) -> None:
    product_id = arguments.get("product_id")
    if not isinstance(product_id, str) or not product_id:
        raise IllegalAction("product_id is required")
    product = product_by_id(catalog, product_id)
    if product is None:
        raise IllegalAction(f"unknown product {product_id!r}")
    session["view"] = "product"
    session["product_id"] = product_id
    session["selected_size"] = None


def _set_size(session: dict[str, Any], catalog: list[dict[str, Any]], arguments: dict[str, Any]) -> None:
    if session.get("view") != "product" or not session.get("product_id"):
        raise IllegalAction("set_size requires an open product")
    size = arguments.get("size")
    if not isinstance(size, str) or not size:
        raise IllegalAction("size is required")
    product = product_by_id(catalog, session["product_id"])
    if product is None:
        raise IllegalAction("unknown product")
    if size not in product["sizes"]:
        raise IllegalAction(f"size {size!r} is not offered")
    session["selected_size"] = size


def _add_to_cart(session: dict[str, Any], catalog: list[dict[str, Any]]) -> None:
    if session.get("view") != "product" or not session.get("product_id"):
        raise IllegalAction("add_to_cart requires an open product")
    size = session.get("selected_size")
    if not size:
        raise IllegalAction("select a size before adding to cart")
    product = product_by_id(catalog, session["product_id"])
    if product is None:
        raise IllegalAction("unknown product")
    if size not in in_stock_sizes(product):
        raise IllegalAction(f"size {size} is out of stock")
    session["cart"].append(
        {
            "product_id": product["id"],
            "name": product["name"],
            "size": size,
            "price": product["price"],
        }
    )


def _set_address(session: dict[str, Any], arguments: dict[str, Any]) -> None:
    if session.get("view") != "checkout":
        raise IllegalAction("set_address requires the checkout view")
    address = arguments.get("address")
    if not isinstance(address, str) or not address.strip():
        raise IllegalAction("address is required")
    session["address"] = address.strip()


def _pay(session: dict[str, Any]) -> None:
    if session.get("view") != "checkout":
        raise IllegalAction("pay requires the checkout view")
    cart = session.get("cart") or []
    if not cart:
        raise IllegalAction("cart is empty")
    address = (session.get("address") or "").strip()
    if not address:
        raise IllegalAction("address is required")
    session["orders"].append({"items": list(cart), "address": address})
    session["cart"] = []
    session["view"] = "confirmation"
