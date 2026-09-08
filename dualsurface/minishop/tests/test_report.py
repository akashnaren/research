from __future__ import annotations

import json
from pathlib import Path

from harness.report import (
    aggregate,
    bootstrap_ci,
    build_report,
    load_results,
    markdown_ci_table,
    markdown_paired,
    markdown_table,
    paired_comparison,
    pareto_frontier,
)


def _result(
    model,
    condition,
    task_id,
    passed,
    steps,
    in_tok,
    out_tok,
    img_tok,
    illegal,
    *,
    malformed=0,
    expect="success",
    repeat=1,
):
    return {
        "type": "result",
        "condition": condition,
        "task_id": task_id,
        "expect": expect,
        "repeat": repeat,
        "model_alias": model,
        "passed": passed,
        "steps": steps,
        "illegal_actions": illegal,
        "malformed_actions": malformed,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "image_tokens": img_tok,
    }


SAMPLE = [
    # C4: cheap and reliable.
    _result("gpt-4o-mini", "C4", "t01", True, 6, 900, 40, 0, 0),
    _result("gpt-4o-mini", "C4", "t02", True, 6, 1100, 60, 0, 0),
    # C3: cheaper per step but more steps and one miss.
    _result("gpt-4o-mini", "C3", "t01", True, 8, 700, 50, 0, 1),
    _result("gpt-4o-mini", "C3", "t02", False, 20, 1500, 120, 0, 3),
    # C1: expensive (image tokens) and less reliable.
    _result("gpt-4o-mini", "C1", "t01", True, 9, 5000, 40, 4200, 2),
    _result("gpt-4o-mini", "C1", "t02", False, 20, 9000, 90, 8000, 5),
]


def test_aggregate_computes_success_and_medians():
    cells = {(c.model_alias, c.condition): c for c in aggregate(SAMPLE)}
    c4 = cells[("gpt-4o-mini", "C4")]
    assert c4.n == 2
    assert c4.success_rate == 1.0
    assert c4.median_input_tokens == 1000  # median(900, 1100)
    assert c4.median_steps == 6

    c3 = cells[("gpt-4o-mini", "C3")]
    assert c3.success_rate == 0.5
    # illegal actions per step: (1 + 3) / (8 + 20)
    assert abs(c3.illegal_rate - (4 / 28)) < 1e-9

    c1 = cells[("gpt-4o-mini", "C1")]
    assert c1.median_image_tokens == 6100  # median(4200, 8000)


def test_pareto_frontier_marks_efficient_points():
    cells = aggregate(SAMPLE)
    points = {(p.model_alias, p.condition): p for p in pareto_frontier(cells)}
    # C4 is cheapest (median 1000) and most reliable (100%): must be on frontier.
    assert points[("gpt-4o-mini", "C4")].on_frontier is True
    # C1 is both more expensive and less reliable than C4: dominated.
    assert points[("gpt-4o-mini", "C1")].on_frontier is False


def test_markdown_table_has_header_and_rows():
    cells = aggregate(SAMPLE)
    table = markdown_table(cells)
    assert "| model | cond | n | success |" in table
    # header + separator + one line per (model, condition) cell
    assert len(table.splitlines()) == 2 + len(cells)


def test_load_results_reads_only_result_rows(tmp_path: Path):
    trace = tmp_path / "run_C4_t01.jsonl"
    rows = [
        {"type": "run", "condition": "C4", "task_id": "t01"},
        {"type": "step", "step": 1},
        _result("m", "C4", "t01", True, 5, 800, 30, 0, 0),
    ]
    trace.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    loaded = load_results(tmp_path)
    assert len(loaded) == 1
    assert loaded[0]["type"] == "result"
    assert loaded[0]["input_tokens"] == 800


def test_build_report_writes_table_and_csv(tmp_path: Path):
    traces = tmp_path / "traces"
    traces.mkdir()
    for i, row in enumerate(SAMPLE):
        (traces / f"run_{i}.jsonl").write_text(
            json.dumps({"type": "run"}) + "\n" + json.dumps(row) + "\n"
        )
    out = tmp_path / "report"
    result = build_report(traces, out, figures=False)
    assert result["n_runs"] == len(SAMPLE)
    assert (out / "summary.md").exists()
    assert (out / "summary.csv").exists()
    assert "success_rate" in (out / "summary.csv").read_text()


# --- Repeated-run aggregation, bootstrap CI, and paired inference ----------


def test_bootstrap_ci_is_deterministic_and_brackets_statistic():
    import statistics

    values = [10.0, 12.0, 14.0, 9.0, 11.0, 13.0, 15.0, 8.0]
    lo1, hi1 = bootstrap_ci(values, statistics.fmean, n_boot=500, seed=42)
    lo2, hi2 = bootstrap_ci(values, statistics.fmean, n_boot=500, seed=42)
    # Same seed -> identical CI.
    assert (lo1, hi1) == (lo2, hi2)
    # A different seed generally shifts the endpoints.
    lo3, hi3 = bootstrap_ci(values, statistics.fmean, n_boot=500, seed=7)
    assert (lo1, hi1) != (lo3, hi3)
    # The interval brackets the sample mean and is ordered.
    mean = statistics.fmean(values)
    assert lo1 <= mean <= hi1
    assert lo1 <= hi1


def test_bootstrap_ci_constant_values_collapse_to_point():
    import statistics

    lo, hi = bootstrap_ci([5.0, 5.0, 5.0], statistics.median, n_boot=100, seed=1)
    assert lo == 5.0 and hi == 5.0


