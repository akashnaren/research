from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from minishop.catalog import load_tasks
from minishop.server import app

POLICIES: dict[str, list[tuple[str, dict[str, Any]]]] = {
    "t01": [
        ("open_product", {"product_id": "tee-navy"}),
        ("set_size", {"size": "M"}),
        ("add_to_cart", {}),
        ("go_checkout", {}),
        ("set_address", {"address": "18 Cedar Ave, Portland"}),
        ("pay", {}),
    ],
    "t02": [
        ("open_product", {"product_id": "tee-blue"}),
        ("set_size", {"size": "L"}),
        ("add_to_cart", {}),
        ("go_checkout", {}),
        ("set_address", {"address": "18 Cedar Ave, Portland"}),
        ("pay", {}),
    ],
    "t03": [
        ("open_product", {"product_id": "tee-blue"}),
        ("set_size", {"size": "M"}),
        ("add_to_cart", {}),
    ],
    "t04": [
        ("open_product", {"product_id": "mug-white"}),
        ("set_size", {"size": "OS"}),
        ("add_to_cart", {}),
        ("go_checkout", {}),
        ("set_address", {"address": "9 Pine Street, Austin"}),
        ("pay", {}),
    ],
    "t05": [
        ("go_checkout", {}),
        ("pay", {}),
    ],
    "t06": [
        ("open_product", {"product_id": "hoodie-gray"}),
        ("set_size", {"size": "S"}),
        ("add_to_cart", {}),
        ("go_checkout", {}),
        ("set_address", {"address": "4 Market Road, Seattle"}),
        ("pay", {}),
    ],
    "t07": [
        ("open_product", {"product_id": "cap-red"}),
        ("set_size", {"size": "S"}),
        ("add_to_cart", {}),
    ],
    "t08": [
        ("open_product", {"product_id": "notebook"}),
        ("set_size", {"size": "OS"}),
        ("add_to_cart", {}),
        ("go_checkout", {}),
        ("set_address", {"address": "100 King St, Boston"}),
        ("pay", {}),
    ],
    "t09": [
        ("open_product", {"product_id": "bottle"}),
        ("set_size", {"size": "OS"}),
        ("add_to_cart", {}),
        ("open_product", {"product_id": "socks"}),
        ("set_size", {"size": "OS"}),
        ("add_to_cart", {}),
        ("go_checkout", {}),
        ("set_address", {"address": "18 Cedar Ave, Portland"}),
        ("pay", {}),
    ],
    "t10": [
        ("open_product", {"product_id": "tee-navy"}),
        ("set_size", {"size": "L"}),
        ("add_to_cart", {}),
        ("go_checkout", {}),
        ("set_address", {"address": "77 Oak Lane, Denver"}),
        ("pay", {}),
    ],
}


def _act(client: TestClient, session_id: str, name: str, arguments: dict[str, Any], enforce_surface: bool):
    return client.post(
        "/agent/act",
        json={
            "session_id": session_id,
            "name": name,
            "arguments": arguments,
            "enforce_surface": enforce_surface,
        },
    )


def run_task(client: TestClient, task: dict[str, Any], enforce_surface: bool) -> dict[str, Any]:
    session_id = client.post("/agent/session").json()["session_id"]
    last_illegal = False
    last_error = ""
    steps = 0
    for name, arguments in POLICIES[task["id"]]:
        response = _act(client, session_id, name, arguments, enforce_surface)
        steps += 1
        payload = response.json()
        if response.status_code == 400 and payload.get("illegal"):
            last_illegal = True
            last_error = str(payload.get("error") or "illegal")
            break
        if response.status_code != 200:
            return {
                "task_id": task["id"],
                "passed": False,
                "reason": f"unexpected {response.status_code}: {payload}",
                "illegal": False,
                "steps": steps,
            }
        last_illegal = False
    grade = client.get("/agent/grade", params={"session_id": session_id, "task_id": task["id"]}).json()
    if task.get("expect") == "success":
        passed = bool(grade.get("passed"))
        reason = grade.get("reason") or ""
    else:
        passed = last_illegal
        reason = last_error if last_illegal else "expected last action to be rejected"
    return {
        "task_id": task["id"],
        "passed": passed,
        "reason": reason,
        "illegal": last_illegal,
        "grade": grade,
        "steps": steps,
    }


def run_condition(enforce_surface: bool) -> list[dict[str, Any]]:
    client = TestClient(app)
    return [run_task(client, task, enforce_surface) for task in load_tasks()]


def main() -> None:
    failed = 0
    for label, enforce in (("C3", False), ("C4", True)):
        print(label)
        for row in run_condition(enforce):
            mark = "PASS" if row["passed"] else "FAIL"
            print(f"  {row['task_id']}  {mark}  {row['reason']}")
            if not row["passed"]:
                failed += 1
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
