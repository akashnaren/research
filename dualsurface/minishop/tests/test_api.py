from fastapi.testclient import TestClient

from minishop.server import app


def test_c4_omits_sold_out_size():
    client = TestClient(app)
    session_id = client.post("/agent/session").json()["session_id"]
    assert (
        client.post(
            "/agent/act",
            json={
                "session_id": session_id,
                "name": "open_product",
                "arguments": {"product_id": "tee-blue"},
                "enforce_surface": True,
            },
        ).status_code
        == 200
    )
    surface = client.get("/agent/surface", params={"session_id": session_id}).json()
    set_size = next(item for item in surface["affordances"] if item["id"] == "set_size")
    assert "M" not in set_size["input"]["properties"]["size"]["enum"]
    assert set_size["input"]["properties"]["size"]["enum"] == ["S", "L"]
    add = next(item for item in surface["affordances"] if item["id"] == "add_to_cart")
    assert add["enabled"] is False
    rejected = client.post(
        "/agent/act",
        json={
            "session_id": session_id,
            "name": "set_size",
            "arguments": {"size": "M"},
            "enforce_surface": True,
        },
    )
    assert rejected.status_code == 400
    assert rejected.json()["illegal"] is True


def test_c3_list_products_is_not_a_view_document():
    client = TestClient(app)
    session_id = client.post("/agent/session").json()["session_id"]
    response = client.post(
        "/agent/act",
        json={
            "session_id": session_id,
            "name": "list_products",
            "arguments": {},
            "enforce_surface": False,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "products" in payload
    assert "affordances" not in payload
    assert "entities" not in payload
    assert payload["products"][0]["id"] == "tee-blue"


def test_c4_rejects_list_products():
    client = TestClient(app)
    session_id = client.post("/agent/session").json()["session_id"]
    response = client.post(
        "/agent/act",
        json={
            "session_id": session_id,
            "name": "list_products",
            "arguments": {},
            "enforce_surface": True,
        },
    )
    assert response.status_code == 400
    assert response.json()["illegal"] is True


def test_empty_pay_is_illegal():
    client = TestClient(app)
    session_id = client.post("/agent/session").json()["session_id"]
    client.post(
        "/agent/act",
        json={"session_id": session_id, "name": "go_checkout", "arguments": {}, "enforce_surface": False},
    )
    response = client.post(
        "/agent/act",
        json={"session_id": session_id, "name": "pay", "arguments": {}, "enforce_surface": False},
    )
    assert response.status_code == 400
    assert response.json() == {"illegal": True, "error": "cart is empty"}


def test_c3_selects_oos_size_then_add_is_illegal():
    client = TestClient(app)
    session_id = client.post("/agent/session").json()["session_id"]
    for name, arguments in (
        ("open_product", {"product_id": "tee-blue"}),
        ("set_size", {"size": "M"}),
    ):
        response = client.post(
            "/agent/act",
            json={"session_id": session_id, "name": name, "arguments": arguments, "enforce_surface": False},
        )
        assert response.status_code == 200, response.text
    rejected = client.post(
        "/agent/act",
        json={"session_id": session_id, "name": "add_to_cart", "arguments": {}, "enforce_surface": False},
    )
    assert rejected.status_code == 400
    assert rejected.json()["illegal"] is True


def test_c4_pay_disabled_on_empty_cart():
    client = TestClient(app)
    session_id = client.post("/agent/session").json()["session_id"]
    client.post(
        "/agent/act",
        json={"session_id": session_id, "name": "go_checkout", "arguments": {}, "enforce_surface": True},
    )
    surface = client.get("/agent/surface", params={"session_id": session_id}).json()
    pay = next(item for item in surface["affordances"] if item["id"] == "pay")
    assert pay["enabled"] is False
    assert set(item["id"] for item in surface["affordances"]) >= {
        "open_product",
        "set_size",
        "add_to_cart",
        "go_catalog",
        "go_checkout",
        "set_address",
        "pay",
    }


def test_human_sold_out_size_is_visible_and_disabled():
    client = TestClient(app)
    page = client.get("/product/tee-blue")
    assert page.status_code == 200
    html = page.text
    assert "Harbor Blue Tee" in html
    assert "Size M sold out" in html
    assert "disabled" in html
    assert "Add to cart" in html
    assert "Staff picks" in html


def test_ten_tasks_match_protocol_ids():
    from minishop.catalog import load_tasks

    ids = [task["id"] for task in load_tasks()]
    assert ids == [f"t{i:02d}" for i in range(1, 11)]
