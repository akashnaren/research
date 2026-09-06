from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from harness.adapters.c1 import apply_c1, observe_c1
from harness.adapters.c2 import apply_c2, observe_c2
from harness.adapters.human_ui import HumanUI
from harness.models import ModelSpec, resolve_aliases
from harness.openai_compat import OpenAICompat
from harness.prompts import system_prompt
from harness.vertex import VertexAccessToken, vertex_endpoint

ROOT = Path(__file__).resolve().parent.parent
TRACES = ROOT / "traces"
STEP_CAP = 20
VIEWPORT = (1280, 800)


def _client(base: str) -> httpx.Client:
    return httpx.Client(base_url=base.rstrip("/"), timeout=30.0)


def _new_session(http: httpx.Client) -> str:
    response = http.post("/agent/session")
    response.raise_for_status()
    return response.json()["session_id"]


def _tasks(http: httpx.Client) -> list[dict[str, Any]]:
    return http.get("/agent/tasks").json()["tasks"]


def _grade(http: httpx.Client, session_id: str, task_id: str) -> dict[str, Any]:
    return http.get("/agent/grade", params={"session_id": session_id, "task_id": task_id}).json()


def _parse_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


JSON_ONLY_INSTRUCTION = (
    "\n\nRespond with a single JSON object only. No prose, no markdown fences, "
    "no text before or after the JSON object."
)


def _messages(
    condition: str,
    task: dict[str, Any],
    prior: list[str],
    observation: str | list[dict[str, Any]],
    *,
    force_json_text: bool = False,
) -> list[dict[str, Any]]:
    prior_text = "None." if not prior else "\n".join(f"{i + 1}. {item}" for i, item in enumerate(prior))
    header = (
        f"Task:\n{task['instruction']}\n\n"
        f"Prior actions:\n{prior_text}\n\n"
        "Current observation only (do not assume pages you cannot see now)."
    )
    if isinstance(observation, list):
        content: Any = [{"type": "text", "text": header}] + observation
    else:
        content = header + "\n\n" + observation
    system = system_prompt(condition)
    if force_json_text:
        # Some Vertex OpenAI-compat paths (e.g. Anthropic/Claude) do not
        # reliably support response_format=json_object; fall back to
        # instructing JSON-only output via the prompt instead, and parse
        # leniently with _parse_json.
        system = system + JSON_ONLY_INSTRUCTION
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": content},
    ]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def run_c3_c4(
    *,
    condition: str,
    task: dict[str, Any],
    http: httpx.Client,
    llm: OpenAICompat,
    model_alias: str,
    json_object_supported: bool = True,
) -> dict[str, Any]:
    session_id = _new_session(http)
    enforce = condition == "C4"
    tools = http.get("/agent/tools").json()["tools"] if condition == "C3" else None
    prior: list[str] = []
    steps: list[dict[str, Any]] = []
    illegal_count = 0
    done = False
    # C3: short tool status / product list only. Never the C4 surface document.
    observation: str | list[dict[str, Any]] = json.dumps({"status": "start"})
    for step in range(1, STEP_CAP + 1):
        if condition == "C4":
            observation = json.dumps(http.get("/agent/surface", params={"session_id": session_id}).json())
            messages = _messages(condition, task, prior, observation, force_json_text=not json_object_supported)
            result = llm.chat(messages, json_object=json_object_supported)
            action = _parse_json(result["message"].get("content") or "")
            name = action.get("name")
            arguments = action.get("arguments") or {}
        else:
            result = llm.chat(_messages(condition, task, prior, observation), tools=tools)
            message = result["message"]
            calls = message.get("tool_calls") or []
            if not calls:
                done = True
                steps.append(
                    {
                        "type": "step",
                        "step": step,
                        "usage": result["usage"],
                        "action": {"name": "stop", "arguments": {}},
                        "illegal": False,
                    }
                )
                break
            call = calls[0]
            fn = call.get("function") or {}
            name = fn.get("name")
            raw_args = fn.get("arguments") or "{}"
            arguments = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            action = {"name": name, "arguments": arguments}

        if name in {None, "done", "stop"}:
            done = True
            steps.append({"type": "step", "step": step, "usage": result["usage"], "action": action, "illegal": False})
            break

        response = http.post(
            "/agent/act",
            json={
                "session_id": session_id,
                "name": name,
                "arguments": arguments,
                "enforce_surface": enforce,
            },
        )
        payload = response.json()
        illegal = response.status_code == 400 and bool(payload.get("illegal"))
        if illegal:
            illegal_count += 1
        prior.append(f"{name} {json.dumps(arguments, sort_keys=True)}")
        steps.append(
            {
                "type": "step",
                "step": step,
                "usage": result["usage"],
                "action": action,
                "result": payload,
                "illegal": illegal,
            }
        )
        if condition == "C3":
            observation = json.dumps(payload)
        grade = _grade(http, session_id, task["id"])
        if task.get("expect") == "success" and grade.get("passed"):
            break

    grade = _grade(http, session_id, task["id"])
    return _summarize(condition, task, llm.model, model_alias, session_id, steps, illegal_count, grade, done)


