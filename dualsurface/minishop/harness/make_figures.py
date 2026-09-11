"""Render the token-accounting figures from the deterministic obs_cost data.

Two figures are produced (PNG):

- ``image_tokens_vs_resolution.png`` -- the C1 screenshot's estimated image
  tokens as a function of viewport resolution, under the OpenAI gpt-4o
  high-detail tiling model, with the flat low-detail cost for contrast. This
  makes the central point visible: image-token cost tracks *resolution/detail*,
  not the visual complexity or information content of the page.
- ``token_composition_by_condition.png`` -- a stacked bar of the per-step input
  composition for each condition, splitting fixed overhead (system prompt, task
  text, prior actions) from the condition-specific part (the tool schema on C3,
  the view document on C4, the image estimate on C1). C1(est)/C3/C4 are
  reconstructed deterministically; C2's accessibility tree needs a live browser,
  so its bar is measured from the recorded run traces when they are available.

Figures are written to ``--out`` (default ``/opt/cursor/artifacts``). Nothing is
billed and no model is called.
"""

from __future__ import annotations

import argparse
import glob
import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from harness.obs_cost import (
    _encoder,
    count_tokens,
    image_tokens_by_resolution,
    measure_composition,
    summarize_composition,
)
from harness.prompts import system_prompt

ROOT = Path(__file__).resolve().parent.parent
TRACES = ROOT / "traces"

# Consistent colors for the composition stack.
COLORS = {
    "system_prompt": "#8da0cb",
    "task_and_prior": "#a6d854",
    "tools_schema": "#ffd92f",
    "observation": "#fc8d62",
}
COMPONENT_LABELS = {
    "system_prompt": "system prompt",
    "task_and_prior": "task + prior actions",
    "tools_schema": "tool schema (C3)",
    "observation": "condition observation",
}


def image_tokens_figure(out: Path) -> Path:
    rows = image_tokens_by_resolution()
    labels = [f"{r.width}x{r.height}" for r in rows]
    highs = [r.high_detail_tokens for r in rows]
    lows = [r.low_detail_tokens for r in rows]
    tiles = [r.tiles for r in rows]

    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    x = range(len(rows))
    ax.plot(x, highs, "-o", color="#fc8d62", linewidth=2, markersize=7, label="high detail (tiled)")
    ax.plot(x, lows, "--s", color="#8da0cb", linewidth=2, markersize=6, label="low detail (flat)")
    for xi, (h, t) in enumerate(zip(highs, tiles)):
        ax.annotate(f"{h} tok\n{t} tiles", (xi, h), textcoords="offset points", xytext=(0, 10),
                    ha="center", fontsize=8, color="#7f3b1f")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_xlabel("viewport resolution (CSS px)")
    ax.set_ylabel("estimated image tokens")
    ax.set_title("C1 screenshot cost is a function of resolution/detail, not page content\n"
                 "(OpenAI gpt-4o tiling estimate: 85 + 170/tile)")
    ax.set_ylim(0, max(highs) * 1.25)
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper left")
    fig.tight_layout()
    path = out / "image_tokens_vs_resolution.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _c2_from_traces(enc) -> dict[str, float] | None:
    """Median per-step C2 composition from recorded traces (measured, optional).

    Returns None if no C2 traces are present (they are gitignored). The tree is
    measured; the fixed-overhead terms reuse the deterministic system prompt and
    an approximate task+prior header consistent with the other bars.
    """
    files = sorted(glob.glob(str(TRACES / "*_C2_t*_rep*.jsonl")))
    if not files:
        return None
    tree_tokens: list[int] = []
    for path in files:
        try:
            lines = [json.loads(line) for line in open(path)]
        except (OSError, json.JSONDecodeError):
            continue
        # Skip refusal tasks so the comparison matches the deterministic set.
        header = next((l for l in lines if l.get("type") == "run"), {})
        if header.get("task_id") in {"t03", "t05", "t07"}:
            continue
        for row in lines:
            if row.get("type") != "step":
                continue
            obs = row.get("observation") or {}
            tree = obs.get("tree") if isinstance(obs, dict) else None
            if isinstance(tree, str) and tree:
                tree_tokens.append(count_tokens(enc, tree))
    if not tree_tokens:
        return None
    system = count_tokens(enc, system_prompt("C2"))
    return {
        "system_prompt": float(system),
        "task_and_prior": 62.0,  # matches the deterministic header estimate
        "tools_schema": 0.0,
        "observation": float(statistics.median(tree_tokens)),
    }


def composition_figure(out: Path) -> Path:
    summary = summarize_composition(measure_composition())
    enc = _encoder()

    order = ["C1(est)", "C2*", "C3", "C4"]
    data: dict[str, dict[str, float]] = {}
    c2 = _c2_from_traces(enc)
    for cond in order:
        if cond == "C2*":
            if c2 is not None:
                data[cond] = c2
            continue
        data[cond] = summary[cond]

    conds = list(data)
    components = ["system_prompt", "task_and_prior", "tools_schema", "observation"]

    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    bottoms = [0.0] * len(conds)
    for comp in components:
        vals = [data[c].get(comp, 0.0) for c in conds]
        ax.bar(conds, vals, bottom=bottoms, color=COLORS[comp], label=COMPONENT_LABELS[comp],
               edgecolor="white", linewidth=0.6)
        bottoms = [b + v for b, v in zip(bottoms, vals)]
    for xi, c in enumerate(conds):
        ax.annotate(f"{bottoms[xi]:.0f}", (xi, bottoms[xi]), textcoords="offset points",
                    xytext=(0, 4), ha="center", fontsize=9, fontweight="bold")

    ax.set_ylabel("median per-step input tokens")
    note = "C2* measured from run traces" if c2 is not None else "C2 needs a live browser (omitted)"
    ax.set_title("Per-step input composition by condition\n"
                 f"(C1(est)/C3/C4 deterministic; {note}; o200k_base tokenizer)")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    path = out / "token_composition_by_condition.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Render token-accounting figures (no model)")
    parser.add_argument("--out", default="/opt/cursor/artifacts", help="Output directory for PNGs")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    p1 = image_tokens_figure(out)
    p2 = composition_figure(out)
    print(f"wrote {p1}")
    print(f"wrote {p2}")


if __name__ == "__main__":
    main()