def _repeated_cell(model, condition, task_ids, per_task, *, expect="success"):
    """Build repeated result rows: per_task maps task_id -> (passed, in_tok, steps, repeats)."""
    rows = []
    for task_id in task_ids:
        passed, in_tok, steps, repeats = per_task[task_id]
        for rep in range(1, repeats + 1):
            rows.append(
                _result(
                    model,
                    condition,
                    task_id,
                    passed,
                    steps,
                    in_tok,
                    10,
                    0,
                    0,
                    expect=expect,
                    repeat=rep,
                )
            )
    return rows


def test_aggregate_malformed_rate_kept_separate_from_illegal():
    rows = [
        _result("m", "C2", "t01", True, 5, 1000, 20, 0, 2, malformed=1),
        _result("m", "C2", "t02", False, 5, 1000, 20, 0, 0, malformed=3),
    ]
    cell = {(c.model_alias, c.condition): c for c in aggregate(rows)}[("m", "C2")]
    # illegal/step = 2/10, malformed/step = 4/10, and they are distinct.
    assert abs(cell.illegal_rate - 0.2) < 1e-9
    assert abs(cell.malformed_rate - 0.4) < 1e-9


def test_aggregate_folds_repeats_and_attaches_cis():
    tasks = ["t01", "t02", "t03"]
    per_task = {"t01": (True, 1000, 6, 5), "t02": (True, 1100, 6, 5), "t03": (True, 900, 6, 5)}
    rows = _repeated_cell("m", "C4", tasks, per_task)
    cells = aggregate(rows, ci=True, n_boot=300, seed=123)
    c4 = {(c.model_alias, c.condition): c for c in cells}[("m", "C4")]
    # 3 tasks x 5 repeats = 15 task-repeat units.
    assert c4.n == 15
    assert c4.n_tasks == 3 and c4.n_repeats == 5
    assert c4.success_rate == 1.0
    # All runs passed, so the success CI collapses to [1, 1].
    assert c4.success_ci == (1.0, 1.0)
    # Input-token CI brackets the median (1000) and is ordered.
    assert c4.input_tokens_ci is not None
    lo, hi = c4.input_tokens_ci
    assert lo <= 1000 <= hi
    # Deterministic for a fixed seed.
    again = aggregate(rows, ci=True, n_boot=300, seed=123)
    assert again[0].input_tokens_ci == c4.input_tokens_ci


def test_paired_comparison_c4_minus_c3_input_tokens_and_success():
    tasks = ["t01", "t02", "t04"]
    # C4 costs a fixed +50 tokens per task vs C3; both succeed every repeat.
    c3 = _repeated_cell("m", "C3", tasks, {t: (True, 100, 5, 4) for t in tasks})
    c4 = _repeated_cell("m", "C4", tasks, {t: (True, 150, 5, 4) for t in tasks})
    comp = paired_comparison(c3 + c4, "m", base="C3", treat="C4", expect="success", n_boot=300, seed=5)
    assert comp.tasks == tasks
    # Per-task input-token diff is exactly +50 for every task -> CI collapses,
    # excludes zero (C4 is significantly more expensive here).
    in_diff = comp.diffs["input_tokens"]
    assert abs(in_diff.mean_diff - 50.0) < 1e-9
    assert in_diff.ci == (50.0, 50.0)
    assert in_diff.excludes_zero is True
    # Success is identical -> mean diff 0, CI collapses to 0, does not exclude 0.
    succ = comp.diffs["success"]
    assert succ.mean_diff == 0.0
    assert succ.ci == (0.0, 0.0)
    assert succ.excludes_zero is False


def test_paired_comparison_separates_success_and_refusal_tasks():
    succ_tasks = ["t01", "t02"]
    ref_tasks = ["t03", "t05"]
    c3 = _repeated_cell("m", "C3", succ_tasks, {t: (True, 100, 5, 3) for t in succ_tasks})
    c3 += _repeated_cell("m", "C3", ref_tasks, {t: (True, 40, 2, 3) for t in ref_tasks}, expect="refusal")
    c4 = _repeated_cell("m", "C4", succ_tasks, {t: (True, 120, 5, 3) for t in succ_tasks})
    c4 += _repeated_cell("m", "C4", ref_tasks, {t: (False, 60, 3, 3) for t in ref_tasks}, expect="refusal")
    rows = c3 + c4

    succ = paired_comparison(rows, "m", expect="success", n_boot=200, seed=9)
    ref = paired_comparison(rows, "m", expect="refusal", n_boot=200, seed=9)
    assert succ.tasks == succ_tasks
    assert ref.tasks == ref_tasks
    # Success tasks: C4 costs +20 tokens each.
    assert abs(succ.diffs["input_tokens"].mean_diff - 20.0) < 1e-9
    # Refusal tasks: C4 fails all -> success diff is -1 per task.
    assert abs(ref.diffs["success"].mean_diff - (-1.0)) < 1e-9
    assert ref.diffs["success"].excludes_zero is True


def test_markdown_ci_and_paired_tables_render():
    tasks = ["t01", "t02", "t03"]
    c3 = _repeated_cell("m", "C3", tasks, {t: (True, 100, 5, 3) for t in tasks})
    c4 = _repeated_cell("m", "C4", tasks, {t: (True, 150, 5, 3) for t in tasks})
    cells = aggregate(c3 + c4, ci=True, n_boot=100, seed=1)
    ci_table = markdown_ci_table(cells)
    assert "success 95% CI" in ci_table
    assert "malformed/step" in ci_table
    comp = paired_comparison(c3 + c4, "m", expect="success", n_boot=100, seed=1)
    paired = markdown_paired([comp])
    assert "C4 - C3" in paired
    assert "excludes 0?" in paired
