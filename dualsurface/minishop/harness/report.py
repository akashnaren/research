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
import math
import random
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

RESULT_TYPE = "result"

# Bootstrap defaults. A fixed seed makes every reported confidence interval
# deterministic and reproducible from the same traces.
DEFAULT_SEED = 20260908
DEFAULT_N_BOOT = 2000


def _percentile(sorted_vals: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile of an already-sorted sequence.

    ``q`` is a fraction in ``[0, 1]``. Returns NaN for an empty input.
    """
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    idx = q * (len(sorted_vals) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return float(sorted_vals[lo])
    frac = idx - lo
    return float(sorted_vals[lo]) * (1 - frac) + float(sorted_vals[hi]) * frac


def bootstrap_ci(
    values: Sequence[float],
    statistic: Callable[[Sequence[float]], float],
    *,
    n_boot: int = DEFAULT_N_BOOT,
    seed: int = DEFAULT_SEED,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Percentile bootstrap confidence interval for ``statistic(values)``.

    Resamples ``values`` with replacement ``n_boot`` times, applies
    ``statistic`` to each resample, and returns the ``(alpha/2, 1-alpha/2)``
    percentiles of the resampled statistics. Deterministic for a fixed
    ``seed``. Returns ``(nan, nan)`` for empty input.
    """
    data = [float(v) for v in values]
    if not data:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(data)
    stats: list[float] = []
    for _ in range(n_boot):
        sample = [data[rng.randrange(n)] for _ in range(n)]
        stats.append(float(statistic(sample)))
    stats.sort()
    return (_percentile(stats, alpha / 2), _percentile(stats, 1 - alpha / 2))


def _mean(values: Sequence[float]) -> float:
    return statistics.fmean(values) if values else 0.0


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
    # Malformed model responses per step (non-object output the loop had to
    # treat as a no-op). Distinct from illegal_rate (backend rejections).
    malformed_rate: float = 0.0
    # Number of distinct tasks and repeats-per-task folded into this cell.
    n_tasks: int = 0
    n_repeats: int = 0
    # Bootstrap 95% CIs (None on single-pass / when CIs are not requested).
    success_ci: tuple[float, float] | None = None
    input_tokens_ci: tuple[float, float] | None = None

    def as_row(self) -> dict[str, Any]:
        return {
            "model_alias": self.model_alias,
            "condition": self.condition,
            "n": self.n,
            "success_rate": round(self.success_rate, 4),
            "success_ci_lo": _round_or_none(self.success_ci[0] if self.success_ci else None, 4),
            "success_ci_hi": _round_or_none(self.success_ci[1] if self.success_ci else None, 4),
            "median_steps": round(self.median_steps, 2),
            "median_input_tokens": round(self.median_input_tokens, 1),
            "input_tokens_ci_lo": _round_or_none(self.input_tokens_ci[0] if self.input_tokens_ci else None, 1),
            "input_tokens_ci_hi": _round_or_none(self.input_tokens_ci[1] if self.input_tokens_ci else None, 1),
            "median_output_tokens": round(self.median_output_tokens, 1),
            "median_image_tokens": round(self.median_image_tokens, 1),
            "illegal_rate": round(self.illegal_rate, 4),
            "malformed_rate": round(self.malformed_rate, 4),
        }


def _round_or_none(value: float | None, ndigits: int) -> float | None:
    return None if value is None else round(value, ndigits)


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


def _model_key(row: dict[str, Any]) -> str:
    return str(row.get("model_alias") or row.get("model") or "?")


def aggregate(
    results: list[dict[str, Any]],
    *,
    ci: bool = False,
    n_boot: int = DEFAULT_N_BOOT,
    seed: int = DEFAULT_SEED,
) -> list[Cell]:
    """Collapse per-run result rows into (model, condition) cells.

    ``passed`` already encodes the correct per-task outcome for both
    success and refusal tasks (see ``minishop.grader``), so the success rate
    is simply the mean of ``passed`` over the runs in a cell. Each run row is
    one task-repeat unit; a cell folds together every repeat of every task for
    that (model, condition).

    When ``ci`` is True, a percentile bootstrap 95% CI is attached to the
    success rate and to the median input tokens, resampling over the cell's
    task-repeat units with a fixed ``seed`` (so the CIs are reproducible).
    Single-pass callers can leave ``ci`` False; the CI fields stay ``None``.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in results:
        key = (_model_key(row), str(row.get("condition") or "?"))
        groups.setdefault(key, []).append(row)

    cells: list[Cell] = []
    for (model_alias, condition), rows in sorted(groups.items()):
        n = len(rows)
        passed = sum(1 for r in rows if r.get("passed"))
        illegal_total = sum(int(r.get("illegal_actions") or 0) for r in rows)
        malformed_total = sum(int(r.get("malformed_actions") or 0) for r in rows)
        step_total = sum(int(r.get("steps") or 0) for r in rows)
        tasks = {str(r.get("task_id")) for r in rows if r.get("task_id") is not None}
        repeats = {int(r.get("repeat") or 1) for r in rows}

        success_ci: tuple[float, float] | None = None
        input_tokens_ci: tuple[float, float] | None = None
        if ci and n:
            passed_units = [1.0 if r.get("passed") else 0.0 for r in rows]
            in_tok_units = [float(r.get("input_tokens") or 0) for r in rows]
            success_ci = bootstrap_ci(passed_units, statistics.fmean, n_boot=n_boot, seed=seed)
            input_tokens_ci = bootstrap_ci(in_tok_units, statistics.median, n_boot=n_boot, seed=seed)

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
                # Illegal actions per step: a rate comparable across conditions
                # with different step counts.
                illegal_rate=(illegal_total / step_total) if step_total else 0.0,
                # Malformed responses per step: honest formatting-failure rate,
                # kept separate from backend rejections (illegal_rate).
                malformed_rate=(malformed_total / step_total) if step_total else 0.0,
                n_tasks=len(tasks),
                n_repeats=len(repeats),
                success_ci=success_ci,
                input_tokens_ci=input_tokens_ci,
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


PAIRED_METRICS = ("success", "input_tokens", "steps")


def _per_task_means(
    results: list[dict[str, Any]],
    model_alias: str,
    condition: str,
    expect: str | None = None,
) -> dict[str, dict[str, float]]:
    """Average each per-task outcome over that task's repeats for one cell.

    Returns ``task_id -> {"success", "input_tokens", "steps"}`` where each
    value is the mean over the task's repeats. ``expect`` optionally restricts
    to ``"success"`` or ``"refusal"`` tasks (per PROTOCOL/plan, these are
    reported separately so refusal-by-inaction cannot inflate the headline).
    """
    rows = [
        r
        for r in results
        if _model_key(r) == model_alias
        and str(r.get("condition") or "") == condition
        and (expect is None or str(r.get("expect") or "") == expect)
    ]
    by_task: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_task.setdefault(str(r.get("task_id")), []).append(r)

    out: dict[str, dict[str, float]] = {}
    for task_id, task_rows in by_task.items():
        out[task_id] = {
            "success": _mean([1.0 if r.get("passed") else 0.0 for r in task_rows]),
            "input_tokens": _mean([float(r.get("input_tokens") or 0) for r in task_rows]),
            "steps": _mean([float(r.get("steps") or 0) for r in task_rows]),
        }
    return out


@dataclass
class PairedDiff:
    metric: str
    n_tasks: int
    mean_diff: float
    ci: tuple[float, float]

    @property
    def excludes_zero(self) -> bool:
        lo, hi = self.ci
        if math.isnan(lo) or math.isnan(hi):
            return False
        return lo > 0.0 or hi < 0.0


@dataclass
class PairedComparison:
    model_alias: str
    base: str
    treat: str
    expect: str
    tasks: list[str]
    diffs: dict[str, PairedDiff]


def paired_comparison(
    results: list[dict[str, Any]],
    model_alias: str,
    *,
    base: str = "C3",
    treat: str = "C4",
    expect: str = "success",
    n_boot: int = DEFAULT_N_BOOT,
    seed: int = DEFAULT_SEED,
) -> PairedComparison:
    """Paired per-task ``treat`` minus ``base`` comparison (default C4 - C3).

    For each task shared by both conditions, average the outcome over repeats
    under each condition, take the paired difference (treat - base), and report
    the mean paired difference with a bootstrap 95% CI resampled over the
    tasks. ``expect`` selects success vs refusal tasks; they are reported
    separately.
    """
    base_means = _per_task_means(results, model_alias, base, expect)
    treat_means = _per_task_means(results, model_alias, treat, expect)
    tasks = sorted(set(base_means) & set(treat_means))

    diffs: dict[str, PairedDiff] = {}
    for metric in PAIRED_METRICS:
        per_task = [treat_means[t][metric] - base_means[t][metric] for t in tasks]
        mean_diff = _mean(per_task) if per_task else float("nan")
        ci = bootstrap_ci(per_task, statistics.fmean, n_boot=n_boot, seed=seed) if per_task else (
            float("nan"),
            float("nan"),
        )
        diffs[metric] = PairedDiff(metric=metric, n_tasks=len(tasks), mean_diff=mean_diff, ci=ci)

    return PairedComparison(
        model_alias=model_alias,
        base=base,
        treat=treat,
        expect=expect,
        tasks=tasks,
        diffs=diffs,
    )


def _fmt_ci(ci: tuple[float, float] | None, fmt: str = "g") -> str:
    if ci is None:
        return "-"
    lo, hi = ci
    if math.isnan(lo) or math.isnan(hi):
        return "-"
    return f"[{format(lo, fmt)}, {format(hi, fmt)}]"


def markdown_ci_table(cells: list[Cell]) -> str:
    """Repeated-run table with bootstrap CIs on success and input tokens."""
    headers = [
        "model",
        "cond",
        "n",
        "tasks×reps",
        "success",
        "success 95% CI",
        "med_in_tok",
        "in_tok 95% CI",
        "illegal/step",
        "malformed/step",
    ]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for c in cells:
        reps = f"{c.n_tasks}×{c.n_repeats}" if c.n_tasks else str(c.n)
        success_ci = "-" if c.success_ci is None else _fmt_ci((c.success_ci[0], c.success_ci[1]), ".0%")
        in_ci = _fmt_ci(c.input_tokens_ci, "g") if c.input_tokens_ci else "-"
        lines.append(
            "| "
            + " | ".join(
                [
                    c.model_alias,
                    c.condition,
                    str(c.n),
                    reps,
                    f"{c.success_rate:.0%}",
                    success_ci,
                    f"{c.median_input_tokens:g}",
                    in_ci,
                    f"{c.illegal_rate:.3f}",
                    f"{c.malformed_rate:.3f}",
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def markdown_paired(comparisons: list[PairedComparison]) -> str:
    """Render paired treat-vs-base differences (mean + 95% CI, excludes 0?)."""
    if not comparisons:
        return ""
    headers = [
        "model",
        "compare",
        "task set",
        "n_tasks",
        "metric",
        "mean diff (treat - base)",
        "95% CI",
        "excludes 0?",
    ]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for comp in comparisons:
        for metric in PAIRED_METRICS:
            d = comp.diffs[metric]
            fmt = ".3f" if metric == "success" else "g"
            lines.append(
                "| "
                + " | ".join(
                    [
                        comp.model_alias,
                        f"{comp.treat} - {comp.base}",
                        comp.expect,
                        str(d.n_tasks),
                        metric,
                        format(d.mean_diff, fmt) if not math.isnan(d.mean_diff) else "-",
                        _fmt_ci(d.ci, fmt),
                        "yes" if d.excludes_zero else "no",
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


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
        "malformed/step",
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
                    f"{c.malformed_rate:.3f}",
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
        "success_ci_lo",
        "success_ci_hi",
        "median_steps",
        "median_input_tokens",
        "input_tokens_ci_lo",
        "input_tokens_ci_hi",
        "median_output_tokens",
        "median_image_tokens",
        "illegal_rate",
        "malformed_rate",
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
    cell_by_key = {(c.model_alias, c.condition): c for c in cells}
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for p in points:
        marker = "o" if p.on_frontier else "x"
        cell = cell_by_key.get((p.model_alias, p.condition))
        xerr = yerr = None
        if cell is not None and cell.input_tokens_ci is not None:
            lo, hi = cell.input_tokens_ci
            xerr = [[max(p.cost - lo, 0.0)], [max(hi - p.cost, 0.0)]]
        if cell is not None and cell.success_ci is not None:
            lo, hi = cell.success_ci
            yerr = [[max(p.reliability - lo, 0.0)], [max(hi - p.reliability, 0.0)]]
        if xerr is not None or yerr is not None:
            ax.errorbar(p.cost, p.reliability, xerr=xerr, yerr=yerr, fmt=marker,
                        elinewidth=0.8, capsize=2, alpha=0.8)
        else:
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


def write_paired_figure(
    results: list[dict[str, Any]],
    model_alias: str,
    out_dir: str | Path,
    *,
    base: str = "C3",
    treat: str = "C4",
    seed: int = DEFAULT_SEED,
) -> Path | None:
    """Draw per-task input-token differences (treat - base) for success tasks.

    Returns the path written, or ``None`` if there is no paired data to plot.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - exercised only without mpl
        raise RuntimeError(
            "matplotlib is required for --figures. Install it: pip install matplotlib"
        ) from exc

    base_means = _per_task_means(results, model_alias, base, "success")
    treat_means = _per_task_means(results, model_alias, treat, "success")
    tasks = sorted(set(base_means) & set(treat_means))
    if not tasks:
        return None

    comp = paired_comparison(results, model_alias, base=base, treat=treat, expect="success", seed=seed)
    in_diff = comp.diffs["input_tokens"]
    per_task = [treat_means[t]["input_tokens"] - base_means[t]["input_tokens"] for t in tasks]

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    colors = ["tab:red" if d > 0 else "tab:green" for d in per_task]
    ax.bar(range(len(tasks)), per_task, color=colors, alpha=0.8)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.axhline(in_diff.mean_diff, color="tab:blue", linestyle="--", linewidth=1.0,
               label=f"mean diff {in_diff.mean_diff:.0f}")
    lo, hi = in_diff.ci
    if not (math.isnan(lo) or math.isnan(hi)):
        ax.axhspan(lo, hi, color="tab:blue", alpha=0.12, label=f"95% CI [{lo:.0f}, {hi:.0f}]")
    ax.set_xticks(range(len(tasks)))
    ax.set_xticklabels(tasks, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel(f"input tokens: {treat} - {base} (per task, mean over repeats)")
    ax.set_title(f"Paired {treat} vs {base} input-token difference ({model_alias}, success tasks)")
    ax.legend(fontsize=7)
    fig.tight_layout()
    path = out_dir / "c3_c4_paired.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _models_with_pair(cells: list[Cell], base: str = "C3", treat: str = "C4") -> list[str]:
    by_model: dict[str, set[str]] = {}
    for c in cells:
        by_model.setdefault(c.model_alias, set()).add(c.condition)
    return sorted(m for m, conds in by_model.items() if base in conds and treat in conds)


def build_report(
    traces_dir: str | Path,
    out_dir: str | Path,
    figures: bool = False,
    *,
    seed: int = DEFAULT_SEED,
    n_boot: int = DEFAULT_N_BOOT,
) -> dict[str, Any]:
    results = load_results(traces_dir)
    cells = aggregate(results, ci=True, n_boot=n_boot, seed=seed)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Paired C4-vs-C3 comparison per model that ran both conditions, reported
    # separately for success and refusal tasks (PROTOCOL/plan Section 8).
    comparisons: list[PairedComparison] = []
    for model_alias in _models_with_pair(cells):
        for expect in ("success", "refusal"):
            comp = paired_comparison(
                results, model_alias, base="C3", treat="C4", expect=expect, n_boot=n_boot, seed=seed
            )
            if comp.tasks:
                comparisons.append(comp)

    table_md = markdown_table(cells)
    ci_md = markdown_ci_table(cells)
    paired_md = markdown_paired(comparisons)

    doc = ["## Per-(model, condition) summary\n", table_md, ""]
    doc += ["\n## Repeated-run aggregation with bootstrap 95% CIs\n", ci_md, ""]
    if paired_md:
        doc += ["\n## Paired C4-vs-C3 per-task differences (treat - base)\n", paired_md, ""]
    (out_dir / "summary.md").write_text("\n".join(doc) + "\n")
    write_csv(cells, out_dir / "summary.csv")

    figure_paths: list[Path] = []
    if figures:
        figure_paths = write_figures(cells, out_dir)
        for model_alias in _models_with_pair(cells):
            paired_fig = write_paired_figure(results, model_alias, out_dir, seed=seed)
            if paired_fig is not None:
                figure_paths.append(paired_fig)

    return {
        "n_runs": len(results),
        "cells": cells,
        "comparisons": comparisons,
        "figures": figure_paths,
        "out_dir": out_dir,
    }


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
    print("\n" + markdown_ci_table(report["cells"]))
    paired_md = markdown_paired(report["comparisons"])
    if paired_md:
        print("\nPaired C4-vs-C3 per-task differences (treat - base):")
        print(paired_md)
    print(f"\nWrote {report['out_dir']}/summary.md and summary.csv")
    for path in report["figures"]:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
