from __future__ import annotations

import threading
import time

import httpx
import pytest
import uvicorn

from harness.adapters.human_ui import HumanUI
from minishop.server import app

HOST = "127.0.0.1"
PORT = 8766
BASE = f"http://{HOST}:{PORT}"


@pytest.fixture(scope="module")
def live_server():
    try:
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        browser.close()
        playwright.stop()
    except Exception as exc:
        pytest.skip(f"Playwright Chromium not available: {exc}")
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="error")
    server = uvicorn.Server(config)
    server.install_signal_handlers = False
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            httpx.get(f"{BASE}/", timeout=0.2)
            yield server
            return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("MiniShop server did not start")


def test_c2_human_ui_completes_t01(live_server):
    session_id = httpx.post(f"{BASE}/agent/session", timeout=5).json()["session_id"]
    ui = HumanUI(BASE, session_id)
    ui.start()
    try:
        ui.click_named("Navy Crew Tee")
        ui.click_named("Size M")
        ui.click_named("Add to cart")
        ui.click_named("Checkout")
        ui.fill_named("Shipping address", "18 Cedar Ave, Portland")
        ui.click_named("Save address")
        ui.click_named("Pay now")
        assert "Order confirmed" in ui.page.content()
    finally:
        ui.close()
    grade = httpx.get(
        f"{BASE}/agent/grade",
        params={"session_id": session_id, "task_id": "t01"},
        timeout=5,
    ).json()
    assert grade["passed"], grade


def test_c1_screenshot_and_click_open_product(live_server):
    session_id = httpx.post(f"{BASE}/agent/session", timeout=5).json()["session_id"]
    ui = HumanUI(BASE, session_id)
    ui.start()
    try:
        png = ui.screenshot_png()
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        box = ui.page.get_by_role("link", name="Harbor Blue Tee").bounding_box()
        assert box
        ui.click_xy(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        html = ui.page.content()
        assert "Harbor Blue Tee" in html
        assert "Size M sold out" in html
        assert ui.page.get_by_role("button", name="Size M sold out").is_disabled()
    finally:
        ui.close()


def test_human_pay_empty_cart_is_illegal(live_server):
    session_id = httpx.post(f"{BASE}/agent/session", timeout=5).json()["session_id"]
    ui = HumanUI(BASE, session_id)
    ui.start()
    try:
        ui.click_named("Checkout")
        ui.click_named("Pay now")
        assert ui.illegal()
    finally:
        ui.close()
