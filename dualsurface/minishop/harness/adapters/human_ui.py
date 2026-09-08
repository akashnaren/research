from __future__ import annotations

from typing import Any


def format_ax_tree(node: dict[str, Any] | None, indent: int = 0) -> str:
    if not node:
        return "(empty accessibility tree)"
    role = node.get("role") or "node"
    name = node.get("name") or ""
    line = f"{'  ' * indent}[{role}] {name}".rstrip()
    children = node.get("children") or []
    lines = [line]
    for child in children:
        lines.append(format_ax_tree(child, indent + 1))
    return "\n".join(lines)


class HumanUI:
    """Drives MiniShop human pages. Used by C1 (screenshot) and C2 (accessibility tree)."""

    def __init__(self, base_url: str, session_id: str, *, width: int = 1280, height: int = 800) -> None:
        self.base_url = base_url.rstrip("/")
        self.session_id = session_id
        self.width = width
        self.height = height
        self._playwright = None
        self._browser = None
        self._context = None
        self.page = None

    def start(self) -> None:
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context(viewport={"width": self.width, "height": self.height})
        self._context.add_cookies(
            [{"name": "session_id", "value": self.session_id, "url": self.base_url}]
        )
        self.page = self._context.new_page()
        self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded")

    def screenshot_png(self) -> bytes:
        assert self.page is not None
        return self.page.screenshot(type="png")

    def aria_tree(self) -> str:
        assert self.page is not None
        try:
            return self.page.locator("body").aria_snapshot()
        except Exception:
            snapshot = self.page.accessibility.snapshot()
            return format_ax_tree(snapshot)

    def illegal(self) -> bool:
        assert self.page is not None
        return self.page.locator("[data-illegal=true]").count() > 0

    def click_xy(self, x: float, y: float) -> None:
        assert self.page is not None
        self.page.mouse.click(float(x), float(y))
        self._settle()

    def type_text(self, text: str) -> None:
        assert self.page is not None
        self.page.keyboard.type(text)

    def scroll(self, dy: float) -> None:
        assert self.page is not None
        self.page.mouse.wheel(0, float(dy))

    def _settle(self) -> None:
        assert self.page is not None
        try:
            self.page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            self.page.wait_for_load_state("domcontentloaded")

    def click_named(self, name: str) -> None:
        assert self.page is not None
        from playwright.sync_api import Locator

        locators: list[Locator] = [
            self.page.get_by_role("button", name=name),
            self.page.get_by_role("link", name=name),
            self.page.get_by_role("textbox", name=name),
            self.page.get_by_label(name),
            self.page.get_by_text(name, exact=True),
        ]
        for locator in locators:
            if locator.count():
                locator.first.click()
                self._settle()
                return
        raise RuntimeError(f"no control named {name!r}")

    def fill_named(self, name: str, text: str) -> None:
        assert self.page is not None
        locator = self.page.get_by_label(name)
        if locator.count() == 0:
            locator = self.page.get_by_role("textbox", name=name)
        if locator.count() == 0:
            raise RuntimeError(f"no field named {name!r}")
        locator.first.fill(text)

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()