def run_c1_c2(
    *,
    condition: str,
    task: dict[str, Any],
    http: httpx.Client,
    llm: OpenAICompat,
    base_url: str,
    model_alias: str,
    json_object_supported: bool = True,
) -> dict[str, Any]:
    session_id = _new_session(http)
    ui = HumanUI(base_url, session_id, width=VIEWPORT[0], height=VIEWPORT[1])
    ui.start()
    prior: list[str] = []
    steps: list[dict[str, Any]] = []
    illegal_count = 0
    done = False
    image_dir = TRACES / "images"
    try:
        for step in range(1, STEP_CAP + 1):
            if condition == "C1":
                obs = observe_c1(ui)
                image_dir.mkdir(parents=True, exist_ok=True)
                image_path = image_dir / f"{task['id']}_C1_step{step}.png"
                image_path.write_bytes(obs["png"])
                b64 = base64.b64encode(obs["png"]).decode("ascii")
                observation: str | list[dict[str, Any]] = [
                    {
                        "type": "text",
                        "text": f"Screenshot {obs['width']}x{obs['height']} CSS pixels. Top-left is (0,0).",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"},
                    },
                ]
                trace_obs = {"kind": "screenshot", "path": str(image_path), "bytes": len(obs["png"])}
            else:
                obs = observe_c2(ui)
                observation = obs["tree"]
                trace_obs = {"kind": "aria", "tree": obs["tree"]}

            messages = _messages(condition, task, prior, observation, force_json_text=not json_object_supported)
            result = llm.chat(messages, json_object=json_object_supported)
            action = _parse_json(result["message"].get("content") or "")
            applied = apply_c1(ui, action) if condition == "C1" else apply_c2(ui, action)
            illegal = bool(applied.get("illegal"))
            if illegal:
                illegal_count += 1
            prior.append(json.dumps(action, sort_keys=True))
            steps.append(
                {
                    "type": "step",
                    "step": step,
                    "usage": result["usage"],
                    "observation": trace_obs,
                    "action": action,
                    "applied": {k: v for k, v in applied.items() if k != "png"},
                    "illegal": illegal,
                }
            )
            if applied.get("done"):
                done = True
                break
            grade = _grade(http, session_id, task["id"])
            if task.get("expect") == "success" and grade.get("passed"):
                break
    finally:
        ui.close()

    grade = _grade(http, session_id, task["id"])
    return _summarize(condition, task, llm.model, model_alias, session_id, steps, illegal_count, grade, done)


def _summarize(
    condition: str,
    task: dict[str, Any],
    model: str,
    model_alias: str,
    session_id: str,
    steps: list[dict[str, Any]],
    illegal_count: int,
    grade: dict[str, Any],
    done: bool,
) -> dict[str, Any]:
    input_tokens = sum(int(step["usage"].get("prompt_tokens") or 0) for step in steps)
    output_tokens = sum(int(step["usage"].get("completion_tokens") or 0) for step in steps)
    image_tokens = sum(int(step["usage"].get("image_tokens") or 0) for step in steps)
    return {
        "type": "result",
        "condition": condition,
        "task_id": task["id"],
        "model": model,
        "model_alias": model_alias,
        "session_id": session_id,
        "passed": bool(grade.get("passed")),
        "reason": grade.get("reason"),
        "steps": len(steps),
        "illegal_actions": illegal_count,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "image_tokens": image_tokens,
        "done": done,
        "temperature": 0,
        "step_cap": STEP_CAP,
        "history": "task + prior actions + current observation",
        "steps_detail": steps,
        "grade": grade,
    }


