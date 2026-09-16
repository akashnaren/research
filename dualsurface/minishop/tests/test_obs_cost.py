from __future__ import annotations

import pytest

from harness.obs_cost import (
    CONDITION_ORDER,
    RESOLUTION_SWEEP,
    VIEWPORT,
    count_tokens,
    find_c4_over_c3_crossover,
    image_tokens_by_resolution,
    image_tokens_high_detail,
    image_tokens_low_detail,
    list_products_tokens,
    measure_all,
    measure_catalog_sweep,
    measure_composition,
    summarize,
    summarize_catalog_sweep,
    summarize_composition,
    synthetic_catalog,
    tile_geometry,
    _encoder,
)
from minishop.catalog import in_stock_sizes, load_catalog


def test_image_tokens_high_detail_for_viewport():
    # 1280x800 high-detail: shortest side scaled to 768 -> 1229x768 -> 3x2 tiles.
    assert image_tokens_high_detail(1280, 800) == 85 + 170 * 6


def test_count_tokens_is_positive_and_monotonic():
    enc = _encoder()
    short = count_tokens(enc, {"status": "ok"})
    long = count_tokens(enc, {"status": "ok", "note": "a much longer payload " * 20})
    assert short > 0
    assert long > short


def test_measure_all_returns_a_row_per_task():
    costs = measure_all()
    assert len(costs) == 10
    for c in costs:
        assert c.steps >= 1
        # Every condition has a positive per-task observation cost.
        assert c.c1_obs_tokens > 0
        assert c.c3_obs_tokens > 0
        assert c.c4_obs_tokens > 0


def test_c4_and_c3_are_cheaper_than_the_c1_image_estimate():
    """The headline direction: text observations cost far less than screenshots."""
    costs = measure_all()
    summary = summarize(costs, only_success=True)
    assert summary["C4"]["median_obs_tokens_per_step"] < summary["C1(est)"]["median_obs_tokens_per_step"]
    assert summary["C3"]["median_obs_tokens_per_step"] < summary["C1(est)"]["median_obs_tokens_per_step"]


# --- Image-token resolution sweep ------------------------------------------


def test_tile_geometry_known_viewport():
    # 1280x800: shortest side scaled to 768 -> ~1229x768 -> 3x2 = 6 tiles.
    sw, sh, tiles = tile_geometry(1280, 800)
    assert tiles == 6
    assert round(sh) == 768
    assert 1220 <= sw <= 1235


def test_low_detail_is_flat_and_independent_of_resolution():
    assert image_tokens_low_detail() == 85
    small = image_tokens_by_resolution([(320, 240)])[0]
    large = image_tokens_by_resolution([(3840, 2160)])[0]
    assert small.low_detail_tokens == large.low_detail_tokens == 85


def test_resolution_sweep_is_monotonic_non_decreasing():
    rows = image_tokens_by_resolution()
    assert [ (r.width, r.height) for r in rows ] == list(RESOLUTION_SWEEP)
    highs = [r.high_detail_tokens for r in rows]
    assert highs == sorted(highs)  # monotonic non-decreasing as resolution grows
    assert highs[0] < highs[-1]  # cost does rise across the full sweep


def test_sweep_high_detail_matches_tiling_formula():
    for r in image_tokens_by_resolution():
        assert r.high_detail_tokens == image_tokens_high_detail(r.width, r.height)
        assert r.high_detail_tokens == 85 + 170 * r.tiles


def test_image_cost_is_resolution_driven_not_content_driven():
    """Two different pages at the same viewport cost the same image tokens."""
    a = image_tokens_high_detail(*VIEWPORT)
    b = image_tokens_high_detail(*VIEWPORT)
    assert a == b == 85 + 170 * 6


# --- Per-condition observation composition ---------------------------------


def test_composition_rows_split_into_fixed_and_specific():
    rows = measure_composition()
    assert rows
    for r in rows:
        assert r.total == r.fixed_overhead + r.condition_specific
        assert r.fixed_overhead == r.system_prompt + r.task_and_prior
        assert r.condition_specific == r.observation + r.tools_schema
        assert r.system_prompt > 0
        assert r.task_and_prior > 0


def test_only_c3_pays_the_tool_schema_every_step():
    rows = measure_composition()
    for r in rows:
        if r.condition == "C3":
            assert r.tools_schema > 0
        else:
            assert r.tools_schema == 0


def test_c1_observation_is_the_image_estimate():
    image = image_tokens_high_detail(*VIEWPORT)
    c1 = [r for r in measure_composition() if r.condition == "C1(est)"]
    assert c1
    assert all(r.observation == image for r in c1)


def test_summarize_composition_covers_the_deterministic_conditions():
    summary = summarize_composition(measure_composition())
    assert set(summary) == set(CONDITION_ORDER)
    # The C1 screenshot's per-step total is the heaviest of the three.
    totals = {cond: summary[cond]["total"] for cond in CONDITION_ORDER}
    assert totals["C1(est)"] == max(totals.values())
    # C3's condition-specific part is dominated by the tool schema it re-sends.
    assert summary["C3"]["tools_schema"] > summary["C3"]["observation"]


# --- Catalog-size sweep ------------------------------------------------------


def test_synthetic_catalog_preserves_real_products_and_shape():
    real = load_catalog()
    assert synthetic_catalog(len(real)) == real
    padded = synthetic_catalog(50)
    assert padded[: len(real)] == real
    assert len(padded) == 50
    ids = [item["id"] for item in padded]
    assert len(ids) == len(set(ids))  # no id collisions
    for item in padded[len(real) :]:
        assert set(item) == {"id", "name", "price", "sizes", "stock"}
        assert in_stock_sizes(item)  # padding has purchasable shape


def test_synthetic_catalog_rejects_shrinking():
    with pytest.raises(ValueError):
        synthetic_catalog(1)


def test_in_memory_replay_matches_http_baseline_at_real_size():
    """The sweep's in-memory replay reproduces measure_all at the real catalog."""
    http_costs = {c.task_id: c for c in measure_all()}
    rows = measure_catalog_sweep([len(load_catalog())])
    assert len(rows) == len(http_costs)
    for r in rows:
        h = http_costs[r.task_id]
        assert (r.steps, r.c3_obs_tokens, r.c4_obs_tokens) == (h.steps, h.c3_obs_tokens, h.c4_obs_tokens)
        assert r.c1_obs_tokens == h.c1_obs_tokens


def test_c4_grows_with_catalog_and_c3_does_not():
    summary = summarize_catalog_sweep(measure_catalog_sweep([8, 50]))
    assert summary[50]["C4"] > summary[8]["C4"]
    assert summary[50]["C3"] == summary[8]["C3"]
    assert summary[50]["C1(est)"] == summary[8]["C1(est)"]


def test_list_products_payload_grows_with_catalog():
    enc = _encoder()
    assert list_products_tokens(enc, synthetic_catalog(50)) > list_products_tokens(enc, synthetic_catalog(8))


def test_crossover_is_found_and_consistent():
    n = find_c4_over_c3_crossover(8, 50)
    assert n is not None
    assert 8 < n <= 50
    below = summarize_catalog_sweep(measure_catalog_sweep([n - 1]))[n - 1]
    at = summarize_catalog_sweep(measure_catalog_sweep([n]))[n]
    assert below["C4"] <= below["C3"]
    assert at["C4"] > at["C3"]
