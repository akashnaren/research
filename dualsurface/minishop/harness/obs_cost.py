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

from harness.prompts import system_prompt
from harness.scripted import POLICIES
from minishop.catalog import load_tasks
from minishop.server import app
from minishop.tools import tool_schemas

VIEWPORT = (1280, 800)

# Viewport resolutions used to show how the C1 screenshot cost scales with
# resolution (not with visual complexity). Ordered small -> large so a sweep
# over this list is monotonic non-decreasing in tile count and image tokens.
RESOLUTION_SWEEP: tuple[tuple[int, int], ...] = (
    (640, 480),
    (1024, 768),
    (1280, 800),
    (1536, 864),
    (1920, 1080),
)


def _encoder():
    import tiktoken

    try:
        return tiktoken.get_encoding("o200k_base")
    except Exception:  # pragma: no cover - environment dependent
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(enc, obj: Any) -> int:
    text = obj if isinstance(obj, str) else json.dumps(obj)
    return len(enc.encode(text))


def tile_geometry(width: int, height: int) -> tuple[float, float, int]:
    """Return the (scaled_w, scaled_h, tiles) of the OpenAI high-detail tiling.

    The rule: downscale to fit within 2048x2048, then scale the shortest side
    to 768px, then cover the result in 512x512 tiles. This geometry is a
    function of *resolution only* -- a blank page and a busy page at the same
    viewport produce the identical tile count and therefore the identical
    image-token cost. The formula is provider- and model-specific (this is the
    OpenAI gpt-4o family); other providers tokenize images differently.
    """
    w, h = float(width), float(height)
    if max(w, h) > 2048:
        s = 2048 / max(w, h)
        w, h = w * s, h * s
    if min(w, h) > 768:
        s = 768 / min(w, h)
        w, h = w * s, h * s
    tiles = math.ceil(w / 512) * math.ceil(h / 512)
    return w, h, tiles


def image_tokens_high_detail(width: int, height: int, *, base: int = 85, per_tile: int = 170) -> int:
    """OpenAI gpt-4o high-detail image-token estimate for a fixed viewport.

    ``tokens ~= base + per_tile * tiles`` where ``tiles`` comes from
    :func:`tile_geometry` (e.g. OpenAI high-detail base=85, per_tile=170).
    Labeled as an estimate; the real value is provider-reported at run time,
    and providers such as Vertex/Gemini fold it into ``prompt_tokens`` rather
    than itemizing it.
    """
    _, _, tiles = tile_geometry(width, height)
    return base + per_tile * tiles


def image_tokens_low_detail(*, base: int = 85) -> int:
    """OpenAI low-detail image cost: a flat ``base`` independent of resolution.

    Low detail sends a single downscaled thumbnail, so its cost does not vary
    with viewport size at all -- the clearest illustration that image-token
    cost is a resolution/detail decision, not a function of page content.
    """
    return base


@dataclass(frozen=True)
class ResolutionCost:
    width: int
    height: int
    scaled_width: int
    scaled_height: int
    tiles: int
    high_detail_tokens: int
    low_detail_tokens: int


def image_tokens_by_resolution(
    resolutions: tuple[tuple[int, int], ...] | list[tuple[int, int]] | None = None,
    *,
    base: int = 85,
    per_tile: int = 170,
) -> list[ResolutionCost]:
    """Sweep the C1 image-token estimate across viewport resolutions.

    Shows how the screenshot's cost scales with resolution under the OpenAI
    high-detail tiling model, plus the flat low-detail cost for contrast. The
    high-detail token count is monotonic non-decreasing as resolution grows.
    """
    rows: list[ResolutionCost] = []
    for width, height in resolutions or RESOLUTION_SWEEP:
        sw, sh, tiles = tile_geometry(width, height)
        rows.append(
            ResolutionCost(
                width=width,
                height=height,
                scaled_width=int(round(sw)),
                scaled_height=int(round(sh)),
                tiles=tiles,
                high_detail_tokens=base + per_tile * tiles,
                low_detail_tokens=image_tokens_low_detail(base=base),
            )
        )
    return rows


def write_resolution_csv(rows: list[ResolutionCost], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["width", "height", "scaled_width", "scaled_height", "tiles", "high_detail_tokens", "low_detail_tokens"]
        )
        for r in rows:
            writer.writerow(
                [r.width, r.height, r.scaled_width, r.scaled_height, r.tiles, r.high_detail_tokens, r.low_detail_tokens]
            )


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


