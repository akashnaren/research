"""Aggregate MiniShop model-loop traces into per-model x condition results.

The model loop (`harness.model_loop`) writes one JSONL trace per
(model, condition, task). This module reads those traces and produces the
two artifacts the pilot reports:

1. A per-(model, condition) summary table: success rate, median steps,
   median input/output/image tokens, and illegal-action rate. Following
   PROTOCOL.md, results are never pooled across models -- every row is a
   single (model, condition) cell.
2. A cost-reliability Pareto frontier over (model, condition) points, where
   the cost axis is median input tokens per task and the reliability axis is
   success rate. A point is on the frontier if no other point is both
   cheaper and at least as reliable.

Tables are emitted as Markdown and CSV. Figures (a Pareto scatter and a
grouped token bar chart) are emitted only when matplotlib is installed and
`--figures` is passed; the aggregation itself has no plotting dependency.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

RESULT_TYPE = "result"


@dataclass(frozen=True)
class Cell:
    """Aggregated metrics for one (model, condition) pair."""

    model_alias: str
    condition: str
    n: int
    success_rate: float
    median_steps: float
    median_input_tokens: float
    median_output_tokens: float
    median_image_tokens: float
    illegal_rate: float

    def as_row(self) -> dict[str, Any]:
        return {
            "model_alias": self.model_alias,
            "condition": self.condition,
            "n": self.n,
            "success_rate": round(self.success_rate, 4),
            "median_steps": round(self.median_steps, 2),
            "median_input_tokens": round(self.median_input_tokens, 1),
            "median_output_tokens": round(self.median_output_tokens, 1),
            "median_image_tokens": round(self.median_image_tokens, 1),
            "illegal_rate": round(self.illegal_rate, 4),
        }


def load_results(traces_dir: str | Path) -> list[dict[str, Any]]:
    """Read every ``*.jsonl`` trace and return its final ``result`` row.

    Each trace file is ``[run-header, *steps, result]``. Only the result row
    carries the per-run rollups this module needs, so we ignore the rest.
    """
    traces_dir = Path(traces_dir)
    results: list[dict[str, Any]] = []
    for path in sorted(traces_dir.glob("*.jsonl")):
        result: dict[str, Any] | None = None
        with path.open() as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("type") == RESULT_TYPE:
                    result = row
        if result is not None:
            results.append(result)
    return results


def _median(values: Iterable[float]) -> float:
    data = [float(v) for v in values if v is not None]
    return statistics.median(data) if data else 0.0


def aggregate(results: list[dict[str, Any]]) -> list[Cell]:
    """Collapse per-run result rows into (model, condition) cells.

    ``passed`` already encodes the correct per-task outcome for both
    success and refusal tasks (see ``minishop.grader``), so the success rate
    is simply the mean of ``passed`` over the runs in a cell.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in results:
        key = (str(row.get("model_alias") or row.get("model") or "?"), str(row.get("condition") or "?"))
        groups.setdefault(key, []).append(row)

    cells: list[Cell] = []
    for (model_alias, condition), rows in sorted(groups.items()):
        n = len(rows)
        passed = sum(1 for r in rows if r.get("passed"))
        illegal_total = sum(int(r.get("illegal_actions") or 0) for r in rows)
        step_total = sum(int(r.get("steps") or 0) for r in rows)
        cells.append(
            Cell(
                model_alias=model_alias,
                condition=condition,
                n=n,
                success_rate=passed / n if n else 0.0,
                median_steps=_median(r.get("steps") for r in rows),
                median_input_tokens=_median(r.get("input_tokens") for r in rows),
                median_output_tokens=_median(r.get("output_tokens") for r in rows),
                median_image_tokens=_median(r.get("image_tokens") for r in rows),
                # Illegal actions per step: a rate that is comparable across
                # conditions with different step counts.
                illegal_rate=(illegal_total / step_total) if step_total else 0.0,
            )
        )
    return cells


@dataclass
class ParetoPoint:
    model_alias: str
    condition: str
    cost: float  # median input tokens (lower is better)
    reliability: float  # success rate (higher is better)
    on_frontier: bool = field(default=False)


def pareto_frontier(cells: list[Cell]) -> list[ParetoPoint]:
    """Mark the cost-reliability efficient frontier.

    A point is dominated when another point is no more costly and at least as
    reliable, with a strict advantage on at least one axis. Non-dominated
    points form the frontier: the cheapest representation for each reliability
    level (and vice versa).
    """
    points = [
        ParetoPoint(c.model_alias, c.condition, c.median_input_tokens, c.success_rate)
        for c in cells
    ]
    for p in points:
        dominated = False
        for q in points:
            if q is p:
                continue
            no_worse = q.cost <= p.cost and q.reliability >= p.reliability
            strictly_better = q.cost < p.cost or q.reliability > p.reliability
            if no_worse and strictly_better:
                dominated = True
                break
        p.on_frontier = not dominated
    return points