def run_one(
    condition: str,
    task: dict[str, Any],
    http: httpx.Client,
    llm: OpenAICompat,
    base_url: str,
    *,
    model_alias: str,
    json_object_supported: bool = True,
) -> dict[str, Any]:
    if condition in {"C3", "C4"}:
        return run_c3_c4(
            condition=condition,
            task=task,
            http=http,
            llm=llm,
            model_alias=model_alias,
            json_object_supported=json_object_supported,
        )
    if condition in {"C1", "C2"}:
        return run_c1_c2(
            condition=condition,
            task=task,
            http=http,
            llm=llm,
            base_url=base_url,
            model_alias=model_alias,
            json_object_supported=json_object_supported,
        )
    raise ValueError(f"unknown condition {condition}")


def _build_llm(spec: ModelSpec) -> OpenAICompat:
    """Construct an OpenAICompat client for a ModelSpec (Vertex or OpenAI)."""
    if spec.provider == "vertex":
        endpoint = vertex_endpoint()
        token = VertexAccessToken()
        # Pass a callable, not a fixed string: Vertex access tokens expire
        # after about an hour and must be refreshed on every request.
        return OpenAICompat(token.get, endpoint.base_url, spec.api_model)
    if spec.provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("OPENAI_API_KEY is required (see .env.example). Do not commit .env.", file=sys.stderr)
            raise SystemExit(2)
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        return OpenAICompat(api_key, base_url, spec.api_model)
    raise ValueError(f"unknown provider {spec.provider!r} for model alias {spec.alias!r}")


def main(argv: list[str] | None = None) -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="MiniShop model loop for C1–C4")
    parser.add_argument("--conditions", default="C3,C4", help="Comma-separated C1,C2,C3,C4")
    parser.add_argument("--tasks", default="all", help="Comma-separated task ids, or all")
    parser.add_argument("--model", default=os.environ.get("MODEL", "gpt-4o-mini"))
    parser.add_argument(
        "--models",
        default=None,
        help=(
            "Comma-separated model aliases from harness/models.py (e.g. gemini-flash,sonnet,grok-fast), "
            "or a sweep name (mid, better, gcp). Overrides --model. Every requested model runs across "
            "every requested condition; results are tagged per model alias, never pooled."
        ),
    )
    parser.add_argument("--base", default=os.environ.get("MINISHOP_BASE", "http://127.0.0.1:8765"))
    args = parser.parse_args(argv)

    if args.models:
        try:
            specs = resolve_aliases(args.models)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(2)
    else:
        # Backward-compatible path: a single OpenAI model id, unchanged behavior.
        specs = [
            ModelSpec(
                alias=args.model,
                provider="openai",
                api_model=args.model,
                vision=True,
                tools=True,
                json_object=True,
            )
        ]

    conditions = [item.strip().upper() for item in args.conditions.split(",") if item.strip()]
    http = _client(args.base)
    try:
        http.get("/agent/tasks").raise_for_status()
    except httpx.HTTPError as exc:
        print(f"MiniShop is not reachable at {args.base}. Start uvicorn first. ({exc})", file=sys.stderr)
        raise SystemExit(2)

    all_tasks = _tasks(http)
    if args.tasks != "all":
        wanted = {item.strip() for item in args.tasks.split(",")}
        all_tasks = [task for task in all_tasks if task["id"] in wanted]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    failed = 0
    # Loop models outermost, same shape as the existing loop over conditions
    # and tasks. Never pooled: each model x condition combination gets its
    # own trace file and its own tagged result row (PROTOCOL.md "Models").
    for spec in specs:
        llm = _build_llm(spec)
        for condition in conditions:
            for task in all_tasks:
                print(f"{spec.alias} {condition} {task['id']} ...", flush=True)
                row = run_one(
                    condition,
                    task,
                    http,
                    llm,
                    args.base,
                    model_alias=spec.alias,
                    json_object_supported=spec.json_object,
                )
                path = TRACES / f"{stamp}_{spec.alias}_{condition}_{task['id']}.jsonl"
                header = {
                    "type": "run",
                    "model": spec.api_model,
                    "model_alias": spec.alias,
                    "condition": condition,
                    "task_id": task["id"],
                    "temperature": 0,
                    "step_cap": STEP_CAP,
                    "history": "task + prior actions + current observation",
                }
                _write_jsonl(
                    path, [header, *row["steps_detail"], {k: v for k, v in row.items() if k != "steps_detail"}]
                )
                mark = "PASS" if row["passed"] else "FAIL"
                print(
                    f"  {mark} steps={row['steps']} in={row['input_tokens']} out={row['output_tokens']} "
                    f"image_tokens={row['image_tokens']} illegal={row['illegal_actions']} trace={path}"
                )
                if not row["passed"] and task.get("expect") == "success":
                    failed += 1
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