# ---------------------------------------------------------------------------
# Per-condition observation-token composition
#
# The measure_task path above answers "how heavy is one look". This section
# answers "what is each look made of": it splits every per-step input into the
# fixed overhead the harness sends under every condition (system prompt + task
# text + prior-action history) and the condition-specific part (the tool schema
# on C3, the view document on C4, the image on C1). The reconstruction mirrors
# harness.model_loop._messages exactly for the text parts.
# ---------------------------------------------------------------------------

# Trailing line of the user turn header in model_loop._messages, reproduced
# verbatim so the fixed-overhead count matches what a provider actually bills.
_OBS_FOOTER = "Current observation only (do not assume pages you cannot see now)."


def _header_text(task: dict[str, Any], prior: list[str]) -> str:
    """Reproduce harness.model_loop._messages' user-turn header verbatim."""
    prior_text = "None." if not prior else "\n".join(f"{i + 1}. {item}" for i, item in enumerate(prior))
    return f"Task:\n{task['instruction']}\n\nPrior actions:\n{prior_text}\n\n{_OBS_FOOTER}"


def _prior_item(name: str, arguments: dict[str, Any]) -> str:
    """Canonical prior-action serialization used by the C3/C4 loop.

    C1/C2 serialize their (coordinate/named) actions differently at run time, so
    for those conditions this is a close approximation of the history term; it
    is small next to the image (C1) cost either way.
    """
    return f"{name} {json.dumps(arguments, sort_keys=True)}"


@dataclass(frozen=True)
class StepComposition:
    task_id: str
    condition: str
    step: int
    system_prompt: int  # fixed overhead: condition system prompt
    task_and_prior: int  # fixed overhead: task text + prior-action history
    observation: int  # condition-specific: image (C1)/tool result (C3)/document (C4)
    tools_schema: int  # condition-specific, C3 only (0 elsewhere)

    @property
    def fixed_overhead(self) -> int:
        return self.system_prompt + self.task_and_prior

    @property
    def condition_specific(self) -> int:
        return self.observation + self.tools_schema

    @property
    def total(self) -> int:
        return self.fixed_overhead + self.condition_specific


def _compose_task(
    client: TestClient,
    enc,
    task: dict[str, Any],
    *,
    tools_tokens: int,
    system_tokens: dict[str, int],
    image_per_step: int,
) -> list[StepComposition]:
    """Reconstruct the per-step input composition for C1(est)/C3/C4 on one task.

    C1 is an image-tiling estimate; C3/C4 observations are exact and server-side.
    C2 needs a live browser (its tree is not reconstructable here) and is
    therefore measured during the model runs, not in this deterministic path.
    """
    policy = POLICIES[task["id"]]
    rows: list[StepComposition] = []

    # C4: the view document is fetched before each decision (as in model_loop).
    sid4 = client.post("/agent/session").json()["session_id"]
    prior: list[str] = []
    for step, (name, arguments) in enumerate(policy, start=1):
        surface = client.get("/agent/surface", params={"session_id": sid4}).json()
        rows.append(
            StepComposition(
                task_id=task["id"],
                condition="C4",
                step=step,
                system_prompt=system_tokens["C4"],
                task_and_prior=count_tokens(enc, _header_text(task, prior)),
                observation=count_tokens(enc, surface),
                tools_schema=0,
            )
        )
        r = _act(client, sid4, name, arguments, enforce=True)
        prior.append(_prior_item(name, arguments))
        if r.status_code == 400:
            break

    # C3: previous tool result as the observation, plus the tool schema every call.
    sid3 = client.post("/agent/session").json()["session_id"]
    prior = []
    prev_payload: Any = {"status": "start"}
    for step, (name, arguments) in enumerate(policy, start=1):
        rows.append(
            StepComposition(
                task_id=task["id"],
                condition="C3",
                step=step,
                system_prompt=system_tokens["C3"],
                task_and_prior=count_tokens(enc, _header_text(task, prior)),
                observation=count_tokens(enc, prev_payload),
                tools_schema=tools_tokens,
            )
        )
        r = _act(client, sid3, name, arguments, enforce=False)
        prev_payload = r.json()
        prior.append(_prior_item(name, arguments))
        if r.status_code == 400:
            break

    # C1: image estimate as the observation; no backend calls needed. Steps and
    # history mirror the canonical path (a close approximation for C1's actual
    # coordinate-action history).
    prior = []
    for step, (name, arguments) in enumerate(policy, start=1):
        rows.append(
            StepComposition(
                task_id=task["id"],
                condition="C1(est)",
                step=step,
                system_prompt=system_tokens["C1"],
                task_and_prior=count_tokens(enc, _header_text(task, prior)),
                observation=image_per_step,
                tools_schema=0,
            )
        )
        prior.append(_prior_item(name, arguments))

    return rows


