"""Deterministic, model-free observation-cost baseline for C1-C4.

This measures the *observation* half of the input-token cost equation from
`docs/research-plan.md`:

    input_tokens(run) ~= per_step_observation_cost(condition) * steps + overhead

No model is called and nothing is billed. We replay each task's canonical
action path (the scripted policies in `harness.scripted`) and, at every step,
count the tokens of the observation the agent *would* read under each
condition, using a fixed reference tokenizer. The result is a lower bound on
per-condition input cost along the minimal path, and a fair way to isolate the
"how heavy is one look" term before any model run introduces variance.

Scope and honesty notes:

- C3 and C4 are measured exactly: both are produced server-side and are fully
  deterministic. C3's per-step observation is the tool-result payload plus the
  tool schema (the harness sends the tools on every call); C4's is the view
  document from `/agent/surface`. This is the fair, same-grain comparison at
  the heart of the study.
- C1 is an *estimate*: the image-token cost of the fixed 1280x800 viewport
  under OpenAI's gpt-4o high-detail tiling. Other models tokenize images
  differently, and the true value is read from provider usage at run time.
- C2 (accessibility tree) requires a live browser and is measured during the
  model runs, not here.
- Token counts are tokenizer-dependent. We use `o200k_base` (the gpt-4o
  family) as the reference and fall back to `cl100k_base` if unavailable.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from harness.scripted import POLICIES
from minishop.catalog import load_tasks
from minishop.server import app
from minishop.tools import tool_schemas

VIEWPORT = (1280, 800)


def _encoder():
    import tiktoken

    try:
        return tiktoken.get_encoding("o200k_base")
    except Exception:  # pragma: no cover - environment dependent
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(enc, obj: Any) -> int:
    text = obj if isinstance(obj, str) else json.dumps(obj)
    return len(enc.encode(text))


def image_tokens_high_detail(width: int, height: int, *, base: int = 85, per_tile: int = 170) -> int:
    """OpenAI gpt-4o high-detail image-token estimate for a fixed viewport.

    Scale to fit 2048x2048, then scale the shortest side to 768px, then charge
    ``per_tile`` per 512px tile plus a ``base`` constant. Labeled as an
    estimate; the real value is provider-reported at run time.
    """
    w, h = float(width), float(height)
    if max(w, h) > 2048:
        s = 2048 / max(w, h)
        w, h = w * s, h * s
    if min(w, h) > 768:
        s = 768 / min(w, h)
        w, h = w * s, h * s
    tiles = math.ceil(w / 512) * math.ceil(h / 512)
    return base + per_tile * tiles


@dataclass(frozen=True)
class TaskCost:
    task_id: str
    expect: str
    steps: int
    c1_obs_tokens: int  # estimate (image tiling), per-step constant * steps
    c3_obs_tokens: int  # tool schema + tool-result payloads, exact
    c4_obs_tokens: int  # view documents, exact


def _act(client: TestClient, sid: str, name: str, arguments: dict[str, Any], enforce: bool):
    return client.post(
        "/agent/act",
        json={"session_id": sid, "name": name, "arguments": arguments, "enforce_surface": enforce},
    )


def measure_task(client: TestClient, enc, task: dict[str, Any], tools_tokens: int) -> TaskCost:
    policy = POLICIES[task["id"]]
    image_per_step = image_tokens_high_detail(*VIEWPORT)

    # C4: view document read before each decision.
    sid4 = client.post("/agent/session").json()["session_id"]
    c4 = 0
    for name, arguments in policy:
        surface = client.get("/agent/surface", params={"session_id": sid4}).json()
        c4 += count_tokens(enc, surface)
        r = _act(client, sid4, name, arguments, enforce=True)
        if r.status_code == 400:
            break

    # C3: short status observation before each decision, plus the tool schema
    # that the harness sends on every call.
    sid3 = client.post("/agent/session").json()["session_id"]
    c3 = 0
    prev_payload: Any = {"status": "start"}
    steps = 0
    for name, arguments in policy:
        c3 += tools_tokens + count_tokens(enc, prev_payload)
        steps += 1
        r = _act(client, sid3, name, arguments, enforce=False)
        prev_payload = r.json()
        if r.status_code == 400:
            break

    return TaskCost(
        task_id=task["id"],
        expect=task.get("expect", "success"),
        steps=steps,
        c1_obs_tokens=image_per_step * steps,
        c3_obs_tokens=c3,
        c4_obs_tokens=c4,
    )


def measure_all() -> list[TaskCost]:
    enc = _encoder()
    client = TestClient(app)
    tools_tokens = count_tokens(enc, tool_schemas())
    return [measure_task(client, enc, task, tools_tokens) for task in load_tasks()]


def summarize(costs: list[TaskCost], *, only_success: bool = True) -> dict[str, dict[str, float]]:
    rows = [c for c in costs if (c.expect == "success" or not only_success)]
    out: dict[str, dict[str, float]] = {}
    for cond, attr in (("C1(est)", "c1_obs_tokens"), ("C3", "c3_obs_tokens"), ("C4", "c4_obs_tokens")):
        vals = [getattr(c, attr) for c in rows]
        per_step = [getattr(c, attr) / c.steps for c in rows if c.steps]
        out[cond] = {
            "median_obs_tokens_per_task": statistics.median(vals) if vals else 0.0,
            "median_obs_tokens_per_step": statistics.median(per_step) if per_step else 0.0,
        }
    return out


def markdown_summary(summary: dict[str, dict[str, float]]) -> str:
    lines = [
        "| condition | median obs tokens / task | median obs tokens / step |",
        "| --- | --- | --- |",
    ]
    for cond, m in summary.items():
        lines.append(
            f"| {cond} | {m['median_obs_tokens_per_task']:.0f} | {m['median_obs_tokens_per_step']:.0f} |"
        )
    return "\n".join(lines)


def write_csv(costs: list[TaskCost], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["task_id", "expect", "steps", "c1_est_obs_tokens", "c3_obs_tokens", "c4_obs_tokens"])
        for c in costs:
            writer.writerow([c.task_id, c.expect, c.steps, c.c1_obs_tokens, c.c3_obs_tokens, c.c4_obs_tokens])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Deterministic observation-cost baseline (no model)")
    parser.add_argument("--out", default="report", help="Output directory for the CSV")
    parser.add_argument("--all-tasks", action="store_true", help="Include refusal tasks in the summary")
    args = parser.parse_args(argv)

    costs = measure_all()
    summary = summarize(costs, only_success=not args.all_tasks)
    out = Path(args.out)
    write_csv(costs, out / "obs_cost.csv")

    print("Per-task observation tokens (canonical path):")
    print(f"{'task':>5} {'exp':>8} {'steps':>5} {'C1(est)':>9} {'C3':>7} {'C4':>7}")
    for c in costs:
        print(f"{c.task_id:>5} {c.expect:>8} {c.steps:>5} {c.c1_obs_tokens:>9} {c.c3_obs_tokens:>7} {c.c4_obs_tokens:>7}")
    scope = "all tasks" if args.all_tasks else "success tasks"
    print(f"\nSummary ({scope}):")
    print(markdown_summary(summary))
    print(f"\nWrote {out / 'obs_cost.csv'}")
    print(
        "\nNotes: C3/C4 exact and server-side; C1 is an OpenAI gpt-4o high-detail "
        "image estimate for the 1280x800 viewport; C2 needs a browser and is measured "
        "during model runs. Counts use the o200k_base tokenizer."
    )


if __name__ == "__main__":
    main()