def markdown_table(cells: list[Cell]) -> str:
    headers = [
        "model",
        "cond",
        "n",
        "success",
        "med_steps",
        "med_in_tok",
        "med_out_tok",
        "med_img_tok",
        "illegal/step",
    ]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for c in cells:
        lines.append(
            "| "
            + " | ".join(
                [
                    c.model_alias,
                    c.condition,
                    str(c.n),
                    f"{c.success_rate:.0%}",
                    f"{c.median_steps:g}",
                    f"{c.median_input_tokens:g}",
                    f"{c.median_output_tokens:g}",
                    f"{c.median_image_tokens:g}",
                    f"{c.illegal_rate:.3f}",
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def write_csv(cells: list[Cell], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "model_alias",
        "condition",
        "n",
        "success_rate",
        "median_steps",
        "median_input_tokens",
        "median_output_tokens",
        "median_image_tokens",
        "illegal_rate",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for c in cells:
            writer.writerow(c.as_row())


def write_figures(cells: list[Cell], out_dir: str | Path) -> list[Path]:
    """Emit a Pareto scatter and a token bar chart if matplotlib is present.

    Returns the paths written. Raises ``RuntimeError`` if matplotlib is not
    installed so the CLI can report a clear message rather than a traceback.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - exercised only without mpl
        raise RuntimeError(
            "matplotlib is required for --figures. Install it: pip install matplotlib"
        ) from exc

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    points = pareto_frontier(cells)
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for p in points:
        marker = "o" if p.on_frontier else "x"
        ax.scatter(p.cost, p.reliability, marker=marker)
        ax.annotate(f"{p.model_alias}/{p.condition}", (p.cost, p.reliability), fontsize=7,
                    xytext=(4, 4), textcoords="offset points")
    frontier = sorted([p for p in points if p.on_frontier], key=lambda p: p.cost)
    if len(frontier) > 1:
        ax.plot([p.cost for p in frontier], [p.reliability for p in frontier], linestyle="--")
    ax.set_xlabel("median input tokens per task (lower is better)")
    ax.set_ylabel("success rate (higher is better)")
    ax.set_title("Cost-reliability frontier by (model, condition)")
    fig.tight_layout()
    pareto_path = out_dir / "pareto.png"
    fig.savefig(pareto_path, dpi=150)
    plt.close(fig)
    written.append(pareto_path)

    conditions = sorted({c.condition for c in cells})
    models = sorted({c.model_alias for c in cells})
    fig, ax = plt.subplots(figsize=(6, 4.5))
    width = 0.8 / max(len(models), 1)
    for i, model in enumerate(models):
        xs = range(len(conditions))
        heights = []
        for cond in conditions:
            match = next((c for c in cells if c.model_alias == model and c.condition == cond), None)
            heights.append(match.median_input_tokens if match else 0)
        ax.bar([x + i * width for x in xs], heights, width=width, label=model)
    ax.set_xticks([x + (len(models) - 1) * width / 2 for x in range(len(conditions))])
    ax.set_xticklabels(conditions)
    ax.set_ylabel("median input tokens per task")
    ax.set_title("Input-token cost by condition")
    ax.legend(fontsize=7)
    fig.tight_layout()
    bars_path = out_dir / "input_tokens.png"
    fig.savefig(bars_path, dpi=150)
    plt.close(fig)
    written.append(bars_path)

    return written


def build_report(traces_dir: str | Path, out_dir: str | Path, figures: bool = False) -> dict[str, Any]:
    results = load_results(traces_dir)
    cells = aggregate(results)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    table_md = markdown_table(cells)
    (out_dir / "summary.md").write_text(table_md + "\n")
    write_csv(cells, out_dir / "summary.csv")

    figure_paths: list[Path] = []
    if figures:
        figure_paths = write_figures(cells, out_dir)

    return {"n_runs": len(results), "cells": cells, "figures": figure_paths, "out_dir": out_dir}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Aggregate MiniShop traces into tables and figures")
    parser.add_argument("--traces", default="traces", help="Directory of *.jsonl traces")
    parser.add_argument("--out", default="report", help="Output directory for tables/figures")
    parser.add_argument("--figures", action="store_true", help="Also render PNG figures (needs matplotlib)")
    args = parser.parse_args(argv)

    report = build_report(args.traces, args.out, figures=args.figures)
    if report["n_runs"] == 0:
        print(f"No result rows found in {args.traces}/*.jsonl. Run harness.model_loop first.")
        return
    print(f"Aggregated {report['n_runs']} runs into {len(report['cells'])} (model, condition) cells.")
    print(markdown_table(report["cells"]))
    print(f"\nWrote {report['out_dir']}/summary.md and summary.csv")
    for path in report["figures"]:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