def measure_composition() -> list[StepComposition]:
    enc = _encoder()
    client = TestClient(app)
    tools_tokens = count_tokens(enc, tool_schemas())
    system_tokens = {cond: count_tokens(enc, system_prompt(cond)) for cond in ("C1", "C3", "C4")}
    image_per_step = image_tokens_high_detail(*VIEWPORT)
    rows: list[StepComposition] = []
    for task in load_tasks():
        if task.get("expect", "success") != "success":
            continue
        rows.extend(
            _compose_task(
                client,
                enc,
                task,
                tools_tokens=tools_tokens,
                system_tokens=system_tokens,
                image_per_step=image_per_step,
            )
        )
    return rows


CONDITION_ORDER = ("C1(est)", "C3", "C4")


def summarize_composition(rows: list[StepComposition]) -> dict[str, dict[str, float]]:
    """Median per-step token composition by condition, across success tasks."""
    out: dict[str, dict[str, float]] = {}
    for cond in CONDITION_ORDER:
        cond_rows = [r for r in rows if r.condition == cond]
        if not cond_rows:
            continue
        out[cond] = {
            "system_prompt": statistics.median(r.system_prompt for r in cond_rows),
            "task_and_prior": statistics.median(r.task_and_prior for r in cond_rows),
            "observation": statistics.median(r.observation for r in cond_rows),
            "tools_schema": statistics.median(r.tools_schema for r in cond_rows),
            "fixed_overhead": statistics.median(r.fixed_overhead for r in cond_rows),
            "condition_specific": statistics.median(r.condition_specific for r in cond_rows),
            "total": statistics.median(r.total for r in cond_rows),
        }
    return out


def composition_markdown(summary: dict[str, dict[str, float]]) -> str:
    lines = [
        "| condition | system | task+prior | tools schema | observation | fixed overhead | condition-specific | total |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for cond, m in summary.items():
        lines.append(
            f"| {cond} | {m['system_prompt']:.0f} | {m['task_and_prior']:.0f} | {m['tools_schema']:.0f} | "
            f"{m['observation']:.0f} | {m['fixed_overhead']:.0f} | {m['condition_specific']:.0f} | {m['total']:.0f} |"
        )
    return "\n".join(lines)


def write_composition_csv(rows: list[StepComposition], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["task_id", "condition", "step", "system_prompt", "task_and_prior", "tools_schema", "observation", "total"]
        )
        for r in rows:
            writer.writerow(
                [r.task_id, r.condition, r.step, r.system_prompt, r.task_and_prior, r.tools_schema, r.observation, r.total]
            )


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

    # C1 image-token estimate vs viewport resolution (high-detail tiling).
    res_rows = image_tokens_by_resolution()
    write_resolution_csv(res_rows, out / "image_tokens_by_resolution.csv")
    print("\nC1 image tokens vs viewport resolution (OpenAI gpt-4o high-detail estimate):")
    print(f"{'resolution':>12} {'scaled':>11} {'tiles':>6} {'high':>6} {'low':>5}")
    for r in res_rows:
        print(
            f"{r.width}x{r.height:<7} {r.scaled_width}x{r.scaled_height:<6} "
            f"{r.tiles:>6} {r.high_detail_tokens:>6} {r.low_detail_tokens:>5}"
        )
    print(f"Wrote {out / 'image_tokens_by_resolution.csv'}")

    # Per-condition per-step observation-token composition (success tasks).
    comp_rows = measure_composition()
    comp_summary = summarize_composition(comp_rows)
    write_composition_csv(comp_rows, out / "obs_composition.csv")
    print("\nPer-step input composition by condition (median over success-task steps):")
    print(composition_markdown(comp_summary))
    print(f"Wrote {out / 'obs_composition.csv'}")

    print(
        "\nNotes: C3/C4 exact and server-side; C1 is an OpenAI gpt-4o high-detail "
        "image estimate for the 1280x800 viewport (cost is a function of "
        "resolution/detail, not page content); C2 needs a browser and is measured "
        "during model runs. Counts use the o200k_base tokenizer."
    )


if __name__ == "__main__":
    main()
