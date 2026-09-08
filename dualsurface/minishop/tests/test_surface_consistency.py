"""The C4 view document must not lie about what the backend will accept.

The whole Area 1 claim uses C4 as a trustworthy upper bound, so the surface
and the backend must not disagree. These tests assert two things along the
canonical task paths:

1. Enum fidelity: the `set_size` affordance advertises exactly the in-stock
   sizes, and `add_to_cart` / `pay` are enabled exactly when their
   preconditions hold.
2. No false advertising: an affordance the surface marks disabled is rejected
   by the backend under surface enforcement (C4), and every action the
   scripted C4 path takes (marked enabled) is accepted. This includes a
   t10-specific regression (``set_address`` on the product view) where a model
   in the N=5 sweep emitted a disabled action: the document did not lie about
   it, so the failure is model behavior, not a surface/backend disagreement.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from harness.scripted import POLICIES
from minishop.catalog import in_stock_sizes, load_catalog, load_tasks, product_by_id
from minishop.server import app

CATALOG = load_catalog()
SUCCESS_TASKS = [t for t in load_tasks() if t.get("expect") == "success"]


def _surface(client: TestClient, sid: str) -> dict[str, Any]:
    return client.get("/agent/surface", params={"session_id": sid}).json()


def _affordance(surface: dict[str, Any], name: str) -> dict[str, Any]:
    return next(a for a in surface["affordances"] if a["id"] == name)


def _act(client: TestClient, sid: str, name: str, arguments: dict[str, Any], enforce: bool):
    return client.post(
        "/agent/act",
        json={"session_id": sid, "name": name, "arguments": arguments, "enforce_surface": enforce},
    )


def test_set_size_enum_matches_backend_stock_on_every_product_view():
    """When a product is open, the surface size enum == the in-stock sizes."""
    client = TestClient(app)
    for task in SUCCESS_TASKS:
        sid = client.post("/agent/session").json()["session_id"]
        for name, arguments in POLICIES[task["id"]]:
            _act(client, sid, name, arguments, enforce=True)
            surface = _surface(client, sid)
            if surface["view"] == "product":
                product = product_by_id(CATALOG, surface["state"]["product_id"])
                enum = _affordance(surface, "set_size")["input"]["properties"]["size"]["enum"]
                assert enum == in_stock_sizes(product), (task["id"], product["id"], enum)


def test_enabled_flags_match_preconditions_along_paths():
    client = TestClient(app)
    for task in SUCCESS_TASKS:
        sid = client.post("/agent/session").json()["session_id"]
        for name, arguments in POLICIES[task["id"]]:
            surface = _surface(client, sid)
            state = surface["state"]
            add = _affordance(surface, "add_to_cart")["enabled"]
            pay = _affordance(surface, "pay")["enabled"]
            product = product_by_id(CATALOG, state["product_id"]) if state["product_id"] else None
            expect_add = (
                surface["view"] == "product"
                and product is not None
                and state["selected_size"] in in_stock_sizes(product)
            )
            expect_pay = surface["view"] == "checkout" and state["cart_count"] > 0 and bool(state["address"].strip())
            assert add is expect_add, (task["id"], "add_to_cart", surface["view"], state)
            assert pay is expect_pay, (task["id"], "pay", surface["view"], state)
            _act(client, sid, name, arguments, enforce=True)


def test_disabled_affordance_is_rejected_under_enforcement():
    """A surface-disabled action must be rejected by the backend (C4)."""
    client = TestClient(app)

    # pay on a fresh catalog view: disabled -> rejected.
    sid = client.post("/agent/session").json()["session_id"]
    assert _affordance(_surface(client, sid), "pay")["enabled"] is False
    assert _act(client, sid, "pay", {}, enforce=True).status_code == 400

    # add_to_cart with an open product but no size selected: disabled -> rejected.
    sid = client.post("/agent/session").json()["session_id"]
    _act(client, sid, "open_product", {"product_id": "tee-navy"}, enforce=True)
    assert _affordance(_surface(client, sid), "add_to_cart")["enabled"] is False
    assert _act(client, sid, "add_to_cart", {}, enforce=True).status_code == 400


def test_set_address_on_product_view_is_disabled_and_rejected_t10():
    """Regression for the t10 C4 failure: on the product view (mid-task, item in
    cart, before ``go_checkout``) the surface must mark ``set_address`` disabled
    *and* the backend must reject it under enforcement. Surface and backend
    agree, so the observed t10 illegal action is a model behavior (it ignored
    the ``enabled: false`` flag), not a surface/backend consistency violation.

    The N=5 gemini-flash sweep hit exactly this: after
    open_product(tee-navy) -> set_size(L) -> add_to_cart, the model emitted
    set_address before go_checkout. This pins that the document did not lie:
    it never advertised set_address as available on the product view.
    """
    client = TestClient(app)
    sid = client.post("/agent/session").json()["session_id"]
    for name, arguments in (
        ("open_product", {"product_id": "tee-navy"}),
        ("set_size", {"size": "L"}),
        ("add_to_cart", {}),
    ):
        _act(client, sid, name, arguments, enforce=True)

    surface = _surface(client, sid)
    assert surface["view"] == "product"
    assert surface["state"]["cart_count"] == 1
    # The document marks set_address disabled on the product view ...
    assert _affordance(surface, "set_address")["enabled"] is False
    # ... and the backend rejects the exact action the model emitted.
    response = _act(client, sid, "set_address", {"address": "77 Oak Lane, Denver"}, enforce=True)
    assert response.status_code == 400
    assert response.json().get("illegal") is True


def test_out_of_stock_size_is_absent_from_enum_and_unselectable():
    """tee-blue has M out of stock: it must be omitted and unselectable in C4."""
    client = TestClient(app)
    sid = client.post("/agent/session").json()["session_id"]
    _act(client, sid, "open_product", {"product_id": "tee-blue"}, enforce=True)
    enum = _affordance(_surface(client, sid), "set_size")["input"]["properties"]["size"]["enum"]
    assert "M" not in enum
    # Attempting the omitted value under enforcement is rejected.
    assert _act(client, sid, "set_size", {"size": "M"}, enforce=True).status_code == 400
