from __future__ import annotations

from typing import Any

from harness.adapters.human_ui import HumanUI


def observe_c1(ui: HumanUI) -> dict[str, Any]:
    png = ui.screenshot_png()
    return {
        "kind": "screenshot",
        "png": png,
        "width": ui.width,
        "height": ui.height,
        "illegal": ui.illegal(),
    }


def apply_c1(ui: HumanUI, action: dict[str, Any]) -> dict[str, Any]:
    name = action.get("action")
    if name == "done":
        return {"ok": True, "done": True, "illegal": False}
    if name == "click":
        ui.click_xy(action["x"], action["y"])
    elif name == "type":
        ui.type_text(str(action.get("text") or ""))
    elif name == "scroll":
        ui.scroll(action.get("dy") or 0)
    else:
        return {"ok": False, "done": False, "illegal": False, "error": f"unknown action {name!r}"}
    return {"ok": True, "done": False, "illegal": ui.illegal()}
