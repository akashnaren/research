from __future__ import annotations

from harness.obs_cost import (
    count_tokens,
    image_tokens_high_detail,
    measure_all,
    summarize,
    _encoder,
)


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
