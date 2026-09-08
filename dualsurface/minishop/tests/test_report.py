from __future__ import annotations

import json
from pathlib import Path

from harness.report import (
    aggregate,
    build_report,
    load_results,
    markdown_table,
    pareto_frontier,
)


def _result(model, condition, task_id, passed, steps, in_tok, out_tok, img_tok, illegal):
    return {
        "type": "result",
        "condition": condition,
        "task_id": task_id,
        "model_alias": model,
        "passed": passed,
        "steps": steps,
        "illegal_actions": illegal,
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
