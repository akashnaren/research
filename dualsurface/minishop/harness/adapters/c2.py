from __future__ import annotations

from typing import Any

from harness.adapters.human_ui import HumanUI


def observe_c2(ui: HumanUI) -> dict[str, Any]:
    return {"kind": "aria", "tree": ui.aria_tree(), "illegal": ui.illegal()}


def apply_c2(ui: HumanUI, action: dict[str, Any]) -> dict[str, Any]:
    name = action.get("action")
    if name == "done":
        return {"ok": True, "done": True, "illegal": False}
    try:
        if name == "click":
            ui.click_named(str(action.get("name") or ""))
        elif name == "fill":
            ui.fill_named(str(action.get("name") or ""), str(action.get("text") or ""))
        elif name == "scroll":
            ui.scroll(action.get("dy") or 0)
        else:
            return {"ok": False, "done": False, "illegal": False, "error": f"unknown action {name!r}"}
    except Exception as exc:
        return {"ok": False, "done": False, "illegal": ui.illegal(), "error": str(exc)}
    return {"ok": True, "done": False, "illegal": ui.illegal()}
